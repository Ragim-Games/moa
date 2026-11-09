"""Exercise real dialog callbacks with an in-memory DB; no external services."""
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, Dialog
from core import Store


class DialogFlowTests(unittest.TestCase):
    def test_create_jar_save_product_and_record_balance(self):
        store = Store(":memory:")
        try:
            app = App(store, demo=True)
        except tk.TclError as exc:
            store.db.close()
            self.skipTest(f"Tk display unavailable: {exc}")
        app.withdraw()
        errors = []
        app.report_callback_exception = lambda *args: errors.append(args)

        def dialog():
            return [w for w in app.winfo_children() if isinstance(w, Dialog)][-1]

        def entries(d):
            return [w for w in d.body.winfo_children() if type(w) is ttk.Entry]

        def submit(d, text):
            next(w for w in d.body.winfo_children() if isinstance(w, ttk.Button) and w.cget("text") == text).invoke()

        try:
            with patch.object(Dialog, "position", lambda d: d.withdraw()), patch("app.messagebox.showinfo"), patch("app.messagebox.showerror") as error:
                app.edit_jar()
                d = dialog()
                entries(d)[0].insert(0, "테스트 저금통")
                submit(d, "저장하기")
                self.assertEqual(len(store.jars()), 1)

                app.transaction("add")
                d = dialog()
                entries(d)[0].insert(0, "150000")
                submit(d, "기록하기")
                self.assertEqual(store.balance(app.active), 150000)

                for name, price in [("헤드폰", "200000"), ("키보드", "100000")]:
                    app.edit_product()
                    d = dialog()
                    fields = entries(d)
                    fields[0].insert(0, name)
                    combo = next(w for w in d.body.winfo_children() if isinstance(w, ttk.Combobox))
                    combo.current(1)
                    combo.event_generate("<<ComboboxSelected>>")
                    fields[3].insert(0, price)
                    submit(d, "위시 저장하기")
                self.assertEqual(len(store.products()), 2)
                app.update_idletasks()
                app.render_main()
                texts = [app.canvas.itemcget(i, "text") for i in app.canvas.find_all() if app.canvas.type(i) == "text"]
                self.assertIn("아직 150,000원 남았어요.", texts)

                app.transaction("set")
                d = dialog()
                entries(d)[0].delete(0, "end")
                entries(d)[0].insert(0, "300000")
                submit(d, "기록하기")
                self.assertEqual(store.balance(app.active), 300000)
                self.assertFalse(error.called, error.call_args)
                self.assertFalse(errors, errors)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
