"""Генерация meta.json для RSI (папка со спрайтами *.rsi).

Формат (RSI v1):
    {
      "version": 1,
      "license": "CC-BY-SA-3.0",
      "copyright": "Автор, источник",
      "size": {"x": 32, "y": 32},
      "states": [
        {"name": "icon"},
        {"name": "equipped-BELT", "directions": 4},
        {"name": "anim", "delays": [[0.1, 0.1, 0.1]]}
      ]
    }
``delays`` — список списков: по одному списку на каждое направление.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VALID_DIRECTIONS = (1, 4, 8)
COMMON_LICENSES = ["CC-BY-SA-3.0", "CC-BY-SA-4.0", "CC-BY-3.0", "CC-BY-4.0",
                   "CC0-1.0", "CC-BY-NC-SA-3.0", "MIT"]

_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass
class StateDef:
    name: str
    directions: int = 1
    delays: Optional[List[List[float]]] = None   # None — состояние без анимации

    @property
    def frames(self) -> int:
        return len(self.delays[0]) if self.delays else 1


def make_delays(frames: int, delay: float, directions: int) -> List[List[float]]:
    """Одинаковая задержка на всех кадрах и во всех направлениях."""
    return [[delay] * frames for _ in range(max(1, directions))]


def parse_delays_text(text: str) -> List[List[float]]:
    """Текст «0.1, 0.1, 0.2» (по одному направлению на строку) -> список списков."""
    rows: List[List[float]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        row = []
        for part in re.split(r"[;,\s]+", line):
            if not part:
                continue
            try:
                row.append(float(part.replace(",", ".")))
            except ValueError:
                raise ValueError(f"«{part}» — не число") from None
        if row:
            rows.append(row)
    return rows


def normalize_delays(delays: Optional[List[List[float]]],
                     directions: int) -> Optional[List[List[float]]]:
    """Если задан один ряд, а направлений несколько — копирует ряд на все направления."""
    if not delays:
        return None
    if len(delays) == 1 and directions > 1:
        return [list(delays[0]) for _ in range(directions)]
    return [list(r) for r in delays]


def validate_state(state: StateDef) -> List[str]:
    errors: List[str] = []
    name = state.name.strip()
    if not name:
        errors.append("не указано название состояния")
    elif _BAD_NAME_CHARS.search(name):
        errors.append(f"«{name}»: название не может содержать символы \\ / : * ? \" < > |")
    if state.directions not in VALID_DIRECTIONS:
        errors.append(f"«{name}»: направлений может быть {', '.join(map(str, VALID_DIRECTIONS))}")
    if state.delays is not None:
        if len(state.delays) != state.directions:
            errors.append(f"«{name}»: рядов задержек {len(state.delays)}, "
                          f"а направлений {state.directions}")
        lengths = {len(r) for r in state.delays}
        if len(lengths) > 1:
            errors.append(f"«{name}»: в разных направлениях разное число кадров")
        if 0 in lengths:
            errors.append(f"«{name}»: пустой ряд задержек")
        for row in state.delays:
            if any(d <= 0 for d in row):
                errors.append(f"«{name}»: задержка должна быть больше 0")
                break
    return errors


def validate_meta(width: int, height: int, states: List[StateDef]) -> List[str]:
    errors: List[str] = []
    if width <= 0 or height <= 0:
        errors.append("размер спрайта должен быть положительным")
    if not states:
        errors.append("добавьте хотя бы одно состояние")
    seen = set()
    for st in states:
        errors.extend(validate_state(st))
        key = st.name.strip()
        if key in seen:
            errors.append(f"состояние «{key}» указано дважды")
        seen.add(key)
    return errors


def build_meta(width: int, height: int, license_: str, copyright_: str,
               states: List[StateDef]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"version": 1}
    if license_.strip():
        meta["license"] = license_.strip()
    if copyright_.strip():
        meta["copyright"] = copyright_.strip()
    meta["size"] = {"x": width, "y": height}
    out_states = []
    for st in states:
        item: Dict[str, Any] = {"name": st.name.strip()}
        if st.directions != 1:
            item["directions"] = st.directions
        if st.delays:
            item["delays"] = [[_clean(d) for d in row] for row in st.delays]
        out_states.append(item)
    meta["states"] = out_states
    return meta


def _clean(d: float):
    return int(d) if float(d).is_integer() else d


# -- сериализация: читаемый JSON, числовые массивы — в одну строку ------------

def meta_to_json(meta: Dict[str, Any]) -> str:
    return _dump(meta, 0) + "\n"


def _is_scalar(v: Any) -> bool:
    return not isinstance(v, (dict, list))


def _dump(obj: Any, level: int) -> str:
    pad = "  " * level
    inner = "  " * (level + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        parts = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {_dump(v, level + 1)}"
                 for k, v in obj.items()]
        return "{\n" + ",\n".join(parts) + f"\n{pad}}}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if all(_is_scalar(v) for v in obj):
            return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in obj) + "]"
        parts = [f"{inner}{_dump(v, level + 1)}" for v in obj]
        return "[\n" + ",\n".join(parts) + f"\n{pad}]"
    return json.dumps(obj, ensure_ascii=False)


# -- чтение существующего meta.json и PNG -------------------------------------

def parse_meta(text: str) -> Tuple[int, int, str, str, List[StateDef]]:
    """meta.json -> (width, height, license, copyright, states)."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("в meta.json ожидался объект")
    size = data.get("size") or {}
    width, height = int(size.get("x", 32)), int(size.get("y", 32))
    states = []
    for raw in data.get("states", []):
        directions = int(raw.get("directions", 1))
        delays = raw.get("delays")
        if delays is not None:
            delays = [[float(d) for d in row] for row in delays]
        states.append(StateDef(str(raw.get("name", "")), directions, delays))
    return width, height, str(data.get("license", "")), str(data.get("copyright", "")), states


def scan_png_states(folder: Path) -> List[str]:
    """Имена состояний по файлам *.png в папке .rsi."""
    return sorted(p.stem for p in Path(folder).glob("*.png"))


def save_meta(folder_or_file: Path, text: str) -> Path:
    path = Path(folder_or_file)
    if path.is_dir():
        path = path / "meta.json"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path
