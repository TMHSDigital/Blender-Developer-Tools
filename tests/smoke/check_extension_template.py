"""Load the shipped extension template into Blender and prove its lifecycle.

Run: blender --background --python tests/smoke/check_extension_template.py

Imports templates/extension-addon-template/__init__.py as a package, calls
register(), asserts the operator, panel and Scene pointer exist and that the
operator works, then calls unregister() and asserts all three are gone. Exits
non-zero naming the first failed assertion:

  3  register() or the operator/PropertyGroup contract failed
  4  something survived unregister()

Falsifier (catalog row): `-- --skip-unregister` must exit 4.
"""
import importlib.util
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(ROOT, "templates", "extension-addon-template")


SKIP_UNREGISTER = "--skip-unregister" in (sys.argv[sys.argv.index("--") + 1:]
                                         if "--" in sys.argv else [])


def fail(msg, code=3):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(code)


def operator_present():
    # bpy.ops attribute lookup is lazy and can outlive unregister_class, so
    # ask the type registry instead.
    return bpy.types.Operator.bl_rna_get_subclass_py("EXAMPLE_OT_nudge_active") is not None


def panel_present():
    return bpy.types.Panel.bl_rna_get_subclass_py("VIEW3D_PT_example_addon") is not None


bpy.ops.wm.read_factory_settings(use_empty=True)

spec = importlib.util.spec_from_file_location(
    "example_addon", os.path.join(PKG_DIR, "__init__.py"),
    submodule_search_locations=[PKG_DIR],
)
mod = importlib.util.module_from_spec(spec)
sys.modules["example_addon"] = mod
spec.loader.exec_module(mod)

mod.register()
if not operator_present():
    fail("operator example.nudge_active missing after register()")
if not panel_present():
    fail("panel VIEW3D_PT_example_addon missing after register()")
if not hasattr(bpy.types.Scene, "example_addon"):
    fail("Scene.example_addon pointer missing after register()")

bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.active_object
settings = bpy.context.scene.example_addon
if abs(settings.factor - 1.0) > 1e-9 or settings.enabled is not True:
    fail(f"PropertyGroup defaults wrong: factor={settings.factor} enabled={settings.enabled}")
z0 = cube.location.z
bpy.ops.example.nudge_active(factor=2.5)
if abs(cube.location.z - (z0 + 2.5)) > 1e-6:
    fail(f"operator moved z by {cube.location.z - z0}, expected 2.5")

if not SKIP_UNREGISTER:
    mod.unregister()
if operator_present():
    fail("operator example.nudge_active still present after unregister()", 4)
if panel_present():
    fail("panel still present after unregister()", 4)
if hasattr(bpy.types.Scene, "example_addon"):
    fail("Scene.example_addon pointer still bound after unregister()", 4)

print("extension template register/unregister lifecycle OK")
