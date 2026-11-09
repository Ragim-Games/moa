import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Store, Tracker, amount, connection_status, display_price, extract_price, validate_url, won


def product_html(offers):
    return '<script type="application/ld+json">' + json.dumps({"@type":"Product", "offers":offers}) + '</script>'


class PriceTests(unittest.TestCase):
    def test_json_ld(self):
        q = extract_price(product_html({"price":"199.99", "priceCurrency":"USD"}))
        self.assertEqual((q.price, q.currency), (Decimal("199.99"), "USD"))

    def test_nested_graph(self):
        html = '<script type="application/ld+json">{"@graph":[{"@type":["Product"],"offers":{"price":12000,"priceCurrency":"KRW"}}]}</script>'
        self.assertEqual(extract_price(html).price, 12000)

    def test_meta(self):
        self.assertEqual(extract_price('<meta property="product:price:amount" content="19000"><meta property="product:price:currency" content="KRW">').price, 19000)

    def test_selector_european(self):
        self.assertEqual(extract_price('<b class="price">€ 1.234,56</b>', "EUR", ".price").price, Decimal("1234.56"))

    def test_visible_prices(self):
        for value, expected in [("₩ 1,299,000", "1299000"), ("$199.99", "199.99"), ("1\u00a0299,00 EUR", "1299"), ("12,50 €", "12.50")]:
            self.assertEqual(display_price(value), Decimal(expected))

    def test_reject_multiple_numbers(self):
        for value in ("199원 / 249원", "199 249", "월 9,900원 12개월", "-100원"):
            with self.assertRaises(ValueError):
                display_price(value)

    def test_ambiguous_offers(self):
        with self.assertRaises(ValueError):
            extract_price(product_html([{"price":10,"priceCurrency":"USD"}, {"price":20,"priceCurrency":"USD"}]))

    def test_multiple_products(self):
        with self.assertRaises(ValueError):
            extract_price(product_html({"price":10,"priceCurrency":"USD"})*2)

    def test_no_currency_no_guess(self):
        with self.assertRaises(ValueError):
            extract_price(product_html({"price":10}))

    def test_no_arbitrary_numbers(self):
        with self.assertRaises(ValueError):
            extract_price("<p>로그인 2026년 가격 100원</p>")

    def test_aggregate_label(self):
        self.assertIn("최저가", extract_price(product_html({"lowPrice":10,"highPrice":20,"priceCurrency":"USD"})).source)

    def test_sold_out(self):
        with self.assertRaises(ValueError):
            extract_price(product_html({"price":10,"priceCurrency":"USD","availability":"https://schema.org/OutOfStock"}))

    def test_selector_count(self):
        with self.assertRaises(ValueError):
            extract_price('<b>100</b><b>200</b>', "KRW", "b")

    def test_invalid_amount(self):
        for v in ("NaN", "Infinity", "-1", "0", "abc", "1000000000001"):
            with self.assertRaises(ValueError):
                amount(v)
        self.assertEqual(won(Decimal("100.5")), 101)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.j = self.s.jar("헤드폰", "🎧")

    def tearDown(self):
        self.s.db.close()

    def test_transactions(self):
        self.s.transact(self.j, "100,000", "add")
        self.s.transact(self.j, "20000", "withdraw")
        self.s.transact(self.j, "120000", "set")
        self.assertEqual(self.s.balance(self.j), 120000)
        self.assertEqual(len(self.s.rows("SELECT * FROM transactions")), 3)

    def test_overdraft_atomic(self):
        self.s.transact(self.j, 100, "add")
        with self.assertRaises(ValueError):
            self.s.transact(self.j, 101, "withdraw")
        self.assertEqual(self.s.balance(self.j), 100)
        with self.assertRaises(ValueError):
            self.s.transact(self.j, "1.5", "add")

    def test_zero_reset(self):
        self.s.transact(self.j, 100, "add")
        self.s.transact(self.j, 0, "set")
        self.assertEqual(self.s.balance(self.j), 0)

    def test_isolated_balances(self):
        other = self.s.jar("여행", "✈")
        self.s.transact(self.j, 100, "add")
        self.assertEqual(self.s.balance(other), 0)

    def test_manual_foreign_unknown(self):
        self.s.save_product(self.j, "Keyboard", "", "manual", "USD", "100")
        self.assertIsNone(self.s.products()[0]["krw"])

    def test_keep_last_price_on_error(self):
        self.s.save_product(self.j, "Keyboard", "", "manual", "KRW", "120000")
        p = self.s.products()[0]
        self.s.apply_result(p, error="연결 실패")
        self.assertEqual(self.s.products()[0]["krw"], 120000)
        self.assertEqual(self.s.products()[0]["error"], "연결 실패")

    def test_revision_prevents_race(self):
        i = self.s.save_product(self.j, "A", "", "manual", "KRW", "100")
        old = self.s.products()[0]
        self.s.save_product(self.j, "B", "", "manual", "KRW", "200", product_id=i)
        self.s.apply_result(old, error="old error")
        self.assertEqual(self.s.products()[0]["krw"], 200)
        self.assertFalse(self.s.products()[0]["error"])

    def test_cascade_and_late_result(self):
        self.s.save_product(self.j, "A", "", "manual", "KRW", "100")
        p = self.s.products()[0]
        self.s.delete("jars", self.j)
        self.s.apply_result(p, error="late")
        self.assertEqual(self.s.products(), [])

    def test_backup_persistence(self):
        self.s.transact(self.j, 9876, "add")
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "backup.sqlite3"
            self.s.backup(p)
            restored = Store(p)
            self.assertEqual(restored.balance(self.j), 9876)
            restored.db.close()


class NetworkTests(unittest.TestCase):
    def product(self):
        return {"mode":"manual", "original":"199.99", "currency":"USD"}

    def test_fx_and_rounding(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return json.dumps({"base":"USD","quote":"KRW","rate":1400,"date":"2026-11-06"})
        t = Tracker(fetch)
        self.assertEqual(t.update(self.product())["krw"], 279986)
        t.update(self.product())
        self.assertEqual(len(calls), 1)

    def test_fx_cached_on_failure(self):
        def fail(url):
            raise OSError("offline")
        t = Tracker(fail, {"USD":{"rate":"1400", "date":"2026-11-06"}})
        r = t.update(self.product())
        self.assertTrue(r["warning"])
        self.assertEqual(r["krw"], 279986)

    def test_no_rate_never_fabricated(self):
        with self.assertRaises(ValueError):
            Tracker(lambda url: "{}").update(self.product())

    def test_wrong_currency_rejected(self):
        with self.assertRaises(ValueError):
            Tracker(lambda url: '{"base":"EUR","quote":"KRW","rate":1,"date":"2026-11-06"}').update(self.product())

    def test_offline_and_site_independent(self):
        import requests
        with patch("core.requests.get", side_effect=requests.ConnectionError):
            self.assertFalse(connection_status())
        with patch("core.requests.get") as get:
            get.return_value.status_code = 204
            self.assertTrue(connection_status())

    def test_local_urls_rejected(self):
        with self.assertRaises(ValueError):
            validate_url("file:///secret")
        with patch("core.socket.getaddrinfo", return_value=[(0,0,0,"",("127.0.0.1",443))]):
            with self.assertRaises(ValueError):
                validate_url("https://localhost")


if __name__ == "__main__":
    unittest.main()
