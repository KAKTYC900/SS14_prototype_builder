"""Тесты ядра (без GUI). Запуск:  python -m unittest discover -s tests -v"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ss14pb import rsi  # noqa: E402
from ss14pb.builder import build_prototype, render_yaml, save_yaml  # noqa: E402
from ss14pb.models import (ComponentInstance, DefinitionError, FieldDef,  # noqa: E402
                           parse_number, parse_vector2)
from ss14pb.registry import Registry  # noqa: E402
from ss14pb.yaml_emit import dump_documents, format_scalar  # noqa: E402

try:
    import yaml  # PyYAML — необязателен, только для самопроверки вывода
except ImportError:  # pragma: no cover
    yaml = None


class YamlEmitTests(unittest.TestCase):
    def test_ss14_style(self):
        proto = {"type": "entity", "id": "X", "components": [
            {"type": "Sprite", "sprite": "a.rsi", "layers": [{"state": "icon", "color": "#FFF"},
                                                             {"state": "b"}]},
            {"type": "Appearance"}]}
        expected = (
            "- type: entity\n"
            "  id: X\n"
            "  components:\n"
            "  - type: Sprite\n"
            "    sprite: a.rsi\n"
            "    layers:\n"
            "    - state: icon\n"
            "      color: \"#FFF\"\n"
            "    - state: b\n"
            "  - type: Appearance\n")
        self.assertEqual(dump_documents([proto]), expected)

    def test_scalars(self):
        self.assertEqual(format_scalar(True), "true")
        self.assertEqual(format_scalar(False), "false")
        self.assertEqual(format_scalar(5), "5")
        self.assertEqual(format_scalar(5.0), "5")
        self.assertEqual(format_scalar(0.25), "0.25")
        self.assertEqual(format_scalar("0.5,0.5"), "0.5,0.5")
        self.assertEqual(format_scalar("#FF0000"), '"#FF0000"')
        self.assertEqual(format_scalar("a: b"), '"a: b"')
        self.assertEqual(format_scalar("text # c"), '"text # c"')
        self.assertEqual(format_scalar("line\nbreak"), '"line\\nbreak"')
        self.assertEqual(format_scalar(""), '""')
        self.assertEqual(format_scalar("крутой ключ"), "крутой ключ")
        self.assertEqual(format_scalar("/Audio/x.ogg"), "/Audio/x.ogg")

    def test_empty_containers_and_nested_lists(self):
        out = dump_documents([{"a": {}, "b": [], "c": [[1, 2], []]}])
        self.assertIn("- a: {}\n  b: []\n", out)

    def test_multiple_documents(self):
        out = dump_documents([{"type": "Tag", "id": "A"}, {"type": "Tag", "id": "B"}])
        self.assertEqual(out, "- type: Tag\n  id: A\n\n- type: Tag\n  id: B\n")

    @unittest.skipIf(yaml is None, "PyYAML не установлен")
    def test_roundtrip_with_pyyaml(self):
        proto = {
            "type": "entity", "parent": "BaseItem", "id": "Cool", "name": "крутой: ключ",
            "description": "Строка\nс переносом и # решёткой, \"кавычками\" и \\ слэшем",
            "components": [
                {"type": "Sprite", "color": "#FF8800", "scale": "1.5,1.5", "visible": True,
                 "layers": [{"state": "icon", "map": ["enum.X.Y", "b"]}, {"state": "x"}]},
                {"type": "MeleeWeapon", "attackRate": 1.5, "damage": {"types": {"Blunt": 10, "Slash": 2.5}}},
                {"type": "Appearance"}]}
        for tricky in ('say "hi"\\', "it's", "- dash", "a, b", "[x]", "{y}", "50%", "@at", "k: v", "a #b", "~", "null"):
            self.assertEqual(yaml.safe_load(format_scalar(tricky)), tricky, tricky)
        loaded = yaml.safe_load(dump_documents([proto]))
        self.assertEqual(len(loaded), 1)
        got = loaded[0]
        self.assertEqual(got["name"], proto["name"])
        self.assertEqual(got["description"], proto["description"])
        self.assertEqual(got["components"][0]["color"], "#FF8800")
        self.assertEqual(got["components"][0]["layers"][0]["map"], ["enum.X.Y", "b"])
        self.assertEqual(got["components"][1]["damage"]["types"], {"Blunt": 10, "Slash": 2.5})
        self.assertEqual(got["components"][2], {"type": "Appearance"})


class ModelTests(unittest.TestCase):
    def test_parse_number(self):
        self.assertEqual(parse_number("5", "int"), 5)
        self.assertEqual(parse_number("2,5", "float"), 2.5)
        self.assertEqual(parse_number("3", "float"), 3)
        self.assertEqual(parse_number("1e3", "float"), 1000.0)
        with self.assertRaises(ValueError):
            parse_number("abc", "float")
        with self.assertRaises(ValueError):
            parse_number("2.5", "int")
        with self.assertRaises(ValueError):
            parse_number("nan", "float")

    def test_vector2(self):
        self.assertEqual(parse_vector2("1", "2.5"), "1,2.5")
        self.assertEqual(parse_vector2("", ""), None)
        with self.assertRaises(ValueError):
            parse_vector2("1", "")

    def test_field_validation(self):
        with self.assertRaises(DefinitionError):
            FieldDef.from_dict({"key": "x", "type": "nope"})
        with self.assertRaises(DefinitionError):
            FieldDef.from_dict({"key": "g", "type": "group"})
        with self.assertRaises(DefinitionError):
            FieldDef.from_dict({"type": "string"})


class RegistryTests(unittest.TestCase):
    def test_builtin_loads_cleanly(self):
        reg = Registry.load(custom_dir=Path(tempfile.mkdtemp()))
        self.assertEqual(reg.errors, [])
        self.assertIn("entity", reg.prototype_types)
        self.assertIn("gas", reg.prototype_types)
        self.assertIn("Sprite", reg.components)
        self.assertIn("Визуальные эффекты", reg.categories())
        self.assertTrue(reg.prototype_types["entity"].supports_components)
        self.assertFalse(reg.prototype_types["gas"].supports_components)

    def test_custom_adds_and_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "components").mkdir()
            (tmp / "prototype_types").mkdir()
            (tmp / "components" / "mine.json").write_text(json.dumps({
                "category": "Мои",
                "components": [
                    {"name": "MyComp", "fields": [{"key": "a", "type": "int"}]},
                    {"name": "Sprite", "description": "переопределён", "fields": []},
                ]}), encoding="utf-8")
            (tmp / "prototype_types" / "mine.json").write_text(json.dumps(
                {"type": "myType", "fields": [{"key": "id", "required": True}]}), encoding="utf-8")
            reg = Registry.load(custom_dir=tmp)
            self.assertEqual(reg.errors, [])
            self.assertEqual(reg.components["MyComp"].category, "Мои")
            self.assertEqual(reg.components["MyComp"].origin, "custom")
            self.assertEqual(reg.components["Sprite"].description, "переопределён")
            self.assertIn("myType", reg.prototype_types)

    def test_errors_are_collected_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "components").mkdir()
            (tmp / "components" / "broken.json").write_text("{ not json", encoding="utf-8")
            (tmp / "components" / "bad_field.json").write_text(json.dumps(
                {"components": [{"name": "Bad", "fields": [{"key": "x", "type": "weird"}]},
                                {"name": "Good"}]}), encoding="utf-8")
            (tmp / "components" / "reserved.json").write_text(json.dumps(
                {"components": [{"name": "R", "fields": [{"key": "type"}]}]}), encoding="utf-8")
            reg = Registry.load(custom_dir=tmp)
            self.assertEqual(len(reg.errors), 3)
            self.assertIn("Good", reg.components)
            self.assertNotIn("Bad", reg.components)

    def test_search(self):
        reg = Registry.load(custom_dir=Path(tempfile.mkdtemp()))
        names = [c.name for c in reg.search("spr")]
        self.assertIn("Sprite", names)
        self.assertTrue(any(c.name == "Battery" for c in reg.search("электричество")))


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.load(custom_dir=Path(tempfile.mkdtemp()))

    def test_entity_order_and_components(self):
        ent = self.reg.prototype_types["entity"]
        text = render_yaml(ent, {"id": "A", "name": "a"}, [
            ComponentInstance("Sprite", {"state": "icon"}), ComponentInstance("Appearance")])
        self.assertTrue(text.startswith("- type: entity\n  id: A\n  name: a\n  components:\n"))
        self.assertIn("  - type: Appearance\n", text)

    def test_gas_has_no_components(self):
        gas = self.reg.prototype_types["gas"]
        proto = build_prototype(gas, {"id": "9", "name": "gases-x"}, [ComponentInstance("Sprite")])
        self.assertNotIn("components", proto)

    def test_save_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.yml"
            save_yaml(p, "- type: Tag\n  id: A\n")
            save_yaml(p, "- type: Tag\n  id: B\n", append=True)
            self.assertEqual(p.read_text(encoding="utf-8"),
                             "- type: Tag\n  id: A\n\n- type: Tag\n  id: B\n")
            save_yaml(p, "- type: Tag\n  id: C\n", append=False)
            self.assertEqual(p.read_text(encoding="utf-8"), "- type: Tag\n  id: C\n")


class RsiTests(unittest.TestCase):
    def test_build_and_json(self):
        states = [
            rsi.StateDef("icon"),
            rsi.StateDef("equipped-BELT", 4),
            rsi.StateDef("anim", 1, rsi.make_delays(3, 0.1, 1)),
            rsi.StateDef("walk", 4, rsi.make_delays(2, 0.2, 4)),
        ]
        self.assertEqual(rsi.validate_meta(32, 32, states), [])
        meta = rsi.build_meta(32, 32, "CC-BY-SA-3.0", "Автор", states)
        self.assertEqual(list(meta), ["version", "license", "copyright", "size", "states"])
        text = rsi.meta_to_json(meta)
        self.assertEqual(json.loads(text), meta)
        self.assertEqual(meta["states"][0], {"name": "icon"})
        self.assertEqual(meta["states"][1], {"name": "equipped-BELT", "directions": 4})
        self.assertEqual(meta["states"][2]["delays"], [[0.1, 0.1, 0.1]])
        self.assertEqual(len(meta["states"][3]["delays"]), 4)
        self.assertIn('"delays": [\n', text)       # ряды — на отдельных строках
        self.assertIn("[0.1, 0.1, 0.1]", text)    # числа — в одну строку

    def test_optional_license_copyright(self):
        meta = rsi.build_meta(32, 32, "", "  ", [rsi.StateDef("icon")])
        self.assertEqual(list(meta), ["version", "size", "states"])

    def test_validation(self):
        bad = [rsi.StateDef(""), rsi.StateDef("a/b"), rsi.StateDef("x", 3),
               rsi.StateDef("d", 1, [[0.1, -1]]), rsi.StateDef("m", 4, [[0.1], [0.1, 0.2], [0.1], [0.1]]),
               rsi.StateDef("n", 4, [[0.1]]), rsi.StateDef("icon"), rsi.StateDef("icon")]
        errors = rsi.validate_meta(32, 32, bad)
        self.assertGreaterEqual(len(errors), 7)
        self.assertTrue(any("дважды" in e for e in errors))
        self.assertTrue(rsi.validate_meta(0, 32, [rsi.StateDef("a")]))
        self.assertTrue(rsi.validate_meta(32, 32, []))

    def test_delays_parsing(self):
        self.assertEqual(rsi.parse_delays_text("0.1, 0.2\n0.3 0.4"), [[0.1, 0.2], [0.3, 0.4]])
        # разделитель значений — запятая/пробел/;  десятичный разделитель — только точка
        self.assertEqual(rsi.parse_delays_text("0.1; 0.2,0.3"), [[0.1, 0.2, 0.3]])
        with self.assertRaises(ValueError):
            rsi.parse_delays_text("0.1, abc")
        self.assertEqual(rsi.normalize_delays([[0.1, 0.1]], 4), [[0.1, 0.1]] * 4)

    def test_parse_meta_roundtrip(self):
        states = [rsi.StateDef("a"), rsi.StateDef("b", 4, rsi.make_delays(2, 0.5, 4))]
        text = rsi.meta_to_json(rsi.build_meta(64, 48, "MIT", "me", states))
        w, h, lic, cr, parsed = rsi.parse_meta(text)
        self.assertEqual((w, h, lic, cr), (64, 48, "MIT", "me"))
        self.assertEqual([(s.name, s.directions, s.delays) for s in parsed],
                         [(s.name, s.directions, s.delays) for s in states])

    def test_scan_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in ("icon.png", "b.PNG", "notes.txt"):
                (Path(tmp) / n).write_bytes(b"")
            self.assertEqual(rsi.scan_png_states(Path(tmp)), ["icon"])  # *.png только в нижнем регистре
            out = rsi.save_meta(Path(tmp), "{}\n")
            self.assertEqual(out.name, "meta.json")


if __name__ == "__main__":
    unittest.main()
