"""Register/unregister round-trip for this add-on, headless. Copy it with the template.

    blender --background --factory-startup --python-exit-code 1 \
        --python tests/check_register.py [-- --skip-unregister]

Loads the add-on package (the directory above tests/) under the module name
Blender gives an installed extension, then:

1. register(): every bpy.types class the package defines must be registered,
   and register() must add something (exit 3 otherwise);
2. unregister(): every one of those classes must be gone, and every property
   register() added to an ID type (Scene.my_addon = PointerProperty(...))
   must be deleted again (exit 4 names what survived);
3. register() and unregister() a second time: a non-symmetric pair usually
   fails here, on the re-register (exit 3).

Generic: it finds the classes and properties by comparing before and after,
so it keeps working as you add operators, panels and property groups.
--skip-unregister is the falsifier: it skips step 2's unregister and must
exit 4. Exit 0 means the lifecycle is symmetric on this Blender.
"""
import importlib.util
import inspect
import os
import sys
import tomllib

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.dirname(HERE)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SKIP_UNREGISTER = "--skip-unregister" in ARGS
BASES = (bpy.types.Operator, bpy.types.Panel, bpy.types.Menu, bpy.types.UIList,
         bpy.types.PropertyGroup, bpy.types.AddonPreferences, bpy.types.Header)
ID_TYPES = (bpy.types.Scene, bpy.types.Object, bpy.types.Mesh, bpy.types.Material,
            bpy.types.WindowManager, bpy.types.World, bpy.types.Collection)


def fail(msg, code):
    print(f"FAIL: {msg}", file=sys.stderr)
    return code


def id_props():
    return {(t.__name__, p) for t in ID_TYPES for p in t.bl_rna.properties.keys()}


def package_classes(pkg_name):
    """bpy.types subclasses defined in the package or its submodules."""
    found = set()
    for name, m in list(sys.modules.items()):
        if name != pkg_name and not name.startswith(pkg_name + "."):
            continue
        for _attr, obj in inspect.getmembers(m, inspect.isclass):
            if issubclass(obj, BASES) and obj not in BASES and (
                    obj.__module__ == pkg_name or obj.__module__.startswith(pkg_name + ".")):
                found.add(obj)
    return found


def load_package():
    ident = "addon_under_test"
    manifest = os.path.join(PKG_DIR, "blender_manifest.toml")
    if os.path.isfile(manifest):
        with open(manifest, "rb") as fh:
            ident = tomllib.load(fh).get("id", ident)
    name = f"bl_ext.user_default.{ident}"  # what Blender names an installed extension
    for parent in ("bl_ext", "bl_ext.user_default"):
        sys.modules.setdefault(parent, type(sys)(parent))
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(PKG_DIR, "__init__.py"), submodule_search_locations=[PKG_DIR])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    pkg = load_package()
    classes = package_classes(pkg.__name__)
    before = id_props()

    pkg.register()
    added = id_props() - before
    missing = sorted(c.__name__ for c in classes if not c.is_registered)
    if missing:
        return fail(f"classes not registered by register(): {missing}", 3)
    if not classes and not added:
        return fail("register() registered no class and added no property", 3)

    if not SKIP_UNREGISTER:
        pkg.unregister()
    left = sorted(c.__name__ for c in classes if c.is_registered)
    if left:
        return fail(f"classes still registered after unregister(): {left}", 4)
    stale = sorted(f"{t}.{p}" for t, p in (id_props() & added))
    if stale:
        return fail(f"properties still bound after unregister(): {stale}", 4)

    try:
        pkg.register()
        pkg.unregister()
    except Exception as exc:  # noqa: BLE001 -- any failure here is the asymmetry
        return fail(f"second register()/unregister() raised {type(exc).__name__}: {exc}", 3)

    print(f"OK: {len(classes)} classes and {len(added)} properties register and unregister "
          f"symmetrically on Blender {bpy.app.version_string}")
    return 0


sys.exit(main())
