"""Модели данных: описание полей, компонентов и типов прототипов.

Все описания читаются из JSON, поэтому добавить новый компонент или тип прототипа
можно без правки кода (см. README.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

FIELD_TYPES = (
    "string",   # одна строка
    "text",     # многострочный текст
    "int",      # целое число
    "float",    # дробное число
    "bool",     # true / false / не задано
    "enum",     # выбор из списка options (при editable=true можно вписать своё)
    "color",    # цвет #RRGGBB
    "vector2",  # пара чисел "x,y"
    "list",     # список простых значений (item_type: string/int/float)
    "map",      # словарь «ключ: число/строка» (value_type: float/int/string)
    "group",    # вложенный объект с полями fields
    "objlist",  # список объектов с полями item_fields (например layers у Sprite)
)


class DefinitionError(ValueError):
    """Ошибка в JSON-описании компонента или типа прототипа."""


@dataclass
class FieldDef:
    key: str
    type: str = "string"
    label: str = ""
    required: bool = False
    help: str = ""
    placeholder: str = ""
    options: List[str] = field(default_factory=list)   # для enum
    editable: bool = False                             # enum: разрешить свои значения
    item_type: str = "string"                          # для list
    value_type: str = "float"                          # для map
    fields: List["FieldDef"] = field(default_factory=list)       # для group
    item_fields: List["FieldDef"] = field(default_factory=list)  # для objlist
    item_label_key: str = ""                           # objlist: поле для подписи элемента

    @property
    def title(self) -> str:
        return self.label or self.key

    @staticmethod
    def from_dict(data: Dict[str, Any], where: str = "") -> "FieldDef":
        if not isinstance(data, dict):
            raise DefinitionError(f"{where}: поле должно быть объектом JSON")
        key = data.get("key")
        if not key or not isinstance(key, str):
            raise DefinitionError(f"{where}: у поля нет строкового 'key'")
        ftype = data.get("type", "string")
        if ftype not in FIELD_TYPES:
            raise DefinitionError(
                f"{where}: поле '{key}' имеет неизвестный тип '{ftype}'. "
                f"Допустимые: {', '.join(FIELD_TYPES)}"
            )
        here = f"{where}/{key}"
        sub = [FieldDef.from_dict(f, here) for f in data.get("fields", [])]
        item_sub = [FieldDef.from_dict(f, here) for f in data.get("item_fields", [])]
        if ftype == "group" and not sub:
            raise DefinitionError(f"{here}: для типа 'group' нужен непустой 'fields'")
        if ftype == "objlist" and not item_sub:
            raise DefinitionError(f"{here}: для типа 'objlist' нужен непустой 'item_fields'")
        if ftype == "list" and data.get("item_type", "string") not in ("string", "int", "float"):
            raise DefinitionError(f"{here}: item_type должен быть string, int или float")
        if ftype == "map" and data.get("value_type", "float") not in ("string", "int", "float"):
            raise DefinitionError(f"{here}: value_type должен быть string, int или float")
        return FieldDef(
            key=key,
            type=ftype,
            label=str(data.get("label", "")),
            required=bool(data.get("required", False)),
            help=str(data.get("help", "")),
            placeholder=str(data.get("placeholder", "")),
            options=[str(o) for o in data.get("options", [])],
            editable=bool(data.get("editable", False)),
            item_type=str(data.get("item_type", "string")),
            value_type=str(data.get("value_type", "float")),
            fields=sub,
            item_fields=item_sub,
            item_label_key=str(data.get("item_label_key", "")),
        )


@dataclass
class ComponentDef:
    name: str
    category: str
    description: str = ""
    fields: List[FieldDef] = field(default_factory=list)
    origin: str = "builtin"   # builtin | custom

    @staticmethod
    def from_dict(data: Dict[str, Any], default_category: str, where: str,
                  origin: str) -> "ComponentDef":
        if not isinstance(data, dict):
            raise DefinitionError(f"{where}: компонент должен быть объектом JSON")
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise DefinitionError(f"{where}: у компонента нет строкового 'name'")
        here = f"{where}/{name}"
        fields = [FieldDef.from_dict(f, here) for f in data.get("fields", [])]
        _check_unique(fields, here)
        return ComponentDef(
            name=name,
            category=str(data.get("category") or default_category or "Прочее"),
            description=str(data.get("description", "")),
            fields=fields,
            origin=origin,
        )


@dataclass
class PrototypeTypeDef:
    type: str                  # значение ключа "type:" в YAML (entity, gas, ...)
    label: str = ""
    description: str = ""
    supports_components: bool = False
    fields: List[FieldDef] = field(default_factory=list)
    origin: str = "builtin"

    @property
    def title(self) -> str:
        return self.label or self.type

    @staticmethod
    def from_dict(data: Dict[str, Any], where: str, origin: str) -> "PrototypeTypeDef":
        if not isinstance(data, dict):
            raise DefinitionError(f"{where}: тип прототипа должен быть объектом JSON")
        ptype = data.get("type")
        if not ptype or not isinstance(ptype, str):
            raise DefinitionError(f"{where}: у типа прототипа нет строкового 'type'")
        here = f"{where}/{ptype}"
        fields = [FieldDef.from_dict(f, here) for f in data.get("fields", [])]
        _check_unique(fields, here)
        return PrototypeTypeDef(
            type=ptype,
            label=str(data.get("label", "")),
            description=str(data.get("description", "")),
            supports_components=bool(data.get("supports_components", False)),
            fields=fields,
            origin=origin,
        )


def _check_unique(fields: List[FieldDef], where: str) -> None:
    seen = set()
    for f in fields:
        if f.key == "type":
            raise DefinitionError(f"{where}: ключ 'type' зарезервирован (он задаёт имя "
                                  f"компонента/тип прототипа), используйте другое имя поля")
        if f.key in seen:
            raise DefinitionError(f"{where}: поле '{f.key}' объявлено дважды")
        seen.add(f.key)


# ---------------------------------------------------------------------------
# Разбор значений, введённых пользователем
# ---------------------------------------------------------------------------

def parse_number(text: str, kind: str):
    """Разбирает строку в int/float. Бросает ValueError с понятным текстом."""
    s = text.strip().replace(",", ".") if kind == "float" else text.strip()
    if kind == "int":
        try:
            return int(s)
        except ValueError:
            raise ValueError(f"«{text}» — не целое число") from None
    try:
        f = float(s)
    except ValueError:
        raise ValueError(f"«{text}» — не число") from None
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(f"«{text}» — недопустимое число")
    return int(f) if f.is_integer() and "." not in s and "e" not in s.lower() else f


def parse_vector2(x: str, y: str) -> Optional[str]:
    """Пара чисел -> строка "x,y". Пустая пара -> None."""
    x, y = x.strip(), y.strip()
    if not x and not y:
        return None
    if not x or not y:
        raise ValueError("нужно заполнить обе координаты (X и Y)")
    return f"{_num_text(parse_number(x, 'float'))},{_num_text(parse_number(y, 'float'))}"


def _num_text(n) -> str:
    if isinstance(n, float):
        if n.is_integer():
            return str(int(n))
        return repr(n)
    return str(n)


@dataclass
class ComponentInstance:
    """Компонент, добавленный в прототип: имя + уже типизированные значения полей."""
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
