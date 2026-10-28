"""Главное окно приложения."""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .. import __version__, paths
from ..registry import Registry
from .prototype_tab import PrototypeTab
from .rsi_tab import RsiTab

HELP_TEXT = """\
Как добавить свой компонент
───────────────────────────
1. Откройте папку custom/components (Файл → Открыть папку custom).
2. Создайте файл, например my_components.json, по образцу _example.json.off
   (уберите «.off» из имени).
3. Нажмите F5 (Файл → Перезагрузить списки) — компонент появится в своей категории.

Компонент с тем же именем, что и встроенный, ЗАМЕНЯЕТ встроенный — так можно
поправить поля под вашу версию SS14.

Как добавить свой тип прототипа
───────────────────────────────
Положите JSON-файл в custom/prototype_types (формат смотрите в data/prototype_types).
Укажите "type" (значение для строки «- type: …» в YAML), список "fields" и, если
прототип содержит компоненты, "supports_components": true.

Типы полей: string, text, int, float, bool, enum, color, vector2, list, map,
group (вложенный объект), objlist (список объектов, как layers у Sprite).
Подробности — в README.md.
"""


def _open_folder(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        messagebox.showerror("Не удалось открыть папку", f"{path}\n\n{exc}")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"SS14 Prototype Builder {__version__}")
        self.geometry("1240x800")
        self.minsize(1000, 660)
        self._setup_style()

        self.registry = Registry.load()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)
        self.proto_tab = PrototypeTab(self.notebook, self.registry)
        self.rsi_tab = RsiTab(self.notebook)
        self.notebook.add(self.proto_tab, text="  Прототип  ")
        self.notebook.add(self.rsi_tab, text="  Meta-файл спрайтов (RSI)  ")

        self._build_menu()
        self.bind("<Control-n>", lambda e: self.new_prototype())
        self.bind("<F5>", lambda e: self.reload_lists())
        if self.registry.errors:
            self.after(300, self._show_registry_errors)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        names = style.theme_names()
        for preferred in ("vista", "aqua", "clam"):
            if preferred in names:
                style.theme_use(preferred)
                break

    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=False)
        file_menu.add_command(label="Новый прототип", accelerator="Ctrl+N", command=self.new_prototype)
        file_menu.add_command(label="Перезагрузить списки компонентов", accelerator="F5",
                              command=self.reload_lists)
        file_menu.add_command(label="Открыть папку custom", command=lambda: _open_folder(str(paths.CUSTOM_DIR)))
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.destroy)
        bar.add_cascade(label="Файл", menu=file_menu)

        help_menu = tk.Menu(bar, tearoff=False)
        help_menu.add_command(label="Как добавить компонент или тип прототипа", command=self._show_help)
        help_menu.add_command(label="О программе", command=self._about)
        bar.add_cascade(label="Справка", menu=help_menu)
        self.config(menu=bar)

    # -- действия -------------------------------------------------------------

    def new_prototype(self) -> None:
        if self.proto_tab.has_data() and not messagebox.askyesno(
                "Новый прототип", "Очистить текущий прототип и начать заново?", parent=self):
            return
        self.notebook.select(self.proto_tab)
        self.proto_tab.reset()

    def reload_lists(self) -> None:
        self.registry = Registry.load()
        self.proto_tab.reload_registry(self.registry)
        if self.registry.errors:
            self._show_registry_errors()
        else:
            messagebox.showinfo(
                "Списки обновлены",
                f"Типов прототипов: {len(self.registry.prototype_types)}\n"
                f"Компонентов: {len(self.registry.components)}", parent=self)

    def _show_registry_errors(self) -> None:
        errors = self.registry.errors
        shown = "\n\n".join(errors[:12])
        extra = f"\n\n…и ещё {len(errors) - 12}" if len(errors) > 12 else ""
        messagebox.showwarning("Проблемы в файлах со списками",
                               "Эти записи пропущены:\n\n" + shown + extra, parent=self)

    def _show_help(self) -> None:
        win = tk.Toplevel(self)
        win.title("Как расширять списки")
        win.geometry("640x520")
        text = tk.Text(win, wrap="word", padx=12, pady=10, borderwidth=0)
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

    def _about(self) -> None:
        messagebox.showinfo(
            "О программе",
            f"SS14 Prototype Builder {__version__}\n\n"
            "Генератор YAML-прототипов и meta.json (RSI) для Space Station 14.\n"
            "Списки компонентов хранятся в JSON и расширяются без правки кода.", parent=self)


def run() -> None:
    if sys.platform.startswith("win"):
        try:  # чёткий текст на HiDPI-экранах
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()
