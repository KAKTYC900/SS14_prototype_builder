"""Расположение папок с данными.

* ``data/``   — встроенные списки компонентов и типов прототипов (поставляются с приложением);
* ``custom/`` — ваши дополнения и переопределения. Файлы отсюда загружаются ПОСЛЕ встроенных,
  поэтому компонент/тип с тем же именем заменяет встроенный.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):  # сборка PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _app_root()))
    return _app_root()


APP_ROOT = _app_root()
DATA_DIR = _bundle_root() / "data"
CUSTOM_DIR = APP_ROOT / "custom"

COMPONENTS_SUBDIR = "components"
PROTOTYPE_TYPES_SUBDIR = "prototype_types"
