"""MOA: local bookkeeping, conservative price extraction and exchange rates."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

MAX_MONEY = 1_000_000_000_000


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def amount(value, *, allow_zero=False):
    try:
        n = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise ValueError("금액을 숫자로 입력해 주세요.") from None
    if not n.is_finite() or n > MAX_MONEY or n < 0 or (not allow_zero and n == 0):
        raise ValueError("금액은 0보다 크고 1조 이하여야 해요.")
    return n


def won(value):
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def currency(value):
    code = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("통화 코드는 KRW, USD처럼 영문 3자로 입력해 주세요.")
    return code


class Store:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jars(
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, icon TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY, jar_id INTEGER NOT NULL REFERENCES jars ON DELETE CASCADE,
          delta INTEGER NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY, jar_id INTEGER NOT NULL REFERENCES jars ON DELETE CASCADE,
          name TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL,
          selector TEXT NOT NULL DEFAULT '', currency TEXT NOT NULL, original TEXT,
          krw INTEGER, rate TEXT, rate_date TEXT, checked TEXT,
          error TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS prices(
          id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products ON DELETE CASCADE,
          original TEXT NOT NULL, currency TEXT NOT NULL, krw INTEGER NOT NULL,
          rate TEXT NOT NULL, rate_date TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rates(
          currency TEXT PRIMARY KEY, rate TEXT NOT NULL, date TEXT NOT NULL, fetched TEXT NOT NULL);
        """)

    def rows(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args)]

    def jars(self):
        return self.rows("SELECT * FROM jars ORDER BY id")

    def products(self, jar_id=None):
        return self.rows("SELECT * FROM products" + (" WHERE jar_id=?" if jar_id is not None else "") + " ORDER BY id", (() if jar_id is None else (jar_id,)))

    def jar(self, name, icon, jar_id=None):
        name, icon = name.strip(), icon.strip()
        if not name or len(name) > 40 or not icon or len(icon) > 8:
            raise ValueError("저금통 이름은 1~40자, 아이콘은 1~8자로 입력해 주세요.")
        with self.db:
            if jar_id is not None:
                self.db.execute("UPDATE jars SET name=?,icon=? WHERE id=?", (name, icon, jar_id))
                return jar_id
            return self.db.execute("INSERT INTO jars(name,icon) VALUES(?,?)", (name, icon)).lastrowid

    def balance(self, jar_id):
        return self.db.execute("SELECT COALESCE(SUM(delta),0) FROM transactions WHERE jar_id=?", (jar_id,)).fetchone()[0]

    def transact(self, jar_id, value, kind, note=""):
        n = amount(value, allow_zero=kind == "set")
        if n != n.to_integral_value():
            raise ValueError("저금액은 1원 단위로 입력해 주세요.")
        if kind not in ("add", "withdraw", "set"):
            raise ValueError("알 수 없는 기록 종류예요.")
        with self.db:
            bal = self.balance(jar_id)
            delta = int(n) - bal if kind == "set" else int(n) * (-1 if kind == "withdraw" else 1)
            if not 0 <= bal + delta <= MAX_MONEY:
                raise ValueError("잔액보다 많이 뺄 수 없고, 잔액은 1조 원 이하여야 해요.")
            if delta:
                self.db.execute("INSERT INTO transactions(jar_id,delta,note,created) VALUES(?,?,?,?)", (jar_id, delta, note.strip()[:200] or {"add":"저금 기록", "withdraw":"출금 기록", "set":"잔액 수정"}[kind], now()))

    def save_product(self, jar_id, name, url, mode, code, price="", selector="", product_id=None):
        name, url, selector = name.strip(), url.strip(), selector.strip()
        if not name or len(name) > 80:
            raise ValueError("상품 이름을 1~80자로 입력해 주세요.")
        code = currency(code)
        if mode not in ("auto", "manual"):
            raise ValueError("조회 방식을 선택해 주세요.")
        if url:
            validate_url(url, resolve=False)
        if mode == "auto" and not url:
            raise ValueError("자동 추적할 상품의 URL을 입력해 주세요.")
        original = str(amount(price)) if mode == "manual" else None
        krw = won(original) if original is not None and code == "KRW" else None
        checked = now() if krw is not None else None
        source = "직접 입력" if mode == "manual" else ""
        args = (jar_id, name, url, mode, selector, code, original, krw, checked, source)
        with self.db:
            if product_id is None:
                product_id = self.db.execute("INSERT INTO products(jar_id,name,url,mode,selector,currency,original,krw,checked,source) VALUES(?,?,?,?,?,?,?,?,?,?)", args).lastrowid
            else:
                self.db.execute("UPDATE products SET jar_id=?,name=?,url=?,mode=?,selector=?,currency=?,original=?,krw=?,checked=?,source=?,error='',rate=NULL,rate_date=NULL,revision=revision+1 WHERE id=?", args + (product_id,))
        return product_id

    def delete(self, table, ident):
        if table not in ("jars", "products"):
            raise ValueError("Invalid table")
        with self.db:
            self.db.execute(f"DELETE FROM {table} WHERE id=?", (ident,))

    def apply_result(self, p, result=None, error=""):
        # Discard results for products changed/deleted while the worker was running.
        with self.db:
            row = self.db.execute("SELECT revision FROM products WHERE id=?", (p["id"],)).fetchone()
            if row is None or row[0] != p["revision"]:
                return
            if error:
                self.db.execute("UPDATE products SET error=? WHERE id=?", (error, p["id"]))
                return
            r = result
            stamp = now()
            self.db.execute("UPDATE products SET original=?,currency=?,krw=?,rate=?,rate_date=?,checked=?,source=?,error=? WHERE id=?", (str(r["original"]), r["currency"], r["krw"], str(r["rate"]), r["rate_date"], stamp, r["source"], r.get("warning", ""), p["id"]))
            self.db.execute("INSERT INTO prices(product_id,original,currency,krw,rate,rate_date,created) VALUES(?,?,?,?,?,?,?)", (p["id"], str(r["original"]), r["currency"], r["krw"], str(r["rate"]), r["rate_date"], stamp))
            if r["currency"] != "KRW" and not r.get("warning"):
                self.db.execute("INSERT OR REPLACE INTO rates VALUES(?,?,?,?)", (r["currency"], str(r["rate"]), r["rate_date"], stamp))

    def backup(self, path):
        if self.path != ":memory:" and Path(path).resolve() == Path(self.path).resolve():
            raise ValueError("현재 데이터 파일과 다른 이름으로 저장해 주세요.")
        with closing(sqlite3.connect(path)) as target:
            self.db.backup(target)


def validate_url(url, resolve=True):
    u = urlsplit(url)
    if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password:
        raise ValueError("공개 상품 페이지의 http(s) 주소를 입력해 주세요.")
    if u.port not in (None, 80, 443):
        raise ValueError("일반 웹 포트(80/443)만 지원해요.")
    if resolve:
        for addr in socket.getaddrinfo(u.hostname, u.port or 443, type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(addr[4][0]).is_global:
                raise ValueError("로컬·사설 네트워크 주소는 조회하지 않아요.")
    return url


class Fetcher:
    """No logins, browser automation, or anti-bot bypass. Bounded public HTTP reads."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent":"MoaSavings/1.0 (personal price tracker)", "Accept-Language":"ko,en;q=0.8"})

    def get(self, url):
        deadline = time.monotonic() + 25
        for _ in range(6):
            validate_url(url)
            with self.session.get(url, timeout=(5, 8), allow_redirects=False, stream=True) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers["Location"])
                    continue
                r.raise_for_status()
                data = bytearray()
                for chunk in r.iter_content(32768):
                    data.extend(chunk)
                    if len(data) > 4_000_000 or time.monotonic() > deadline:
                        raise ValueError("페이지가 너무 크거나 응답이 지연돼요.")
                encoding = r.encoding if "charset=" in r.headers.get("Content-Type", "").lower() else "utf-8"
                return bytes(data).decode(encoding or "utf-8", errors="replace")
        raise ValueError("페이지 이동이 너무 많아요.")


@dataclass(frozen=True)
class Quote:
    price: Decimal
    currency: str
    source: str


def display_price(text):
    """Parse ONE visible price; never concatenate sale/original/installment values."""
    if re.search(r"-\s*\d", str(text)):
        raise ValueError("음수 가격은 사용할 수 없어요.")
    tokens = re.findall(r"\d{1,3}(?:\u00a0\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*", str(text))
    tokens = [x.strip() for x in tokens]
    if len(tokens) != 1:
        raise ValueError("가격이 여러 개예요. 실제 판매가격 요소만 선택해 주세요.")
    t = re.sub(r"\s", "", tokens[0])
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", t):
            t = t.replace(",", "")
        elif t.count(",") == 1 and len(t.split(",")[1]) in (1, 2):
            t = t.replace(",", ".")
        else:
            raise ValueError("가격의 숫자 형식을 확인해 주세요.")
    elif t.count(".") > 1:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")
    return amount(t)


def extract_price(html, fallback_currency="KRW", selector=""):
    soup = BeautifulSoup(html, "html.parser")
    if selector:
        nodes = soup.select(selector)
        if len(nodes) != 1:
            raise ValueError("가격 선택자는 정확히 한 요소를 가리켜야 해요.")
        n = nodes[0]
        return Quote(display_price(n.get("content") or n.get_text(" ", strip=True)), currency(fallback_currency), "지정한 가격 요소 · 지정 통화")

    def walk(v):
        if isinstance(v, dict):
            yield v
            for item in v.values():
                yield from walk(item)
        elif isinstance(v, list):
            for item in v:
                yield from walk(item)

    products = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for node in walk(data):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "Product" in types:
                products.append(node)
    if len(products) > 1:
        raise ValueError("여러 상품·옵션이 감지됐어요. 가격 요소를 지정하거나 직접 입력해 주세요.")
    if products:
        offers = products[0].get("offers", [])
        offers = offers if isinstance(offers, list) else [offers]
        quotes = []
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            if str(offer.get("availability", "")).rsplit("/", 1)[-1] in ("OutOfStock", "Discontinued", "SoldOut"):
                raise ValueError("품절 상품이에요. 마지막 가격을 유지해요.")
            raw = offer.get("price")
            source = "자동 추적"
            if raw is None and "lowPrice" in offer:
                raw, source = offer["lowPrice"], "자동 추적 · 옵션 최저가"
            if raw is not None:
                code = offer.get("priceCurrency")
                if not code:
                    raise ValueError("상품의 통화를 확인할 수 없어요. 가격 요소와 통화를 지정해 주세요.")
                # Schema.org numeric prices have a decimal dot, never grouping separators.
                if not re.fullmatch(r"\d+(\.\d+)?", str(raw)):
                    raise ValueError("판매처의 가격 데이터 형식이 올바르지 않아요.")
                quotes.append(Quote(amount(raw), currency(code), source))
        if quotes:
            if len({(q.price, q.currency) for q in quotes}) != 1:
                raise ValueError("판매가격이 여러 개예요. 원하는 옵션의 가격 요소를 지정해 주세요.")
            return quotes[0]

    # Only explicitly labelled product-price metadata, never arbitrary page numbers.
    for prefix in ("product:price", "og:price"):
        prices = soup.select(f'meta[property="{prefix}:amount"]')
        codes = soup.select(f'meta[property="{prefix}:currency"]')
        if len(prices) == len(codes) == 1:
            return Quote(amount(prices[0].get("content", "")), currency(codes[0].get("content", "")), "자동 추적 · 메타데이터")
    raise ValueError("공개 가격을 찾지 못했어요. 가격 요소를 지정하거나 직접 입력해 주세요.")


class Tracker:
    def __init__(self, fetch=None, cached_rates=None):
        self.fetch = fetch or Fetcher().get
        self.cached = cached_rates or {}
        self.fresh = {}

    def rate(self, code):
        if code == "KRW":
            return Decimal(1), "", ""
        if code in self.fresh:
            return self.fresh[code]
        try:
            data = json.loads(self.fetch(f"https://api.frankfurter.dev/v2/rate/{code.lower()}/krw"))
            if data.get("base", "").upper() != code or data.get("quote", "").upper() != "KRW":
                raise ValueError("환율 응답의 통화가 달라요.")
            rate = amount(data["rate"])
            date = data["date"]
            datetime.strptime(date, "%Y-%m-%d")
            result = (rate, date, "")
        except (requests.RequestException, ValueError, KeyError, TypeError, OSError):
            cached = self.cached.get(code)
            if not cached:
                raise ValueError(f"{code} 환율을 가져오지 못했어요. 기존 가격을 유지해요.") from None
            result = (Decimal(cached["rate"]), cached["date"], "환율 갱신 실패 · 저장된 환율로 계산")
        self.fresh[code] = result
        return result

    def update(self, product):
        if product["mode"] == "manual":
            q = Quote(amount(product["original"]), currency(product["currency"]), "직접 입력")
        else:
            q = extract_price(self.fetch(product["url"]), product["currency"], product["selector"])
        rate, date, warning = self.rate(q.currency)
        return {"original":q.price, "currency":q.currency, "krw":won(q.price * rate), "rate":rate, "rate_date":date, "source":q.source, "warning":warning}


def connection_status():
    # Independent checks: a blocked shopping site is not treated as loss of internet.
    for url in ("https://www.gstatic.com/generate_204", "https://www.msftconnecttest.com/connecttest.txt"):
        try:
            r = requests.get(url, timeout=(3, 3), allow_redirects=False)
            if (r.status_code == 204) or (r.status_code == 200 and r.text.strip() == "Microsoft Connect Test"):
                return True
        except requests.RequestException:
            pass
    return False


def friendly_error(error):
    if isinstance(error, requests.HTTPError):
        code = error.response.status_code
        return f"판매처 응답 {code} · 접근 제한 또는 페이지 오류예요."
    if isinstance(error, (requests.RequestException, OSError)):
        return "판매처에 연결하지 못했어요. 마지막 가격을 유지해요."
    return str(error)[:240] or "조회에 실패했어요. 마지막 가격을 유지해요."
