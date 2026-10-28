"""Вкладка «Meta-файл RSI»: генерация meta.json для папки со спрайтами."""

from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from .. import rsi
from ..models import parse_number
from ..rsi import StateDef
from .dialogs import ModalDialog
from .widgets import PlaceholderEntry, Tooltip

DIRECTION_HINTS = {
    "1": "1 — без направлений",
    "4": "4 — юг, север, восток, запад",
    "8": "8 — все стороны, включая диагонали",
}


def _fmt(d: float) -> str:
    return str(int(d)) if float(d).is_integer() else repr(d)


def _delays_text(state: StateDef, limit: int = 40) -> str:
    if not state.delays:
        return "—"
    flat = {d for row in state.delays for d in row}
    if len(flat) == 1:
        text = f"{_fmt(next(iter(flat)))} сек × {state.frames}"
    elif len(state.delays) > 1 and any(r != state.delays[0] for r in state.delays):
        text = "разные для направлений"
    else:
        text = ", ".join(_fmt(d) for d in state.delays[0])
    return text if len(text) <= limit else text[: limit - 1] + "…"


class StateDialog(ModalDialog):
    """Создание / правка одного состояния (state)."""

    def __init__(self, master: tk.Widget, existing_names: List[str],
                 state: Optional[StateDef] = None) -> None:
        super().__init__(master, "Состояние" if state is None else f"Состояние «{state.name}»",
                         ok_text="Добавить" if state is None else "Сохранить")
        self.existing = set(existing_names)
        b = self.body
        b.columnconfigure(1, weight=1)

        ttk.Label(b, text="Название *").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        self.name_var = tk.StringVar()
        name = ttk.Entry(b, textvariable=self.name_var, width=34)
        name.grid(row=0, column=1, sticky="ew", pady=4)
        Tooltip(name, "Имя состояния = имя PNG-файла без расширения "
                      "(например, icon для icon.png).")

        ttk.Label(b, text="Направления").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        self.dir_var = tk.StringVar(value=DIRECTION_HINTS["1"])
        self.dir_box = ttk.Combobox(b, textvariable=self.dir_var, state="readonly",
                                    values=list(DIRECTION_HINTS.values()))
        self.dir_box.grid(row=1, column=1, sticky="ew", pady=4)

        self.anim_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(b, text="Анимированное (несколько кадров)", variable=self.anim_var,
                        command=self._toggle).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 2))

        self.anim_box = ttk.LabelFrame(b, text="Анимация", padding=8)
        self.anim_box.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.anim_box.columnconfigure(1, weight=1)
        ttk.Label(self.anim_box, text="Кадров").grid(row=0, column=0, sticky="w", pady=3, padx=(0, 10))
        self.frames_var = tk.StringVar(value="4")
        self.frames_sp = ttk.Spinbox(self.anim_box, from_=1, to=999, width=8, textvariable=self.frames_var)
        self.frames_sp.grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(self.anim_box, text="Задержка кадра, сек").grid(row=1, column=0, sticky="w", pady=3, padx=(0, 10))
        self.delay_var = tk.StringVar(value="0.1")
        self.delay_en = ttk.Entry(self.anim_box, textvariable=self.delay_var, width=10)
        self.delay_en.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(self.anim_box, text="Свои задержки\n(необязательно)", justify="left").grid(
            row=2, column=0, sticky="nw", pady=3, padx=(0, 10))
        self.manual = tk.Text(self.anim_box, height=4, width=34, borderwidth=1, relief="solid",
                              font=tkfont.nametofont("TkDefaultFont"))
        self.manual.grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(self.anim_box, justify="left", foreground="gray35", wraplength=380,
                  text="Если заполнить, «Кадров» и «Задержка» игнорируются. Значения через запятую; "
                       "одна строка = одно направление. Одна строка при нескольких направлениях "
                       "копируется на все.").grid(row=3, column=0, columnspan=2, sticky="w")

        if state is not None:
            self._load(state)
        self._toggle()
        name.focus_set()

    def _load(self, st: StateDef) -> None:
        self.name_var.set(st.name)
        self.dir_var.set(DIRECTION_HINTS.get(str(st.directions), DIRECTION_HINTS["1"]))
        if st.delays:
            self.anim_var.set(True)
            self.frames_var.set(str(st.frames))
            flat = {d for row in st.delays for d in row}
            if len(flat) == 1:
                self.delay_var.set(_fmt(next(iter(flat))))
            else:
                self.manual.insert("1.0", "\n".join(", ".join(_fmt(d) for d in row)
                                                    for row in st.delays))

    def _toggle(self) -> None:
        state = "normal" if self.anim_var.get() else "disabled"
        for w in (self.frames_sp, self.delay_en, self.manual):
            w.configure(state=state)

    def _directions(self) -> int:
        return int(self.dir_var.get().split()[0])

    def _build_state(self) -> StateDef:
        directions = self._directions()
        delays = None
        if self.anim_var.get():
            manual = self.manual.get("1.0", "end").strip()
            if manual:
                delays = rsi.normalize_delays(rsi.parse_delays_text(manual), directions)
            else:
                frames = parse_number(self.frames_var.get(), "int")
                if frames < 1:
                    raise ValueError("кадров должно быть не меньше 1")
                delay = parse_number(self.delay_var.get(), "float")
                delays = rsi.make_delays(frames, float(delay), directions)
        return StateDef(self.name_var.get().strip(), directions, delays)

    def validate(self) -> bool:
        try:
            state = self._build_state()
        except ValueError as exc:
            messagebox.showerror("Проверьте поля", str(exc), parent=self)
            return False
        errors = rsi.validate_state(state)
        if state.name in self.existing:
            errors.append(f"состояние «{state.name}» уже есть в списке")
        if errors:
            messagebox.showerror("Проверьте поля", "\n".join(errors), parent=self)
            return False
        return True

    def collect(self) -> StateDef:
        return self._build_state()


class RsiTab(ttk.Frame):
    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, padding=8)
        self.states: List[StateDef] = [StateDef("icon")]
        self._last_dir = os.path.expanduser("~")
        self._ready = False
        self._build_params()
        self._build_body()
        self._ready = True
        self._refresh_states()

    # ------------------------------------------------------------------ UI --

    def _build_params(self) -> None:
        box = ttk.LabelFrame(self, text="Параметры RSI", padding=8)
        box.pack(fill="x", pady=(0, 8))
        self.w_var, self.h_var = tk.StringVar(value="32"), tk.StringVar(value="32")
        ttk.Label(box, text="Разрешение (px):").grid(row=0, column=0, sticky="w")
        ttk.Label(box, text="Ширина").grid(row=0, column=1, padx=(10, 4))
        ttk.Spinbox(box, from_=1, to=4096, width=6, textvariable=self.w_var).grid(row=0, column=2)
        ttk.Label(box, text="Высота").grid(row=0, column=3, padx=(10, 4))
        ttk.Spinbox(box, from_=1, to=4096, width=6, textvariable=self.h_var).grid(row=0, column=4)
        ttk.Label(box, text="Лицензия").grid(row=0, column=5, padx=(24, 4))
        self.lic_var = tk.StringVar(value="CC-BY-SA-3.0")
        ttk.Combobox(box, textvariable=self.lic_var, values=rsi.COMMON_LICENSES, width=16).grid(
            row=0, column=6, sticky="w")
        ttk.Label(box, text="Авторство (copyright)").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.copy_entry = PlaceholderEntry(
            box, "Например: Нарисовано Иваном Ивановым для SS14", on_change=self._refresh)
        self.copy_entry.grid(row=1, column=1, columnspan=6, sticky="ew", pady=(8, 0), padx=(10, 0))
        box.columnconfigure(6, weight=1)
        for var in (self.w_var, self.h_var, self.lic_var):
            var.trace_add("write", lambda *a: self._refresh())

    def _build_body(self) -> None:
        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.LabelFrame(main, text="Состояния (states)", padding=6)
        right = ttk.LabelFrame(main, text="Результат (meta.json)", padding=6)
        main.add(left, weight=3)
        main.add(right, weight=2)

        cols = ("name", "dirs", "frames", "delays")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse", height=10)
        for col, title, width, anchor in (("name", "Название", 150, "w"), ("dirs", "Направл.", 70, "center"),
                                          ("frames", "Кадров", 60, "center"), ("delays", "Задержки", 170, "w")):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor=anchor)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.bind("<Double-Button-1>", lambda e: self._edit())
        self.tree.bind("<Delete>", lambda e: self._remove())

        row1 = ttk.Frame(left)
        row1.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        for text, cmd in (("Добавить…", self._add), ("Изменить…", self._edit), ("Дублировать", self._duplicate),
                          ("Убрать", self._remove), ("Вверх", lambda: self._move(-1)), ("Вниз", lambda: self._move(1))):
            ttk.Button(row1, text=text, command=cmd).pack(side="left", padx=(0, 4))
        row2 = ttk.Frame(left)
        row2.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        b1 = ttk.Button(row2, text="Состояния из PNG в папке…", command=self._scan_png)
        b1.pack(side="left", padx=(0, 6))
        Tooltip(b1, "Выберите папку .rsi: для каждого *.png будет добавлено состояние с таким же именем.")
        ttk.Button(row2, text="Открыть готовый meta.json…", command=self._open_meta).pack(side="left")

        frame = ttk.Frame(right)
        frame.pack(fill="both", expand=True)
        self.preview = tk.Text(frame, wrap="none", font=tkfont.nametofont("TkFixedFont"), borderwidth=1,
                               relief="solid", state="disabled", height=16, width=40)
        ysb = ttk.Scrollbar(frame, orient="vertical", command=self.preview.yview)
        xsb = ttk.Scrollbar(frame, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar()
        self.status = ttk.Label(right, textvariable=self.status_var, wraplength=400, justify="left")
        self.status.pack(fill="x", pady=(6, 4))
        bar = ttk.Frame(right)
        bar.pack(fill="x")
        ttk.Button(bar, text="Копировать JSON", command=self._copy).pack(side="left")
        ttk.Button(bar, text="Сохранить meta.json…", command=self._save).pack(side="right")

    # ----------------------------------------------------------- состояния ---

    def _refresh_states(self, select: Optional[int] = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, st in enumerate(self.states):
            self.tree.insert("", "end", iid=str(i),
                             values=(st.name, st.directions, st.frames, _delays_text(st)))
        if select is not None and 0 <= select < len(self.states):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))
        self._refresh()

    def _selected(self) -> Optional[int]:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _add(self) -> None:
        st = StateDialog(self, [s.name for s in self.states]).show()
        if st is not None:
            self.states.append(st)
            self._refresh_states(len(self.states) - 1)

    def _edit(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        others = [s.name for i, s in enumerate(self.states) if i != idx]
        st = StateDialog(self, others, self.states[idx]).show()
        if st is not None:
            self.states[idx] = st
            self._refresh_states(idx)

    def _duplicate(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        src = self.states[idx]
        names = {s.name for s in self.states}
        n = 2
        while f"{src.name}-{n}" in names:
            n += 1
        copy = StateDef(f"{src.name}-{n}", src.directions,
                        [list(r) for r in src.delays] if src.delays else None)
        self.states.insert(idx + 1, copy)
        self._refresh_states(idx + 1)

    def _remove(self) -> None:
        idx = self._selected()
        if idx is not None:
            del self.states[idx]
            self._refresh_states(min(idx, len(self.states) - 1))

    def _move(self, delta: int) -> None:
        idx = self._selected()
        if idx is None:
            return
        new = idx + delta
        if 0 <= new < len(self.states):
            self.states[idx], self.states[new] = self.states[new], self.states[idx]
            self._refresh_states(new)

    def _scan_png(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Папка .rsi со спрайтами",
                                         initialdir=self._last_dir)
        if not folder:
            return
        self._last_dir = folder
        names = rsi.scan_png_states(Path(folder))
        if not names:
            messagebox.showinfo("PNG не найдены", "В этой папке нет файлов *.png.", parent=self)
            return
        have = {s.name for s in self.states}
        new = [n for n in names if n not in have]
        for n in new:
            self.states.append(StateDef(n))
        self._refresh_states(len(self.states) - 1 if new else None)
        messagebox.showinfo(
            "Готово",
            f"Добавлено состояний: {len(new)} (пропущено уже существующих: {len(names) - len(new)}).\n\n"
            "Теперь для нужных состояний задайте направления и задержки "
            "(двойной клик по строке).", parent=self)

    def _open_meta(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Открыть meta.json", initialdir=self._last_dir,
                                          filetypes=[("meta.json", "*.json"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            w, h, lic, cr, states = rsi.parse_meta(text)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            messagebox.showerror("Не удалось открыть", f"Файл не похож на meta.json RSI:\n{exc}", parent=self)
            return
        self._last_dir = os.path.dirname(path)
        self._ready = False
        self.w_var.set(str(w))
        self.h_var.set(str(h))
        self.lic_var.set(lic)
        self.copy_entry.set_text(cr)
        self.states = states
        self._ready = True
        self._refresh_states(0 if states else None)

    # ------------------------------------------------------------ результат --

    def _size(self):
        try:
            return int(self.w_var.get()), int(self.h_var.get()), None
        except ValueError:
            return 32, 32, "размер спрайта должен быть целым числом"

    def _meta_text(self):
        w, h, size_err = self._size()
        errors = [size_err] if size_err else []
        errors += rsi.validate_meta(w, h, self.states)
        meta = rsi.build_meta(w, h, self.lic_var.get(), self.copy_entry.get_text(), self.states)
        return rsi.meta_to_json(meta), errors

    def _refresh(self) -> None:
        if not self._ready:
            return
        text, errors = self._meta_text()
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")
        if errors:
            more = f"  (и ещё {len(errors) - 1})" if len(errors) > 1 else ""
            self.status_var.set(f"Внимание: {errors[0]}{more}")
            self.status.configure(foreground="#b00020")
        else:
            self.status_var.set("Готово: положите meta.json в папку со спрайтами (.rsi)")
            self.status.configure(foreground="#1b7a2f")

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.preview.get("1.0", "end-1c"))
        self.status_var.set("Скопировано в буфер обмена")
        self.status.configure(foreground="#1b7a2f")

    def _save(self) -> None:
        text, errors = self._meta_text()
        if errors:
            messagebox.showerror("Нельзя сохранить", "\n".join(errors), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Сохранить meta.json (в папку .rsi)", initialfile="meta.json",
            initialdir=self._last_dir, defaultextension=".json", filetypes=[("meta.json", "*.json")])
        if not path:
            return
        try:
            rsi.save_meta(Path(path), text)
        except OSError as exc:
            messagebox.showerror("Ошибка записи", str(exc), parent=self)
            return
        self._last_dir = os.path.dirname(path)
        self.status_var.set(f"Сохранено: {path}")
        self.status.configure(foreground="#1b7a2f")
        if os.path.basename(path) != "meta.json":
            messagebox.showwarning("Имя файла",
                                   "Для RSI файл должен называться ровно meta.json — "
                                   "не забудьте переименовать.", parent=self)
