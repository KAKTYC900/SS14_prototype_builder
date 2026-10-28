"""Сборка итогового прототипа и запись в файл."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .models import ComponentInstance, PrototypeTypeDef
from .yaml_emit import dump_documents


def build_prototype(ptype: PrototypeTypeDef, values: Dict[str, Any],
                    components: List[ComponentInstance]) -> Dict[str, Any]:
    """Собирает dict прототипа в порядке, принятом в SS14: type, поля..., components."""
    proto: Dict[str, Any] = {"type": ptype.type}
    for key, value in values.items():
        proto[key] = value
    if ptype.supports_components and components:
        comps = []
        for comp in components:
            item: Dict[str, Any] = {"type": comp.name}
            item.update(comp.data)
            comps.append(item)
        proto["components"] = comps
    return proto


def render_yaml(ptype: PrototypeTypeDef, values: Dict[str, Any],
                components: List[ComponentInstance]) -> str:
    return dump_documents([build_prototype(ptype, values, components)])


def save_yaml(path: Path, text: str, append: bool = False) -> None:
    """Записывает YAML в файл (UTF-8, LF). При append дописывает в конец через пустую строку."""
    path = Path(path)
    if append and path.exists() and path.stat().st_size > 0:
        existing = path.read_text(encoding="utf-8-sig")
        if not existing.endswith("\n"):
            existing += "\n"
        text = existing + "\n" + text
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
