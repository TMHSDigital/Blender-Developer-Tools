"""Fixtures for tools/bpy_lint.py (#534): every rule fires on its anti-pattern and
stays quiet on the fix. No Blender required.

    python tests/test_bpy_lint.py -v
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import bpy_lint as bl  # noqa: E402

# rule -> (bad source, good source). Each bad case is the rule's own "Wrong"
# pattern; each good case is its "Right" pattern.
CASES = {
    "no-bgl": ("import bgl\nbgl.glEnable(bgl.GL_BLEND)\n",
               "import gpu\ngpu.state.blend_set('ALPHA')\n"),
    "no-legacy-vse-sequences": ("se.sequences.new_effect(name='A')\n",
                                "coll = se.strips if hasattr(se, 'strips') else se.sequences\nse.strips_all\n"),
    "no-removed-normals-api": ("me.use_auto_smooth = True\nme.calc_normals_split()\n",
                               "me.set_sharp_from_angle(angle=0.5)\n"),
    "prefer-temp-override-over-context-copy": (
        "ctx = bpy.context.copy()\nbpy.ops.object.join(ctx)\n",
        "with bpy.context.temp_override(active_object=o):\n    bpy.ops.object.join()\n"),
    "type-annotate-props-and-defend-context": (
        "class P(bpy.types.PropertyGroup):\n    x = bpy.props.FloatProperty()\n"
        "obj = bpy.context.active_object\nobj.name = 'a'\n",
        "class P(bpy.types.PropertyGroup):\n    x: bpy.props.FloatProperty()\n"
        "obj = bpy.context.active_object\nif obj is None:\n    raise SystemExit(3)\n"),
    "use-foreach-set-for-bulk-data": ("for v in me.vertices:\n    v.co.z = 0.0\n",
                                      "me.vertices.foreach_set('co', flat)\n"),
    "prefer-data-over-ops-in-loops": (
        "for o in objs:\n    bpy.ops.object.shade_smooth()\n",
        "for o in objs:\n    o.data.shade_smooth()\nbpy.ops.export_scene.gltf.get_rna_type()\n"),
    "always-free-bmesh": ("def f(me):\n    bm = bmesh.new()\n    bm.from_mesh(me)\n",
                          "def f(me):\n    bm = bmesh.new()\n    try:\n        bm.from_mesh(me)\n"
                          "    finally:\n        bm.free()\n"),
    "no-legacy-action-fcurves": ("fc = obj.animation_data.action.fcurves.new('location', index=2)\n",
                                 "fc = cbag.fcurves.new('location', index=2)\n"),
    "principled-v2-socket-names": ('bsdf.inputs["Emission"].default_value = (1, 1, 1, 1)\nbsdf.inputs[17]\n',
                                   'bsdf.inputs["Emission Color"].default_value = (1, 1, 1, 1)\nmix.inputs[6]\n'),
    "no-nodes-modifier-idprop-inputs": (
        'mod["Socket_2"] = 2.5\n',
        'if bpy.app.version >= (5, 2, 0):\n    getattr(mod.properties.inputs, ident).value = 2.5\n'
        'else:\n    mod[ident] = 2.5\n'),
    "branch-eevee-engine-id": (
        "scene.render.engine = 'BLENDER_EEVEE_NEXT'\n",
        "def eevee():\n    if bpy.app.version >= (5, 0, 0):\n        return 'BLENDER_EEVEE'\n"
        "    return 'BLENDER_EEVEE_NEXT'\n"),
    "validate-imported-mesh-scale": (
        "bpy.ops.import_scene.gltf(filepath=p)\nbm = bmesh.new()\n",
        "bpy.ops.import_scene.gltf(filepath=p)\nscene.unit_settings.scale_length = 1.0\n"
        "bpy.ops.object.transform_apply(scale=True)\nbm = bmesh.new()\n"),
    "no-unapplied-modifiers-on-export": (
        "o.modifiers.new('S', 'SUBSURF')\nbpy.ops.export_scene.gltf(filepath=p)\n",
        "o.modifiers.new('S', 'SUBSURF')\nbpy.ops.export_scene.gltf(filepath=p, export_apply=True)\n"),
    "use-correct-axis-rna-per-exporter": (
        "bpy.ops.export_scene.gltf(filepath=p, axis_forward='-Z')\n",
        "bpy.ops.export_scene.gltf(filepath=p, export_yup=True)\n"
        "bpy.ops.export_scene.fbx(filepath=q, axis_forward='-Z', axis_up='Y')\n"),
}


def rules_hit(src: str, path: str = "x.py") -> set[str]:
    return {f.rule for f in bl.lint_source(path, src)}


class EveryRuleHasADetector(unittest.TestCase):
    def test_rules_dir_and_detectors_match(self):
        stems = {p.stem for p in (REPO / "rules").glob("*.mdc")}
        self.assertEqual(set(bl.DETECTORS), stems)
        self.assertEqual(set(bl.SKILL), stems)
        for rule, skill in bl.SKILL.items():
            self.assertTrue((REPO / "skills" / skill / "SKILL.md").is_file(), (rule, skill))

    def test_every_detector_has_a_fixture(self):
        self.assertEqual(set(CASES) | {"target-extensions-platform-format"}, set(bl.DETECTORS))


class Fixtures(unittest.TestCase):
    def test_bad_fires_and_good_is_quiet(self):
        for rule, (bad, good) in CASES.items():
            with self.subTest(rule=rule):
                self.assertIn(rule, rules_hit(bad), "bad case not flagged")
                self.assertNotIn(rule, rules_hit(good), "good case flagged")

    def test_bl_info_without_manifest(self):
        src = "bl_info = {'name': 'x', 'blender': (4, 5, 0)}\n"
        with tempfile.TemporaryDirectory() as td:
            init = os.path.join(td, "__init__.py")
            self.assertIn("target-extensions-platform-format", rules_hit(src, init))
            Path(td, "blender_manifest.toml").write_text("id = 'x'\n", encoding="utf-8")
            self.assertNotIn("target-extensions-platform-format", rules_hit(src, init))

    def test_ignore_comment(self):
        src = "import bgl  # bpy-lint: ignore[no-bgl] 4.5-only fallback\n"
        self.assertNotIn("no-bgl", rules_hit(src))
        self.assertIn("no-bgl", rules_hit("import bgl  # bpy-lint: ignore[always-free-bmesh]\n"))

    def test_syntax_error_is_reported_not_raised(self):
        self.assertEqual(rules_hit("def (:\n"), {"syntax"})


class Cli(unittest.TestCase):
    def run_cli(self, src, *extra):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td, "a.py")
            p.write_text(src, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = bl.main([str(p), *extra])
        return code, out.getvalue()

    def test_exit_codes(self):
        self.assertEqual(self.run_cli("x = 1\n")[0], 0)
        self.assertEqual(self.run_cli("import bgl\n")[0], 1)

    def test_json_output(self):
        code, out = self.run_cli("import bgl\n", "--json")
        rows = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(rows[0]["rule"], "no-bgl")
        self.assertEqual(rows[0]["skill"], "gpu-drawing-and-overlays")

    def test_rule_filter(self):
        code, out = self.run_cli("import bgl\nme.use_auto_smooth = True\n", "--rule", "no-bgl")
        self.assertIn("no-bgl", out)
        self.assertNotIn("no-removed-normals-api", out)


if __name__ == "__main__":
    unittest.main()
