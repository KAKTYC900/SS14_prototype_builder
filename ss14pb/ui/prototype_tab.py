"""Вкладка «Прототип»: выбор типа, основные поля, компоненты, предпросмотр YAML."""

from __future__ import annotations

import os
import re
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from ..builder import render_yaml, save_yaml
from ..models import ComponentDef, ComponentInstance, PrototypeTypeDef
from ..registry import Registry
from .dialogs import FormDialog
from .widgets import FieldForm, ScrollableFrame


def _short(v: Any) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_short(i) for i in v[:3]) + ("…" if len(v) > 3 else "") + "]"
    if isinstance(v, dict):
        return "{…}"
    return str(v)


def _comp_summary(comp: ComponentInstance, limit: int = 64) -> str:
    if not comp.data:
        return comp.name
    body = ", ".join(f"{k}={_short(v)}" for k, v in comp.data.items())
    text = f"{comp.name} — {body}"
    return text if len(text) <= limit else text[: limit - 1] + "…"


class PrototypeTab(ttk.Frame):
    def __init__(self, master: tk.Widget, registry: Registry) -> None:
        super().__init__(master, padding=8)
        self.reg = registry
        self.components: List[ComponentInstance] = []
        self.ptype: Optional[PrototypeTypeDef] = None
        self.form: Optional[FieldForm] = None
        self._ready = False
        self._last_dir = os.path.expanduser("~")
        self._type_by_title: Dict[str, PrototypeTypeDef] = {}

        self._build_header()
        self._build_body()
        self._fill_types()
        self._ready = True
        self._select_type(next(iter(self.reg.prototype_types.values()), None))

    # ------------------------------------------------------------------ UI --

    def _build_header(self) -> None:
        head = ttk.Frame(self)
        head.pack(fill="x", pady=(0, 8))
        ttk.Label(head, text="Тип прототипа:", font=tkfont.nametofont("TkDefaultFont")).pack(side="left")
        self.type_var = tk.StringVar()
        self.type_box = ttk.Combobox(head, textvariable=self.type_var, state="readonly", width=38)
        self.type_box.pack(side="left", padx=8)
        self.type_box.bind("<<ComboboxSelected>>", self._on_type_selected)
        self.type_desc = ttk.Label(head, text="", foreground="gray35", wraplength=620, justify="left")
        self.type_desc.pack(side="left", padx=8)

    def _build_body(self) -> None:
        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)
        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=3)
        main.add(right, weight=2)

        # левая часть: форма + компоненты
        self.left_pane = ttk.PanedWindow(left, orient="vertical")
        self.left_pane.pack(fill="both", expand=True)
        self.form_box = ttk.LabelFrame(self.left_pane, text="Основные данные", padding=6)
        self.scroll = ScrollableFrame(self.form_box)
        self.scroll.pack(fill="both", expand=True)
        self.left_pane.add(self.form_box, weight=1)

        self.comp_box = ttk.LabelFrame(self.left_pane, text="Компоненты", padding=6)
        self._build_components(self.comp_box)
        self.left_pane.add(self.comp_box, weight=2)
        self._comp_visible = True

        # правая часть: предпросмотр
        self._build_preview(right)

    def _build_components(self, box: ttk.LabelFrame) -> None:
        box.columnconfigure(0, weight=1, uniform="c")
        box.columnconfigure(1, weight=1, uniform="c")
        box.rowconfigure(1, weight=1)

        # доступные
        top = ttk.Frame(box)
        top.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Label(top, text="Доступные (по категориям)").pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(top, textvariable=self.search_var, width=16)
        search.pack(side="right")
        ttk.Label(top, text="Поиск:").pack(side="right", padx=(0, 4))
        self.search_var.trace_add("write", lambda *a: self._fill_tree())

        tree_frame = ttk.Frame(box)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=4)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse", height=8)
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-Button-1>", self._on_tree_double)
        self.tree.bind("<Return>", lambda e: self._add_selected())

        self.desc_var = tk.StringVar(value="Выберите компонент, чтобы увидеть описание.")
        ttk.Label(box, textvariable=self.desc_var, wraplength=300, justify="left",
                  foreground="gray30").grid(row=2, column=0, sticky="nw", padx=(0, 6))
        self.add_btn = ttk.Button(box, text="Добавить →", command=self._add_selected)
        self.add_btn.grid(row=3, column=0, sticky="w", pady=(6, 0))

        # добавленные
        ttk.Label(box, text="В прототипе").grid(row=0, column=1, sticky="w")
        list_frame = ttk.Frame(box)
        list_frame.grid(row=1, column=1, sticky="nsew", pady=4)
        self.comp_list = tk.Listbox(list_frame, exportselection=False, activestyle="none", height=8)
        lsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.comp_list.yview)
        self.comp_list.configure(yscrollcommand=lsb.set)
        self.comp_list.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        self.comp_list.bind("<Double-Button-1>", lambda e: self._edit_selected())
        self.comp_list.bind("<Delete>", lambda e: self._remove_selected())
        btns = ttk.Frame(box)
        btns.grid(row=3, column=1, sticky="w", pady=(6, 0))
        for text, cmd in (("Изменить…", self._edit_selected), ("Убрать", self._remove_selected),
                          ("Вверх", lambda: self._move(-1)), ("Вниз", lambda: self._move(1))):
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 4))

    def _build_preview(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="Результат (YAML)", padding=6)
        box.pack(fill="both", expand=True, padx=(8, 0))
        frame = ttk.Frame(box)
        frame.pack(fill="both", expand=True)
        self.preview = tk.Text(frame, wrap="none", font=tkfont.nametofont("TkFixedFont"),
                               borderwidth=1, relief="solid", state="disabled", height=20, width=44)
        ysb = ttk.Scrollbar(frame, orient="vertical", command=self.preview.yview)
        xsb = ttk.Scrollbar(frame, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar()
        self.status = ttk.Label(box, textvariable=self.status_var, wraplength=420, justify="left")
        self.status.pack(fill="x", pady=(6, 4))
        bar = ttk.Frame(box)
        bar.pack(fill="x")
        ttk.Button(bar, text="Копировать YAML", command=self._copy).pack(side="left")
        ttk.Button(bar, text="Сохранить в файл…", command=self._save).pack(side="right")

    # --------------------------------------------------------------- типы ---

    def _fill_types(self) -> None:
        self._type_by_title = {t.title: t for t in self.reg.prototype_types.values()}
        self.type_box.configure(values=list(self._type_by_title))

    def _on_type_selected(self, _e=None) -> None:
        new = self._type_by_title.get(self.type_var.get())
        if new is None or new is self.ptype:
            return
        if self.components and not new.supports_components:
            if not messagebox.askyesno(
                    "Сменить тип?",
                    f"У типа «{new.type}» нет компонентов — добавленные компоненты "
                    f"({len(self.components)}) будут удалены. Продолжить?", parent=self):
                if self.ptype:
                    self.type_var.set(self.ptype.title)
                return
        self._select_type(new)

    def _select_type(self, new: Optional[PrototypeTypeDef]) -> None:
        if new is None:
            return
        old_values: Dict[str, Any] = {}
        if self.form is not None:
            old_values, _ = self.form.collect()
        self.ptype = new
        self.type_var.set(new.title)
        self.type_desc.configure(text=new.description)
        if not new.supports_components:
            self.components.clear()
        self._build_form(old_values)
        self._set_components_visible(new.supports_components)
        self._fill_tree()
        self._refresh_comp_list()
        self._refresh()

    def _build_form(self, values: Dict[str, Any]) -> None:
        was_ready, self._ready = self._ready, False
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self.form = FieldForm(self.scroll.inner, self.ptype.fields, on_change=self._refresh)
        self.form.pack(fill="both", expand=True, padx=(0, 8))
        self.form.set_values(values)
        self.scroll.canvas.yview_moveto(0)
        self._ready = was_ready
        self.form.focus_first()

    def _set_components_visible(self, visible: bool) -> None:
        if visible and not self._comp_visible:
            self.left_pane.add(self.comp_box, weight=2)
        elif not visible and self._comp_visible:
            self.left_pane.forget(self.comp_box)
        self._comp_visible = visible

    # ------------------------------------------------------ дерево списка ---

    def _fill_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        query = self.search_var.get()
        added = {c.name for c in self.components}
        found = {c.name for c in self.reg.search(query)}
        for cat, comps in self.reg.components_by_category().items():
            shown = [c for c in comps if c.name in found]
            if not shown:
                continue
            cat_id = self.tree.insert("", "end", iid=f"cat:{cat}", text=f"{cat}  ({len(shown)})",
                                      open=True)
            for comp in shown:
                mark = "   [добавлен]" if comp.name in added else ""
                self.tree.insert(cat_id, "end", iid=f"comp:{comp.name}", text=comp.name + mark)

    def _selected_def(self) -> Optional[ComponentDef]:
        sel = self.tree.selection()
        if sel and sel[0].startswith("comp:"):
            return self.reg.components.get(sel[0][5:])
        return None

    def _on_tree_select(self, _e=None) -> None:
        cdef = self._selected_def()
        if cdef is None:
            sel = self.tree.selection()
            self.desc_var.set("Раскройте категорию и выберите компонент." if sel else
                              "Выберите компонент, чтобы увидеть описание.")
            return
        n = len(cdef.fields)
        params = f"Параметров: {n}." if n else "Параметров нет — добавляется сразу."
        origin = "  (свой)" if cdef.origin == "custom" else ""
        self.desc_var.set(f"{cdef.name}{origin}\n{cdef.description}\n{params}")

    def _on_tree_double(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid and iid.startswith("comp:"):
            self.tree.selection_set(iid)
            self._add_selected()

    # ----------------------------------------------------- работа с компонентами

    def _add_selected(self) -> None:
        cdef = self._selected_def()
        if cdef is None:
            messagebox.showinfo("Компонент не выбран",
                                "Выберите компонент в списке слева.", parent=self)
            return
        self.add_component(cdef)

    def add_component(self, cdef: ComponentDef) -> None:
        for i, comp in enumerate(self.components):
            if comp.name == cdef.name:
                messagebox.showinfo("Компонент уже добавлен",
                                    f"{cdef.name} уже есть в прототипе — открываю для изменения.",
                                    parent=self)
                self._edit_index(i)
                return
        if cdef.fields:
            data = FormDialog(self, f"Компонент {cdef.name}", cdef.fields,
                              description=cdef.description, ok_text="Добавить").show()
            if data is None:
                return
        else:
            data = {}
        self.components.append(ComponentInstance(cdef.name, data))
        self._components_changed(select=len(self.components) - 1)

    def _selected_index(self) -> Optional[int]:
        sel = self.comp_list.curselection()
        return sel[0] if sel else None

    def _edit_selected(self) -> None:
        idx = self._selected_index()
        if idx is not None:
            self._edit_index(idx)

    def _edit_index(self, idx: int) -> None:
        comp = self.components[idx]
        cdef = self.reg.components.get(comp.name)
        if cdef is None:
            messagebox.showerror("Нет описания",
                                 f"Описание компонента {comp.name} не найдено в списках.", parent=self)
            return
        if not cdef.fields:
            messagebox.showinfo("Нет параметров", f"У {comp.name} нет параметров для изменения.",
                                parent=self)
            return
        data = FormDialog(self, f"Компонент {comp.name}", cdef.fields, description=cdef.description,
                          initial=comp.data, ok_text="Сохранить").show()
        if data is not None:
            comp.data = data
            self._components_changed(select=idx)

    def _remove_selected(self) -> None:
        idx = self._selected_index()
        if idx is not None:
            del self.components[idx]
            self._components_changed(select=min(idx, len(self.components) - 1))

    def _move(self, delta: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        new = idx + delta
        if 0 <= new < len(self.components):
            self.components[idx], self.components[new] = self.components[new], self.components[idx]
            self._components_changed(select=new)

    def _components_changed(self, select: Optional[int] = None) -> None:
        self._refresh_comp_list(select)
        self._fill_tree()
        self._refresh()

    def _refresh_comp_list(self, select: Optional[int] = None) -> None:
        self.comp_list.delete(0, "end")
        for comp in self.components:
            self.comp_list.insert("end", _comp_summary(comp))
        if select is not None and 0 <= select < len(self.components):
            self.comp_list.selection_set(select)
            self.comp_list.see(select)

    # ------------------------------------------------------------ результат --

    def _refresh(self) -> None:
        if not self._ready or self.form is None or self.ptype is None:
            return
        values, errors = self.form.collect()
        text = render_yaml(self.ptype, values, self.components)
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")
        if errors:
            more = f"  (и ещё {len(errors) - 1})" if len(errors) > 1 else ""
            self.status_var.set(f"Внимание: {errors[0]}{more}")
            self.status.configure(foreground="#b00020")
        else:
            self.status_var.set("Всё заполнено, можно сохранять")
            self.status.configure(foreground="#1b7a2f")

    def current_yaml(self) -> Optional[str]:
        values, errors = self.form.collect()
        if errors:
            messagebox.showerror("Заполните форму", "\n".join(errors), parent=self)
            return None
        return render_yaml(self.ptype, values, self.components)

    def _copy(self) -> None:
        text = self.preview.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Скопировано в буфер обмена")
        self.status.configure(foreground="#1b7a2f")

    def _default_filename(self, values: Dict[str, Any]) -> str:
        ident = str(values.get("id", "")).strip()
        if not ident:
            return "prototype.yml"
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", ident).lower()
        snake = re.sub(r"[^a-z0-9_]+", "_", snake).strip("_")
        return (snake or "prototype") + ".yml"

    def _save(self) -> None:
        values, errors = self.form.collect()
        if errors:
            messagebox.showerror("Нельзя сохранить", "\n".join(errors), parent=self)
            return
        text = render_yaml(self.ptype, values, self.components)
        path = filedialog.asksaveasfilename(
            parent=self, title="Сохранить прототип", defaultextension=".yml",
            initialfile=self._default_filename(values), initialdir=self._last_dir,
            filetypes=[("YAML", "*.yml *.yaml"), ("Все файлы", "*.*")], confirmoverwrite=False)
        if not path:
            return
        append = False
        if os.path.exists(path) and os.path.getsize(path) > 0:
            answer = messagebox.askyesnocancel(
                "Файл уже существует",
                "Дописать прототип в конец этого файла?\n\n"
                "Да — дописать в конец\nНет — перезаписать файл\nОтмена — не сохранять",
                parent=self)
            if answer is None:
                return
            append = answer
        try:
            save_yaml(Path(path), text, append=append)
        except OSError as exc:
            messagebox.showerror("Ошибка записи", str(exc), parent=self)
            return
        self._last_dir = os.path.dirname(path)
        self.status_var.set(f"Сохранено: {path}")
        self.status.configure(foreground="#1b7a2f")

    # ------------------------------------------------------- команды меню ----

    def has_data(self) -> bool:
        if self.form is None:
            return False
        values, _ = self.form.collect()
        return bool(values or self.components)

    def reset(self) -> None:
        self.components.clear()
        self.form = None
        self._select_type(self.ptype)
        self.search_var.set("")

    def reload_registry(self, registry: Registry) -> None:
        """Подхватить изменения в JSON-списках без перезапуска."""
        self.reg = registry
        current = self.ptype.type if self.ptype else None
        self._fill_types()
        new = registry.prototype_types.get(current) or next(iter(registry.prototype_types.values()), None)
        self._select_type(new)
