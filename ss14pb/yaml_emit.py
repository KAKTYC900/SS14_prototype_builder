"""Минимальный генератор YAML в стиле файлов Space Station 14.

Без внешних зависимостей. Особенности стиля SS14:
    * элементы списка записываются на том же отступе, что и ключ-владелец;
    * цвета и строки со спецсимволами берутся в двойные кавычки;
    * bool пишутся как true/false.

    - type: entity
      id: Example
      components:
      - type: Sprite
        sprite: Objects/example.rsi
"""

from __future__ import annotations

import re
from typing import Any, List

_INDENT = 2

# Строки, которые нельзя писать «голыми».
_LEADING_SPECIAL = set("-?:,[]{}#&*!|>'\"%@`")
_FORCE_QUOTE_WORDS = {"~", "null", "Null", "NULL"}


def _needs_quotes(s: str) -> bool:
    if s == "" or s != s.strip():
        return True
    if s in _FORCE_QUOTE_WORDS:
        return True
    if s[0] in _LEADING_SPECIAL:
        return True
    if ": " in s or " #" in s or s.endswith(":"):
        return True
    if re.search(r"[\x00-\x1f\x7f]", s):
        return True
    return False


def _quote(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\x%02x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    s = str(value)
    return _quote(s) if _needs_quotes(s) else s


def _format_key(key: Any) -> str:
    return format_scalar(str(key))


def _is_empty_container(v: Any) -> bool:
    return isinstance(v, (dict, list)) and len(v) == 0


def _emit_mapping(mapping: dict, indent: int) -> List[str]:
    lines: List[str] = []
    pad = " " * indent
    for key, value in mapping.items():
        k = _format_key(key)
        if isinstance(value, dict) and value:
            lines.append(f"{pad}{k}:")
            lines.extend(_emit_mapping(value, indent + _INDENT))
        elif isinstance(value, list) and value:
            lines.append(f"{pad}{k}:")
            lines.extend(_emit_list(value, indent))
        elif _is_empty_container(value):
            lines.append(f"{pad}{k}: {'{}' if isinstance(value, dict) else '[]'}")
        else:
            lines.append(f"{pad}{k}: {format_scalar(value)}")
    return lines


def _emit_list(items: list, indent: int) -> List[str]:
    lines: List[str] = []
    pad = " " * indent
    for item in items:
        if isinstance(item, dict) and item:
            inner = _emit_mapping(item, indent + _INDENT)
            # первая строка элемента сливается с маркером "- "
            lines.append(f"{pad}- {inner[0][indent + _INDENT:]}")
            lines.extend(inner[1:])
        elif isinstance(item, list) and item:
            inner = _emit_list(item, indent + _INDENT)
            lines.append(f"{pad}- {inner[0][indent + _INDENT:]}")
            lines.extend(inner[1:])
        elif _is_empty_container(item):
            lines.append(f"{pad}- {'{}' if isinstance(item, dict) else '[]'}")
        else:
            lines.append(f"{pad}- {format_scalar(item)}")
    return lines


def dump_documents(prototypes: List[dict]) -> str:
    """Список прототипов (dict) -> текст .yml. Между прототипами пустая строка."""
    blocks = []
    for proto in prototypes:
        blocks.append("\n".join(_emit_list([proto], 0)))
    return "\n\n".join(blocks) + "\n"


def dump_prototype(proto: dict) -> str:
    return dump_documents([proto])
