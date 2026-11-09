"""Run: python app.py. The GUI uses Tk, shipped with standard Python installers."""
from __future__ import annotations

import argparse
import os
import queue
import sqlite3
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.font import Font
from urllib.parse import urlsplit
import webbrowser

from core import Store, Tracker, connection_status, friendly_error, now

BG = "#F4F6F9"
WHITE = "#FFFFFF"
INK = "#191F28"
MUTED = "#7C8798"
BLUE = "#3182F6"
LINE = "#E9EDF3"
FONT = "Malgun Gothic" if sys.platform == "win32" else "Apple SD Gothic Neo" if sys.platform == "darwin" else "Noto Sans CJK KR"
ICONS = ["🐷", "🎧", "💻", "📷", "✈️", "🚗", "🏠", "🎮", "🎁", "👟", "⌚", "🌱", "📚", "🚲", "☕", "✨"]


def money(n):
    return f"{n:,}원"


def date_text(value):
    if not value:
        return "아직 확인 전"
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%m.%d %H:%M")
    except ValueError:
        return value


def rounded(c, x, y, w, h, color=WHITE, radius=22, outline=""):
    r = min(radius, w / 2, h / 2)
    return c.create_polygon(x+r,y, x+w-r,y, x+w,y, x+w,y+r, x+w,y+h-r, x+w,y+h,
                            x+w-r,y+h, x+r,y+h, x,y+h, x,y+h-r, x,y+r, x,y,
                            smooth=True, fill=color, outline=outline)


class Dialog(tk.Toplevel):
    def __init__(self, app, title, width=520):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.configure(bg=WHITE)
        self.resizable(False, False)
        self.transient(app)
        self.dialog_width = width
        self.scroll = tk.Canvas(self, bg=WHITE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.scroll.yview)
        scrollbar.pack(side="right", fill="y")
        self.scroll.pack(side="left", fill="both", expand=True)
        self.scroll.configure(yscrollcommand=scrollbar.set)
        self.body = tk.Frame(self.scroll, bg=WHITE, padx=28, pady=24)
        self.body_id = self.scroll.create_window(0, 0, anchor="nw", window=self.body, width=width-18)
        self.body.bind("<Configure>", lambda e: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.scroll.bind("<Configure>", lambda e: self.scroll.itemconfigure(self.body_id, width=e.width))
        tk.Label(self.body, text=title, bg=WHITE, fg=INK, font=(FONT, 19, "bold")).pack(anchor="w", pady=(0, 16))
        self.minsize(width, 100)
        self.bind("<Escape>", lambda e: self.destroy())
        self.after_idle(self.position)

    def position(self):
        if not self.winfo_exists():
            return
        self.update_idletasks()
        height = min(self.body.winfo_reqheight(), self.winfo_screenheight()-130)
        x = self.app.winfo_rootx() + (self.app.winfo_width() - self.dialog_width) // 2
        y = max(20, self.app.winfo_rooty() + (self.app.winfo_height() - height) // 2)
        self.geometry(f"{self.dialog_width}x{height}+{max(0,x)}+{y}")
        self.grab_set()

    def hint(self, text):
        tk.Label(self.body, text=text, bg=WHITE, fg=MUTED, font=(FONT, 10), justify="left", wraplength=460).pack(anchor="w", pady=(0, 14))

    def field(self, label, value=""):
        tk.Label(self.body, text=label, bg=WHITE, fg=INK, font=(FONT, 10, "bold")).pack(anchor="w", pady=(10, 5))
        e = ttk.Entry(self.body, font=(FONT, 11))
        e.insert(0, value or "")
        e.pack(fill="x", ipady=5)
        return e

    def submit(self, callback, text="저장하기"):
        def run():
            try:
                callback()
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("입력 내용을 확인해 주세요", str(exc), parent=self)
        ttk.Button(self.body, text=text, style="Accent.TButton", command=run).pack(fill="x", pady=(22, 0), ipady=6)


class App(tk.Tk):
    def __init__(self, store, demo=False):
        super().__init__()
        self.store, self.demo = store, demo
        self.title("모아 · 나의 위시 저금통" + (" · 데모" if demo else ""))
        self.geometry(f"1180x{min(860, self.winfo_screenheight()-100)}")
        self.minsize(940, 620)
        self.configure(bg=BG)
        self.option_add("*Font", (FONT, 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TEntry", fieldbackground=BG, bordercolor=LINE, padding=7)
        style.configure("TCombobox", fieldbackground=BG, padding=6)
        style.configure("TButton", background=BG, foreground=INK, borderwidth=0, padding=(14, 9), font=(FONT, 10, "bold"))
        style.map("TButton", background=[("active", "#E5EBF4")])
        style.configure("Accent.TButton", background=BLUE, foreground=WHITE)
        style.map("Accent.TButton", background=[("active", "#226FE0")])
        style.configure("Treeview", rowheight=35, font=(FONT, 10), background=WHITE, fieldbackground=WHITE)
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"), padding=8)
        self.active = None
        self.events = queue.Queue()
        self.busy = False
        self.pending = False
        self.net_busy = False
        self.online = None
        self.minutes = 30
        self.stop = threading.Event()
        self.button_widgets = []
        self.resize_job = None
        self.auto_job = None
        self.sidebar = tk.Frame(self, bg=WHITE, width=226)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Frame(self, bg=LINE, width=1).pack(side="left", fill="y")
        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(main, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(main, orient="vertical", command=self.canvas.yview)
        bar.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Control-n>", lambda e: self.edit_jar())
        self.bind("<Control-r>", lambda e: self.refresh())
        self.render()
        self.after(120, self.poll)
        if not demo:
            self.after(500, self.check_network)
            self.after(800, self.refresh)
        self.schedule()

    def wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1), "units")

    def on_resize(self, event):
        if self.resize_job:
            self.after_cancel(self.resize_job)
        self.resize_job = self.after(100, self.render_main)

    def text(self, x, y, text, size=11, color=INK, bold=False, width=None, anchor="nw"):
        return self.canvas.create_text(x, y, text=text, anchor=anchor, font=(FONT, size, "bold" if bold else "normal"), fill=color, width=width)

    def button(self, x, y, text, command, width=116, primary=False, color=None):
        b = tk.Button(self.canvas, text=text, command=command, bg=color or (BLUE if primary else "#EFF3F8"), fg=WHITE if primary else "#425168", activebackground="#246FE0" if primary else "#E2E9F2", activeforeground=WHITE if primary else INK, relief="flat", bd=0, cursor="hand2", font=(FONT, 10, "bold"), takefocus=True)
        self.canvas.create_window(x, y, window=b, anchor="nw", width=width, height=36)
        self.button_widgets.append(b)
        return b

    def fit(self, text, pixels, size=13):
        font = Font(family=FONT, size=size, weight="bold")
        if font.measure(text) <= pixels:
            return text
        while text and font.measure(text + "…") > pixels:
            text = text[:-1]
        return text + "…"

    def select(self, ident):
        self.active = ident
        self.canvas.yview_moveto(0)
        self.render()

    def render(self):
        jars = self.store.jars()
        if self.active not in [j["id"] for j in jars]:
            self.active = jars[0]["id"] if jars else None
        for child in self.sidebar.winfo_children():
            child.destroy()
        tk.Label(self.sidebar, text="모아", font=(FONT, 29, "bold"), bg=WHITE, fg=BLUE).pack(anchor="w", padx=26, pady=(31, 0))
        tk.Label(self.sidebar, text="작은 저금, 가까워지는 위시", font=(FONT, 9), bg=WHITE, fg=MUTED).pack(anchor="w", padx=27, pady=(1, 34))
        tk.Label(self.sidebar, text="MY SAVINGS", font=(FONT, 9, "bold"), bg=WHITE, fg=MUTED).pack(anchor="w", padx=27, pady=(0, 12))
        # Scroll independently when many jars are present.
        holder = tk.Frame(self.sidebar, bg=WHITE)
        holder.pack(fill="both", expand=True)
        jar_canvas = tk.Canvas(holder, bg=WHITE, highlightthickness=0)
        jar_scroll = ttk.Scrollbar(holder, orient="vertical", command=jar_canvas.yview)
        jar_scroll.pack(side="right", fill="y")
        jar_canvas.pack(side="left", fill="both", expand=True)
        jar_canvas.configure(yscrollcommand=jar_scroll.set)
        jar_list = tk.Frame(jar_canvas, bg=WHITE)
        jar_canvas.create_window(0, 0, window=jar_list, anchor="nw", width=208)
        for jar in jars:
            selected = jar["id"] == self.active
            tk.Button(jar_list, text=f'{jar["icon"]}  {jar["name"]}', anchor="w", wraplength=156, justify="left", bg="#EDF4FF" if selected else WHITE, fg=BLUE if selected else "#505B6D", relief="flat", bd=0, padx=15, pady=15, cursor="hand2", font=(FONT, 11, "bold" if selected else "normal"), command=lambda i=jar["id"]: self.select(i)).pack(fill="x", padx=(12, 0), pady=3)
        jar_list.update_idletasks()
        jar_canvas.configure(scrollregion=jar_canvas.bbox("all"))
        ttk.Button(self.sidebar, text="＋  새 저금통", command=self.edit_jar).pack(fill="x", padx=20, pady=12)
        tk.Label(self.sidebar, text="내가 직접 기록하는 저금\n실제 돈은 금융 앱에 보관해요", justify="left", bg=WHITE, fg=MUTED, font=(FONT, 9)).pack(anchor="w", padx=26, pady=(18, 14))
        ttk.Button(self.sidebar, text="설정 · 데이터 백업", command=self.settings).pack(fill="x", padx=20, pady=(0, 24))
        self.render_main()

    def render_main(self):
        self.resize_job = None
        c = self.canvas
        for b in self.button_widgets:
            b.destroy()
        self.button_widgets = []
        c.delete("all")
        w = max(680, c.winfo_width())
        x, right = 34, w - 34
        width = right - x
        self.text(x, 30, "나의 위시 저금통", 10, MUTED)
        self.text(x, 57, "갖고 싶은 일상에, 한 걸음 더", 23, bold=True)
        if self.demo:
            status, color = "●  데모 · 예시 데이터", BLUE
        elif self.online is None:
            status, color = "●  연결 확인 중", MUTED
        elif self.online:
            status, color = "●  인터넷 연결됨", "#21966B"
        else:
            status, color = "●  인터넷 연결 끊김 · 또는 확인 서버에 연결할 수 없어요", "#C27B19"
        self.text(x, 105, status, 9, color)
        self.button(right-118, 99, "조회 중…" if self.busy else "↻ 가격 새로고침", self.refresh, 118)
        if self.active is None:
            rounded(c, x, 164, width, 390)
            self.text(x+width/2, 205, "🐷", 60, anchor="n")
            self.text(x+width/2, 310, "첫 번째 위시를 담아볼까요?", 21, bold=True, anchor="n")
            self.text(x+width/2, 356, "저금통을 만들고, 사고 싶은 물건을 추가해 보세요.\n가격이 바뀌면 필요한 저금액도 함께 바뀌어요.", 11, MUTED, anchor="n")
            self.button(x+width/2-85, 437, "＋ 첫 저금통 만들기", self.edit_jar, 170, True)
            c.configure(scrollregion=(0,0,w,600))
            return
        jar = next(j for j in self.store.jars() if j["id"] == self.active)
        products = self.store.products(self.active)
        balance = self.store.balance(self.active)
        known = [p for p in products if p["krw"] is not None]
        total = sum(p["krw"] for p in known)
        unknown = len(products)-len(known)
        stale = any(p["error"] for p in products) or self.online is False
        y = 158
        rounded(c, x, y, width, 254, "#E8F1FF")
        self.text(x+26, y+24, self.fit(f'{jar["icon"]}  {jar["name"]}', width-190, 16), 16, bold=True)
        self.button(right-105, y+21, "편집", lambda: self.edit_jar(jar), 76, color="#DCEAFF")
        self.text(x+28, y+75, "지금까지 모았어요", 10, "#5D789D")
        self.text(x+25, y+102, money(balance), 34, bold=True)
        if not products:
            remaining = "첫 위시를 추가하고 목표를 정해 보세요."
        elif unknown:
            remaining = f"상품 {unknown}개의 가격을 확인하면 목표가 완성돼요."
        elif balance >= total:
            remaining = "위시를 살 만큼 모았어요!" if not stale else "저장된 가격 기준으로 목표를 달성했어요."
        else:
            remaining = f"아직 {money(total-balance)} 남았어요."
        self.text(x+28, y+164, remaining, 13, "#2763B2", True, width=width-56)
        rounded(c, x+28, y+211, width-56, 8, "#CEDFF6", 4)
        ratio = min(1, balance / total) if total > 0 and not unknown else 0
        if ratio:
            rounded(c, x+28, y+211, max(8,(width-56)*ratio), 8, BLUE, 4)
        target_label = f'{"확인된 가격 합계" if unknown else "위시 목표"}  {money(total)}'
        if stale and products:
            target_label += "  · 저장된 값 포함"
        self.text(x+28, y+228, target_label, 9, "#5D789D")
        self.text(right-28, y+228, "확인 중" if unknown else f"{int(ratio*100)}%", 9, "#5D789D", anchor="ne")
        y += 274
        self.button(x, y, "＋ 저금 기록", lambda: self.transaction("add"), 130, True)
        self.button(x+140, y, "출금 기록", lambda: self.transaction("withdraw"), 100)
        self.button(x+250, y, "잔액 수정", lambda: self.transaction("set"), 100)
        self.button(right-102, y, "기록 보기", self.transactions, 102)
        y += 64
        self.text(x, y, "나의 위시리스트", 17, bold=True)
        self.text(x, y+32, f"{len(products)}개의 위시 · 각 상품 1개씩 합산해요", 10, MUTED)
        self.button(right-113, y, "＋ 상품 추가", self.edit_product, 113)
        y += 76
        if not products:
            rounded(c, x, y, width, 140)
            self.text(x+25, y+27, "무엇을 위해 모으고 있나요?", 14, bold=True)
            self.text(x+25, y+64, "상품 링크를 추가하면 가격과 남은 금액을 함께 확인할 수 있어요.", 10, MUTED, width=width-50)
            y += 158
        for p in products:
            height = 224 if p["error"] else 169
            rounded(c, x, y, width, height)
            rounded(c, x+20, y+22, 46, 46, "#F0F4FA", 14)
            self.text(x+43, y+28, "↗" if p["mode"] == "auto" else "✎", 22, BLUE, anchor="n")
            self.text(x+81, y+20, self.fit(p["name"], width-340), 13, bold=True)
            host = urlsplit(p["url"]).hostname or "내가 정한 가격"
            self.text(x+81, y+49, host[:48], 9, MUTED)
            self.text(right-22, y+22, money(p["krw"]) if p["krw"] is not None else "가격 확인 대기", 17, bold=True, anchor="ne")
            if p["original"] and p["currency"] != "KRW":
                self.text(right-22, y+53, f'{p["original"]} {p["currency"]}', 9, MUTED, anchor="ne")
            source = p["source"] or ("자동 추적 대기" if p["mode"] == "auto" else "직접 입력")
            self.text(x+22, y+84, f'{source}  ·  {date_text(p["checked"])}', 9, MUTED, width=width-44)
            if p["rate_date"]:
                self.text(x+22, y+105, f'1 {p["currency"]} ≈ {p["rate"]}원 · 환율 기준 {p["rate_date"]}', 9, MUTED, width=width-44)
            else:
                self.text(x+22, y+105, "상품 가격 기준 · 배송비·세금·카드 수수료 별도", 9, MUTED)
            if p["error"]:
                self.text(x+22, y+127, "! " + p["error"], 9, "#B87819", width=width-44)
            by = y + height - 43
            if p["url"]:
                self.button(x+20, by, "상품 보기 ↗", lambda url=p["url"]: webbrowser.open(url), 105)
            self.button(right-246, by, "가격 기록", lambda pid=p["id"]: self.price_history(pid), 90)
            self.button(right-146, by, "수정", lambda item=p: self.edit_product(item), 56)
            self.button(right-80, by, "삭제", lambda item=p: self.delete_product(item), 56)
            y += height+14
        self.text(x, y+9, f"앱 실행 중 {self.minutes}분마다 가격 확인 · 연결 상태는 30초마다 확인", 9, MUTED)
        self.text(x, y+32, "외화는 기준 환율로 환산한 예상 금액이에요. 실제 결제 금액과 다를 수 있어요.", 9, MUTED, width=width)
        c.configure(scrollregion=(0,0,w,y+90))

    def edit_jar(self, jar=None):
        d = Dialog(self, "저금통 편집" if jar else "새로운 저금통")
        d.hint("이름과 아이콘을 골라 나만의 저금통을 만들어 보세요.")
        name = d.field("저금통 이름", jar["name"] if jar else "")
        icon = d.field("아이콘 · 이모지나 짧은 글자도 좋아요", jar["icon"] if jar else "🐷")
        grid = tk.Frame(d.body, bg=WHITE)
        grid.pack(fill="x", pady=12)
        for i, emoji in enumerate(ICONS):
            def choose(e=emoji):
                icon.delete(0, "end")
                icon.insert(0, e)
            tk.Button(grid, text=emoji, font=(FONT, 20), bg=BG, bd=0, width=3, command=choose).grid(row=i//8, column=i%8, padx=2, pady=3)
        def save():
            self.active = self.store.jar(name.get(), icon.get(), jar["id"] if jar else None)
            d.destroy()
            self.render()
        d.submit(save)
        if jar:
            def remove():
                if messagebox.askyesno("저금통 삭제", "이 저금통의 상품과 모든 기록도 삭제돼요. 삭제할까요?", parent=d):
                    self.store.delete("jars", jar["id"])
                    d.destroy()
                    self.render()
            ttk.Button(d.body, text="저금통 삭제", command=remove).pack(fill="x", pady=(10, 0))
        name.focus_set()

    def edit_product(self, product=None):
        if self.active is None:
            return
        p = product or {}
        d = Dialog(self, "위시 수정" if product else "새로운 위시")
        d.hint("상품 1개의 가격을 목표에 더해요. 자동 추적이 지원되지 않는 판매처는 직접 입력할 수 있어요.")
        name = d.field("상품 이름", p.get("name", ""))
        url = d.field("상품 URL", p.get("url", ""))
        tk.Label(d.body, text="가격 확인 방식", bg=WHITE, fg=INK).pack(anchor="w", pady=(14, 5))
        mode = ttk.Combobox(d.body, values=["자동 추적", "직접 입력"], state="readonly")
        mode.current(1 if p.get("mode") == "manual" else 0)
        mode.pack(fill="x")
        code = d.field("통화 코드 · 자동 추적은 페이지의 통화를 우선 사용", p.get("currency", "KRW"))
        price = d.field("직접 입력 가격 · 예: 249000 또는 199.99", p.get("original", ""))
        selector = d.field("고급: 가격 CSS 선택자 · 비워두면 자동 감지", p.get("selector", ""))
        d.hint("선택자를 지정하면 위 통화를 사용해요. 옵션 최저가가 감지되면 별도로 표시해요.")
        def changed(e=None):
            manual = mode.current() == 1
            price.configure(state="normal" if manual else "disabled")
            selector.configure(state="disabled" if manual else "normal")
        mode.bind("<<ComboboxSelected>>", changed)
        changed()
        def save():
            self.store.save_product(self.active, name.get(), url.get(), "manual" if mode.current() else "auto", code.get(), price.get(), selector.get(), p.get("id"))
            d.destroy()
            self.render_main()
            self.refresh()
        d.submit(save, "위시 저장하기")
        name.focus_set()

    def transaction(self, kind):
        if self.active is None:
            return
        labels = {"add":"저금 기록하기", "withdraw":"출금 기록하기", "set":"현재 잔액 수정"}
        d = Dialog(self, labels[kind])
        d.hint("실제 돈은 이동하지 않아요. 금융 앱에 보관한 금액을 여기에 기록해 주세요.")
        value = d.field("현재 잔액 (원)" if kind == "set" else "금액 (원)", str(self.store.balance(self.active)) if kind == "set" else "")
        note = d.field("메모 · 선택")
        def save():
            self.store.transact(self.active, value.get(), kind, note.get())
            d.destroy()
            self.render_main()
        d.submit(save, "기록하기")
        value.focus_set()

    def table(self, title, headings, rows):
        d = Dialog(self, title, 760)
        frame = tk.Frame(d.body, bg=WHITE)
        frame.pack(fill="both", expand=True)
        cols = [str(i) for i in range(len(headings))]
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for i, heading in enumerate(headings):
            tree.heading(str(i), text=heading)
            tree.column(str(i), width=160 if i else 110, anchor="w")
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        for row in rows:
            tree.insert("", "end", values=row)
        if not rows:
            d.hint("아직 기록이 없어요.")
        d.hint("최근 200개 기록을 표시해요. 전체 기록은 데이터 백업에 포함돼요.")

    def transactions(self):
        rows = self.store.rows("SELECT * FROM transactions WHERE jar_id=? ORDER BY id DESC LIMIT 200", (self.active,))
        self.table("저금 기록", ["일시", "변동 금액", "메모"], [(date_text(r["created"]), ("+" if r["delta"] > 0 else "") + money(r["delta"]), r["note"]) for r in rows])

    def price_history(self, ident):
        rows = self.store.rows("SELECT * FROM prices WHERE product_id=? ORDER BY id DESC LIMIT 200", (ident,))
        self.table("가격 기록", ["확인 시각", "원래 가격", "원화 환산", "환율 기준일"], [(date_text(r["created"]), f'{r["original"]} {r["currency"]}', money(r["krw"]), r["rate_date"] or "—") for r in rows])

    def delete_product(self, product):
        if messagebox.askyesno("위시 삭제", f'{product["name"]}과 가격 기록을 삭제할까요?', parent=self):
            self.store.delete("products", product["id"])
            self.render_main()

    def settings(self):
        d = Dialog(self, "설정 · 데이터 백업")
        d.hint("가격 추적은 앱이 실행 중일 때만 동작해요. 앱을 다시 열면 즉시 확인해요.")
        tk.Label(d.body, text="자동 확인 간격", bg=WHITE).pack(anchor="w", pady=8)
        interval = ttk.Combobox(d.body, values=["5", "15", "30", "60"], state="readonly")
        interval.set(str(self.minutes))
        interval.pack(fill="x")
        d.hint("단위: 분 · 기본 30분 · 변경한 간격은 이번 실행에 적용돼요.")
        def backup():
            path = filedialog.asksaveasfilename(parent=d, title="데이터 백업", defaultextension=".sqlite3", initialfile="moa-backup.sqlite3", filetypes=[("SQLite database", "*.sqlite3")])
            if path:
                try:
                    self.store.backup(path)
                    messagebox.showinfo("백업 완료", "저금통, 상품, 입출금·가격 기록을 저장했어요.", parent=d)
                except (ValueError, OSError, sqlite3.Error) as exc:
                    messagebox.showerror("백업 실패", str(exc), parent=d)
        ttk.Button(d.body, text="모든 데이터 백업", command=backup).pack(fill="x", pady=12)
        d.hint("데이터 위치: " + self.store.path)
        def save():
            self.minutes = int(interval.get())
            self.schedule()
            d.destroy()
            self.render_main()
        d.submit(save)

    def schedule(self):
        if self.auto_job:
            self.after_cancel(self.auto_job)
        def tick():
            if not self.demo:
                self.refresh()
            self.schedule()
        self.auto_job = self.after(self.minutes * 60_000, tick)

    def refresh(self):
        if self.demo:
            messagebox.showinfo("데모 화면", "데모에서는 네트워크 조회를 하지 않아요. 실제 추적은 python app.py로 실행해 주세요.", parent=self)
            return
        if self.busy:
            self.pending = True
            return
        products = self.store.products()
        if not products:
            return
        cached = {r["currency"]:r for r in self.store.rows("SELECT * FROM rates")}
        self.busy = True
        self.render_main()
        def work():
            tracker = Tracker(cached_rates=cached)
            try:
                for p in products:
                    if self.stop.is_set():
                        break
                    try:
                        self.events.put(("price", p, tracker.update(p), ""))
                    except Exception as exc:
                        self.events.put(("price", p, None, friendly_error(exc)))
            finally:
                self.events.put(("done",))
        threading.Thread(target=work, daemon=True).start()

    def check_network(self):
        if not self.net_busy:
            self.net_busy = True
            def work():
                try:
                    self.events.put(("network", connection_status()))
                except Exception:
                    self.events.put(("network", False))
            threading.Thread(target=work, daemon=True).start()
        self.after(30_000, self.check_network)

    def poll(self):
        dirty = False
        while True:
            try:
                e = self.events.get_nowait()
            except queue.Empty:
                break
            if e[0] == "price":
                self.store.apply_result(e[1], e[2], e[3])
                dirty = True
            elif e[0] == "done":
                self.busy = False
                dirty = True
                if self.pending:
                    self.pending = False
                    self.after(200, self.refresh)
            elif e[0] == "network":
                previous = self.online
                self.online, self.net_busy = e[1], False
                dirty = True
                if self.online and previous is False:
                    self.after(200, self.refresh)
        if dirty:
            self.render_main()
        self.after(150, self.poll)

    def close(self):
        self.stop.set()
        self.store.db.close()
        self.destroy()


def seed_demo(store):
    j = store.jar("나를 위한 작은 선물", "🎁")
    store.jar("다음 여행의 시작", "✈️")
    store.jar("책상이 좋아지는 시간", "💻")
    store.transact(j, 350000, "add", "차곡차곡 모은 돈 · 예시")
    for name, price, code, rate in [("노이즈 캔슬링 헤드폰", "329000", "KRW", "1"), ("매일 쓰고 싶은 키보드", "129", "USD", "1400")]:
        ident = store.save_product(j, name, "", "manual", code, price)
        p = next(p for p in store.products() if p["id"] == ident)
        from decimal import Decimal
        store.apply_result(p, {"original":Decimal(price), "currency":code, "krw":int(Decimal(price)*Decimal(rate)), "rate":Decimal(rate), "rate_date":"2026-11-06" if code != "KRW" else "", "source":"예시 가격 · 실제 시세 아님"})


def default_data_path():
    # PyInstaller onefile extracts __file__ to a disposable directory.
    # Keep packaged Windows data in the user's permanent application-data folder.
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "Moa" / "moa.sqlite3"
    return Path(__file__).resolve().parent / "data" / "moa.sqlite3"


def main():
    parser = argparse.ArgumentParser(description="모아 · 로컬 저금통 앱")
    parser.add_argument("--demo", action="store_true", help="저장되지 않는 예시 화면")
    parser.add_argument("--data", type=Path, default=default_data_path())
    args = parser.parse_args()
    store = Store(":memory:" if args.demo else args.data)
    if args.demo:
        seed_demo(store)
    App(store, args.demo).mainloop()


if __name__ == "__main__":
    main()
