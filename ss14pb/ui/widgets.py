"""Виджеты форм: по описанию поля (FieldDef) строится нужный элемент ввода.

Каждый «полевой» виджет умеет:
    get()  -> значение нужного типа или None, если поле не заполнено
              (при неверном вводе бросает ValueError с понятным текстом);
    set(v) -> заполнить из значения.
"""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..models import FieldDef, parse_number, parse_vector2

UNSET = "— не задано —"
BOOL_UNSET = "(по умолчанию)"
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


# ---------------------------------------------------------------------------
# Вспомогательные виджеты
# ---------------------------------------------------------------------------

class Tooltip:
    """Всплывающая подсказка при наведении."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 450, wrap: int = 380) -> None:
        self.widget, self.text, self.delay, self.wrap = widget, text, delay, wrap
        self._after: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self.text, justify="left", background="#ffffe1",
                 foreground="#000000", relief="solid", borderwidth=1, padx=6, pady=4,
                 wraplength=self.wrap).pack()

    def _hide(self, _e=None) -> None:
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


class ScrollableFrame(ttk.Frame):
    """Фрейм с вертикальной прокруткой; контент кладётся в ``.inner``."""

    def __init__(self, master: tk.Widget, **kw) -> None:
        super().__init__(master, **kw)
        bg = ttk.Style().lookup("TFrame", "background") or self.winfo_toplevel().cget("background")
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=bg)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w in (self, self.canvas, self.inner):
            w.bind("<Enter>", self._bind_wheel, add="+")
            w.bind("<Leave>", self._unbind_wheel, add="+")

    def _on_inner(self, _e=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def fit(self, max_height: int) -> None:
        """Подогнать размер canvas под содержимое (но не выше max_height)."""
        self.update_idletasks()
        self.canvas.configure(width=self.inner.winfo_reqwidth(),
                              height=min(self.inner.winfo_reqheight(), max_height))

    def _bind_wheel(self, _e=None) -> None:
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", self._on_wheel)
        self.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self, e=None) -> None:
        if e is not None:
            w = self.winfo_containing(e.x_root, e.y_root)
            if w is not None and str(w).startswith(str(self)):
                return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(seq)

    def _on_wheel(self, e) -> None:
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            return
        if getattr(e, "num", None) == 4 or getattr(e, "delta", 0) > 0:
            self.canvas.yview_scroll(-2, "units")
        else:
            self.canvas.yview_scroll(2, "units")


class PlaceholderEntry(ttk.Entry):
    """ttk.Entry с серой подсказкой-примером, пока поле пустое."""

    def __init__(self, master: tk.Widget, placeholder: str = "",
                 on_change: Optional[Callable[[], None]] = None, **kw) -> None:
        self._var = tk.StringVar()
        super().__init__(master, textvariable=self._var, **kw)
        self._placeholder = placeholder
        self._on_change = on_change
        self._showing = False
        self._normal_fg = ttk.Style().lookup("TEntry", "foreground") or "black"
        self._var.trace_add("write", self._traced)
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        self._maybe_show()

    def _traced(self, *_a) -> None:
        if not self._showing and self._on_change:
            self._on_change()

    def _maybe_show(self) -> None:
        if self._placeholder and not self._var.get() and not self._showing:
            self._showing = True
            self._var.set(self._placeholder)
            self.configure(foreground="gray50")

    def _focus_in(self, _e=None) -> None:
        if self._showing:
            self._showing = False
            self._var.set("")
            self.configure(foreground=self._normal_fg)

    def _focus_out(self, _e=None) -> None:
        self._maybe_show()

    def get_text(self) -> str:
        return "" if self._showing else self._var.get()

    def set_text(self, text: str) -> None:
        if self._showing:
            self._showing = False
            self.configure(foreground=self._normal_fg)
        self._var.set(text)
        if not text and self.focus_get() is not self:
            self._maybe_show()


def _block_wheel(widget: tk.Widget) -> None:
    """Колесо мыши над combobox не должно менять значение при прокрутке формы."""
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        widget.bind(seq, lambda e: "break")


# ---------------------------------------------------------------------------
# Полевые виджеты
# ---------------------------------------------------------------------------

class BaseField:
    spans_row = False   # True — виджет занимает обе колонки (без подписи слева)
    multiline = False   # True — подпись выравнивается по верху

    def __init__(self, master: tk.Widget, fdef: FieldDef,
                 on_change: Optional[Callable[[], None]] = None) -> None:
        self.fdef = fdef
        self._on_change = on_change or (lambda: None)
        self.widget: tk.Widget = self._build(master)

    def changed(self, *_a) -> None:
        self._on_change()

    def _build(self, master: tk.Widget) -> tk.Widget:  # pragma: no cover
        raise NotImplementedError

    def get(self) -> Any:  # pragma: no cover
        raise NotImplementedError

    def set(self, value: Any) -> None:  # pragma: no cover
        raise NotImplementedError


class StringField(BaseField):
    def _build(self, master):
        self.entry = PlaceholderEntry(master, self.fdef.placeholder, on_change=self.changed)
        return self.entry

    def get(self):
        text = self.entry.get_text().strip()
        return text or None

    def set(self, value):
        self.entry.set_text("" if value is None else str(value))


class TextField(BaseField):
    multiline = True

    def _build(self, master):
        self.text = tk.Text(master, height=4, width=30, wrap="word", undo=True,
                            font=tkfont.nametofont("TkDefaultFont"), borderwidth=1, relief="solid")
        for seq in ("<KeyRelease>", "<<Paste>>", "<<Cut>>", "<<Undo>>", "<<Redo>>"):
            self.text.bind(seq, lambda e: self.text.after_idle(self.changed), add="+")
        self.text.bind("<Tab>", lambda e: (self.text.tk_focusNext().focus_set(), "break")[1])
        self.text.bind("<Shift-Tab>", lambda e: (self.text.tk_focusPrev().focus_set(), "break")[1])
        return self.text

    def get(self):
        value = self.text.get("1.0", "end-1c").strip()
        return value or None

    def set(self, value):
        self.text.delete("1.0", "end")
        if value:
            self.text.insert("1.0", str(value))
        self.changed()


class NumberField(BaseField):
    def _build(self, master):
        self.entry = PlaceholderEntry(master, self.fdef.placeholder, on_change=self.changed)
        return self.entry

    def get(self):
        text = self.entry.get_text().strip()
        if not text:
            return None
        return parse_number(text, self.fdef.type)

    def set(self, value):
        self.entry.set_text("" if value is None else str(value))


class BoolField(BaseField):
    def _build(self, master):
        self.var = tk.StringVar(value=BOOL_UNSET)
        cb = ttk.Combobox(master, textvariable=self.var, state="readonly", width=18,
                          values=[BOOL_UNSET, "true", "false"])
        cb.bind("<<ComboboxSelected>>", self.changed)
        _block_wheel(cb)
        return cb

    def get(self):
        v = self.var.get()
        return True if v == "true" else False if v == "false" else None

    def set(self, value):
        self.var.set(BOOL_UNSET if value is None else ("true" if value else "false"))
        self.changed()


class EnumField(BaseField):
    def _build(self, master):
        self.var = tk.StringVar(value=UNSET)
        cb = ttk.Combobox(master, textvariable=self.var, width=28,
                          state="normal" if self.fdef.editable else "readonly",
                          values=[UNSET] + list(self.fdef.options))
        cb.bind("<<ComboboxSelected>>", self.changed)
        self.var.trace_add("write", self.changed)
        _block_wheel(cb)
        return cb

    def get(self):
        v = self.var.get().strip()
        return None if v in ("", UNSET) else v

    def set(self, value):
        self.var.set(UNSET if value is None else str(value))


class ColorField(BaseField):
    def _build(self, master):
        frame = ttk.Frame(master)
        self.entry = PlaceholderEntry(frame, "#RRGGBB", on_change=self._entry_changed, width=14)
        self.entry.pack(side="left")
        self.swatch = tk.Label(frame, width=3, relief="solid", borderwidth=1)
        self.swatch.pack(side="left", padx=6)
        ttk.Button(frame, text="Выбрать…", command=self._pick).pack(side="left")
        self._default_swatch = self.swatch.cget("background")
        return frame

    def _entry_changed(self) -> None:
        text = self.entry.get_text().strip()
        self.swatch.configure(background=text if HEX_RE.match(text) else self._default_swatch)
        self.changed()

    def _pick(self) -> None:
        current = self.entry.get_text().strip()
        rgb, hexval = colorchooser.askcolor(color=current if HEX_RE.match(current) else None,
                                            parent=self.widget, title="Выбор цвета")
        if hexval:
            self.entry.set_text(hexval.upper())

    def get(self):
        text = self.entry.get_text().strip()
        if not text:
            return None
        if text.startswith("#") and not HEX_RE.match(text):
            raise ValueError("цвет должен быть вида #RRGGBB (или #RRGGBBAA)")
        return text

    def set(self, value):
        self.entry.set_text("" if value is None else str(value))


class Vector2Field(BaseField):
    def _build(self, master):
        frame = ttk.Frame(master)
        ttk.Label(frame, text="X").pack(side="left")
        self.x = ttk.Entry(frame, width=9)
        self.x.pack(side="left", padx=(2, 10))
        ttk.Label(frame, text="Y").pack(side="left")
        self.y = ttk.Entry(frame, width=9)
        self.y.pack(side="left", padx=2)
        for e in (self.x, self.y):
            e.bind("<KeyRelease>", self.changed)
        return frame

    def get(self):
        return parse_vector2(self.x.get(), self.y.get())

    def set(self, value):
        self.x.delete(0, "end")
        self.y.delete(0, "end")
        if value:
            parts = str(value).split(",")
            if len(parts) == 2:
                self.x.insert(0, parts[0].strip())
                self.y.insert(0, parts[1].strip())
        self.changed()


class ListField(BaseField):
    multiline = True

    def _build(self, master):
        frame = ttk.Frame(master)
        frame.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(frame, height=4, exportselection=False, activestyle="none")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        ttk.Button(frame, text="Убрать", width=9, command=self._remove).grid(
            row=0, column=2, sticky="n", padx=(6, 0))
        self.entry = ttk.Entry(frame)
        self.entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(frame, text="Добавить", width=9, command=self._add).grid(
            row=1, column=2, padx=(6, 0), pady=(4, 0))
        self.entry.bind("<Return>", lambda e: (self._add(), "break")[1])
        return frame

    def _add(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        if self.fdef.item_type in ("int", "float"):
            try:
                parse_number(text, self.fdef.item_type)
            except ValueError as exc:
                from tkinter import messagebox
                messagebox.showerror("Неверное значение", str(exc), parent=self.widget)
                return
        self.listbox.insert("end", text)
        self.entry.delete(0, "end")
        self.changed()

    def _remove(self) -> None:
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
        self.changed()

    def get(self):
        items = list(self.listbox.get(0, "end"))
        if not items:
            return None
        if self.fdef.item_type in ("int", "float"):
            return [parse_number(i, self.fdef.item_type) for i in items]
        return items

    def set(self, value):
        self.listbox.delete(0, "end")
        for item in value or []:
            self.listbox.insert("end", str(item))
        self.changed()


class MapField(BaseField):
    multiline = True

    def _build(self, master):
        frame = ttk.Frame(master)
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=("k", "v"), show="headings", height=4,
                                 selectmode="browse")
        self.tree.heading("k", text="Ключ")
        self.tree.heading("v", text="Значение")
        self.tree.column("k", width=140, anchor="w")
        self.tree.column("v", width=90, anchor="w")
        self.tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=3, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._load_selected)
        self.key = PlaceholderEntry(frame, "ключ")
        self.val = PlaceholderEntry(frame, "значение", width=10)
        self.key.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.val.grid(row=1, column=1, padx=(6, 0), pady=(4, 0))
        ttk.Button(frame, text="Добавить / обновить", command=self._add).grid(
            row=1, column=2, padx=(6, 0), pady=(4, 0))
        ttk.Button(frame, text="Убрать выбранное", command=self._remove).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        for e in (self.key, self.val):
            e.bind("<Return>", lambda ev: (self._add(), "break")[1])
        return frame

    def _load_selected(self, _e=None) -> None:
        sel = self.tree.selection()
        if sel:
            k, v = self.tree.item(sel[0], "values")
            self.key.set_text(str(k))
            self.val.set_text(str(v))

    def _add(self) -> None:
        k, v = self.key.get_text().strip(), self.val.get_text().strip()
        if not k:
            return
        if self.fdef.value_type in ("int", "float"):
            try:
                v = str(parse_number(v, self.fdef.value_type))
            except ValueError as exc:
                from tkinter import messagebox
                messagebox.showerror("Неверное значение", str(exc), parent=self.widget)
                return
        for iid in self.tree.get_children():
            if self.tree.item(iid, "values")[0] == k:
                self.tree.item(iid, values=(k, v))
                break
        else:
            self.tree.insert("", "end", values=(k, v))
        self.key.set_text("")
        self.val.set_text("")
        self.changed()

    def _remove(self) -> None:
        for iid in self.tree.selection():
            self.tree.delete(iid)
        self.changed()

    def get(self):
        out: Dict[str, Any] = {}
        for iid in self.tree.get_children():
            k, v = self.tree.item(iid, "values")
            k = str(k)
            if self.fdef.value_type in ("int", "float"):
                out[k] = parse_number(str(v), self.fdef.value_type)
            else:
                out[k] = str(v)
        return out or None

    def set(self, value):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for k, v in (value or {}).items():
            self.tree.insert("", "end", values=(k, v))
        self.changed()


class GroupField(BaseField):
    spans_row = True

    def _build(self, master):
        box = ttk.LabelFrame(master, text=self.fdef.title, padding=8)
        self.form = FieldForm(box, self.fdef.fields, on_change=self.changed)
        self.form.pack(fill="both", expand=True)
        if self.fdef.help:
            Tooltip(box, self.fdef.help)
        return box

    def get(self):
        values, errors = self.form.collect()
        if errors:
            raise ValueError("; ".join(errors))
        return values or None

    def set(self, value):
        self.form.set_values(value or {})


def _summary(item: Dict[str, Any], label_key: str, limit: int = 70) -> str:
    parts = []
    if label_key and label_key in item:
        parts.append(str(item[label_key]))
    rest = [f"{k}={_short(v)}" for k, v in item.items() if k != label_key]
    text = "  ".join(parts + ([", ".join(rest)] if rest else [])) or "(пусто)"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _short(v: Any) -> str:
    if isinstance(v, (list, dict)):
        return "[…]" if isinstance(v, list) else "{…}"
    return str(v)


class ObjListField(BaseField):
    multiline = True

    def _build(self, master):
        self.items: List[Dict[str, Any]] = []
        frame = ttk.Frame(master)
        frame.columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(frame, height=5, exportselection=False, activestyle="none")
        self.listbox.grid(row=0, column=0, rowspan=6, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", lambda e: self._edit())
        btns = [("Добавить…", self._add), ("Изменить…", self._edit), ("Убрать", self._remove),
                ("Вверх", lambda: self._move(-1)), ("Вниз", lambda: self._move(1))]
        for i, (text, cmd) in enumerate(btns):
            ttk.Button(frame, text=text, command=cmd, width=11).grid(
                row=i, column=1, padx=(6, 0), pady=1, sticky="n")
        return frame

    def _refresh(self, select: Optional[int] = None) -> None:
        self.listbox.delete(0, "end")
        for i, item in enumerate(self.items, 1):
            self.listbox.insert("end", f"{i}. {_summary(item, self.fdef.item_label_key)}")
        if select is not None and 0 <= select < len(self.items):
            self.listbox.selection_set(select)
        self.changed()

    def _selected(self) -> Optional[int]:
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _open(self, title: str, initial: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        from .dialogs import FormDialog
        return FormDialog(self.widget, title, self.fdef.item_fields, initial=initial).show()

    def _add(self) -> None:
        result = self._open(f"{self.fdef.title}: новый элемент", None)
        if result is not None:
            self.items.append(result)
            self._refresh(len(self.items) - 1)

    def _edit(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        result = self._open(f"{self.fdef.title}: элемент {idx + 1}", self.items[idx])
        if result is not None:
            self.items[idx] = result
            self._refresh(idx)

    def _remove(self) -> None:
        idx = self._selected()
        if idx is not None:
            del self.items[idx]
            self._refresh(min(idx, len(self.items) - 1))

    def _move(self, delta: int) -> None:
        idx = self._selected()
        if idx is None:
            return
        new = idx + delta
        if 0 <= new < len(self.items):
            self.items[idx], self.items[new] = self.items[new], self.items[idx]
            self._refresh(new)

    def get(self):
        return [dict(i) for i in self.items] or None

    def set(self, value):
        self.items = [dict(i) for i in (value or [])]
        self._refresh()


FIELD_CLASSES = {
    "string": StringField,
    "text": TextField,
    "int": NumberField,
    "float": NumberField,
    "bool": BoolField,
    "enum": EnumField,
    "color": ColorField,
    "vector2": Vector2Field,
    "list": ListField,
    "map": MapField,
    "group": GroupField,
    "objlist": ObjListField,
}


# ---------------------------------------------------------------------------
# Форма из списка полей
# ---------------------------------------------------------------------------

class FieldForm(ttk.Frame):
    """Собирает форму по списку FieldDef."""

    def __init__(self, master: tk.Widget, fields: List[FieldDef],
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(master)
        self.fdefs = fields
        self.on_change = on_change
        self.fields: Dict[str, BaseField] = {}
        self.columnconfigure(1, weight=1)
        for row, fdef in enumerate(fields):
            cls = FIELD_CLASSES[fdef.type]
            field = cls(self, fdef, on_change)
            self.fields[fdef.key] = field
            if field.spans_row:
                field.widget.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
                continue
            text = fdef.title + (" *" if fdef.required else "") + (" (?)" if fdef.help or fdef.placeholder else "")
            label = ttk.Label(self, text=text, justify="left", wraplength=200)
            label.grid(row=row, column=0, sticky="nw" if field.multiline else "w",
                       padx=(0, 10), pady=3)
            field.widget.grid(row=row, column=1, sticky="ew", pady=3)
            tip = fdef.help
            if fdef.placeholder and fdef.type in ("string", "int", "float"):
                tip = (tip + "\n" if tip else "") + f"Пример: {fdef.placeholder}"
            if tip:
                Tooltip(label, tip)

    def collect(self) -> Tuple[Dict[str, Any], List[str]]:
        """Возвращает (значения заполненных полей, список ошибок)."""
        values: Dict[str, Any] = {}
        errors: List[str] = []
        for fdef in self.fdefs:
            field = self.fields[fdef.key]
            try:
                value = field.get()
            except ValueError as exc:
                errors.append(f"{fdef.title}: {exc}")
                continue
            if value is None:
                if fdef.required:
                    errors.append(f"Заполните поле «{fdef.title}»")
                continue
            values[fdef.key] = value
        return values, errors

    def set_values(self, data: Dict[str, Any]) -> None:
        for key, field in self.fields.items():
            if key in data:
                field.set(data[key])

    def focus_first(self) -> None:
        for field in self.fields.values():
            target = getattr(field, "entry", None) or getattr(field, "text", None)
            if target is not None:
                target.focus_set()
                return
