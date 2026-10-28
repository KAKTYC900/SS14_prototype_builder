"""Реестр компонентов и типов прототипов.

Читает все ``*.json`` из:
    data/components/            custom/components/
    data/prototype_types/       custom/prototype_types/

Формат файла компонентов:
    {"category": "Визуальные эффекты", "components": [ {...}, {...} ]}
(категорию можно переопределить у отдельного компонента ключом "category").

Формат файла типов прототипов: один объект ``{...}`` или список ``[{...}, ...]``.

Ошибки в отдельных файлах не роняют приложение — они собираются в ``Registry.errors``.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

from .models import ComponentDef, DefinitionError, PrototypeTypeDef
from . import paths


class Registry:
    def __init__(self) -> None:
        self.components: "OrderedDict[str, ComponentDef]" = OrderedDict()
        self.prototype_types: "OrderedDict[str, PrototypeTypeDef]" = OrderedDict()
        self.errors: List[str] = []

    # -- загрузка -------------------------------------------------------------

    @classmethod
    def load(cls, data_dir: Optional[Path] = None,
             custom_dir: Optional[Path] = None) -> "Registry":
        reg = cls()
        data_dir = Path(data_dir) if data_dir else paths.DATA_DIR
        custom_dir = Path(custom_dir) if custom_dir else paths.CUSTOM_DIR
        for root, origin in ((data_dir, "builtin"), (custom_dir, "custom")):
            reg._load_components(root / paths.COMPONENTS_SUBDIR, origin)
            reg._load_prototype_types(root / paths.PROTOTYPE_TYPES_SUBDIR, origin)
        return reg

    def _read_json(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            self.errors.append(f"{path.name}: некорректный JSON (строка {exc.lineno}, "
                               f"столбец {exc.colno}): {exc.msg}")
        except OSError as exc:
            self.errors.append(f"{path.name}: не удалось прочитать файл: {exc}")
        return None

    def _load_components(self, folder: Path, origin: str) -> None:
        if not folder.is_dir():
            return
        for path in sorted(folder.glob("*.json")):
            data = self._read_json(path)
            if data is None:
                continue
            if isinstance(data, list):
                data = {"category": "", "components": data}
            if not isinstance(data, dict) or not isinstance(data.get("components"), list):
                self.errors.append(f"{path.name}: ожидался объект с массивом 'components'")
                continue
            default_category = str(data.get("category", ""))
            for raw in data["components"]:
                try:
                    comp = ComponentDef.from_dict(raw, default_category, path.name, origin)
                except DefinitionError as exc:
                    self.errors.append(str(exc))
                    continue
                self.components[comp.name] = comp

    def _load_prototype_types(self, folder: Path, origin: str) -> None:
        if not folder.is_dir():
            return
        for path in sorted(folder.glob("*.json")):
            data = self._read_json(path)
            if data is None:
                continue
            items = data if isinstance(data, list) else [data]
            for raw in items:
                try:
                    ptype = PrototypeTypeDef.from_dict(raw, path.name, origin)
                except DefinitionError as exc:
                    self.errors.append(str(exc))
                    continue
                self.prototype_types[ptype.type] = ptype

    # -- запросы --------------------------------------------------------------

    def categories(self) -> List[str]:
        """Категории в порядке первого появления."""
        seen: Dict[str, None] = OrderedDict()
        for comp in self.components.values():
            seen.setdefault(comp.category, None)
        return list(seen)

    def components_by_category(self) -> "OrderedDict[str, List[ComponentDef]]":
        out: "OrderedDict[str, List[ComponentDef]]" = OrderedDict(
            (cat, []) for cat in self.categories())
        for comp in self.components.values():
            out[comp.category].append(comp)
        for comps in out.values():
            comps.sort(key=lambda c: c.name.lower())
        return out

    def search(self, query: str) -> List[ComponentDef]:
        q = query.strip().lower()
        if not q:
            return list(self.components.values())
        return [c for c in self.components.values()
                if q in c.name.lower() or q in c.description.lower()
                or q in c.category.lower()]
