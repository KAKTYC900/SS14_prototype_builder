"""Модальные диалоги."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from ..models import FieldDef
from .widgets import FieldForm, ScrollableFrame


class ModalDialog(tk.Toplevel):
    """Базовый модальный диалог с кнопками «ОК» / «Отмена».

    Наследники наполняют ``self.body`` и переопределяют ``validate()`` / ``collect()``.
    """

    def __init__(self, master: tk.Widget, title: str, ok_text: str = "ОК") -> None:
        super().__init__(master)
        self._parent_top = master.winfo_toplevel()
        self._parent_was_modal = bool(getattr(self._parent_top, "_is_modal_dialog", False))
        self._is_modal_dialog = True
        self.title(title)
        self.transient(self._parent_top)
        self.result: Any = None
        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill="both", expand=True)
        bar = ttk.Frame(self, padding=(12, 0, 12, 12))
        bar.pack(fill="x")
        ttk.Button(bar, text="Отмена", command=self.cancel).pack(side="right")
        ttk.Button(bar, text=ok_text, command=self.ok).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<Return>", self._on_return)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    # -- переопределяется в наследниках --------------------------------------
    def validate(self) -> bool:
        return True

    def collect(self) -> Any:
        return True

    # ------------------------------------------------------------------------
    def _on_return(self, event) -> Optional[str]:
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Treeview, ttk.Button)):
            return None
        self.ok()
        return "break"

    def ok(self) -> None:
        if self.validate():
            self.result = self.collect()
            self._close()

    def cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if self._parent_was_modal:
            try:
                self._parent_top.grab_set()
            except tk.TclError:
                pass

    def show(self) -> Any:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        px, py = self._parent_top.winfo_rootx(), self._parent_top.winfo_rooty()
        pw, ph = self._parent_top.winfo_width(), self._parent_top.winfo_height()
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 3)
        self.geometry(f"+{x}+{y}")
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()
        self.wait_window(self)
        return self.result


class FormDialog(ModalDialog):
    """Диалог с формой по списку полей. Результат — dict значений или None."""

    def __init__(self, master: tk.Widget, title: str, fields: List[FieldDef],
                 description: str = "", initial: Optional[Dict[str, Any]] = None,
                 ok_text: str = "ОК") -> None:
        super().__init__(master, title, ok_text)
        if description:
            ttk.Label(self.body, text=description, wraplength=520, justify="left").pack(
                fill="x", pady=(0, 10))
        screen_h = self.winfo_screenheight()
        self._scroll = ScrollableFrame(self.body)
        self._scroll.pack(fill="both", expand=True)
        self.form = FieldForm(self._scroll.inner, fields)
        self.form.pack(fill="both", expand=True, padx=(0, 8))
        if initial:
            self.form.set_values(initial)
        self._scroll.fit(max_height=int(screen_h * 0.62))
        self.minsize(460, 0)
        self.form.focus_first()

    def validate(self) -> bool:
        _, errors = self.form.collect()
        if errors:
            messagebox.showerror("Проверьте поля", "\n".join(errors), parent=self)
            return False
        return True

    def collect(self) -> Dict[str, Any]:
        values, _ = self.form.collect()
        return values
