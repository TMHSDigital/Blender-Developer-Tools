"""Add-on register/unregister lifecycle — a runnable example.

Builds a small dual-format add-on (``blender_manifest.toml`` plus a legacy
``bl_info``) in a temp directory, with one PropertyGroup, one Panel and a
``Scene`` PointerProperty, then witnesses the contracts the scaffolding,
migration, panel and property skills teach:

- ``blender --command extension validate`` accepts the dual-format package:
  a leftover ``bl_info`` does not break the Extensions Platform path.
- The same code with only ``bl_info`` (no manifest) is rejected:
  "blender_manifest.toml not found". That is the first migration step.
- ``register()`` makes the Panel and PropertyGroup classes and the
  ``Scene.addon_probe`` pointer exist, and the pointer reads its default.
- ``unregister()`` in the right order (delete the pointer, then unregister
  the classes in reverse) leaves nothing behind. Unregistering the classes
  first leaves ``Scene.addon_probe`` pointing at an unregistered
  PropertyGroup. Touching that dangling property crashed Blender 5.2.1
  (EXCEPTION_ACCESS_VIOLATION); this script never touches it.

Pathology: no gallery still; the witness is registry state and the
validator's exit code.

    blender --background --python addon_register_lifecycle.py --
    blender --background --python addon_register_lifecycle.py -- --drop-manifest          # 3
    blender --background --python addon_register_lifecycle.py -- --legacy-gets-manifest   # 4
    blender --background --python addon_register_lifecycle.py -- --skip-pointer           # 5
    blender --background --python addon_register_lifecycle.py -- --classes-first          # 6
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

import bpy

ADDON_ID = "addon_probe"
PANEL = "ADDONPROBE_PT_settings"
GROUP = "ADDONPROBE_PG_settings"
DEFAULT_SIZE = 1.5

MANIFEST = textwrap.dedent(f'''\
    schema_version = "1.0.0"
    id = "{ADDON_ID}"
    version = "0.1.0"
    name = "Add-on Probe"
    tagline = "Register/unregister lifecycle witness"
    maintainer = "Blender Developer Tools <noreply@example.com>"
    type = "add-on"
    blender_version_min = "4.5.0"
    license = ["SPDX:GPL-3.0-or-later"]
''')

INIT = textwrap.dedent(f'''\
    # Legacy metadata kept beside the manifest (dual format): ignored by the
    # Extensions Platform, still read by Blender versions before 4.2.
    bl_info = {{"name": "Add-on Probe", "blender": (4, 5, 0), "version": (0, 1, 0),
               "category": "Object"}}

    import bpy


    class {GROUP}(bpy.types.PropertyGroup):
        size: bpy.props.FloatProperty(name="Size", default={DEFAULT_SIZE}, min=0.0)


    class {PANEL}(bpy.types.Panel):
        bl_label = "Add-on Probe"
        bl_idname = "{PANEL}"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Probe"

        def draw(self, context):
            settings = getattr(context.scene, "{ADDON_ID}", None)
            if settings is None:
                return
            self.layout.prop(settings, "size")


    classes = ({GROUP}, {PANEL})
    SKIP_POINTER = False
    CLASSES_FIRST = False


    def register():
        for cls in classes:
            bpy.utils.register_class(cls)
        if not SKIP_POINTER:
            bpy.types.Scene.{ADDON_ID} = bpy.props.PointerProperty(type={GROUP})


    def unregister():
        if CLASSES_FIRST:  # the wrong order: the pointer outlives its type
            for cls in reversed(classes):
                bpy.utils.unregister_class(cls)
            return
        if hasattr(bpy.types.Scene, "{ADDON_ID}"):
            del bpy.types.Scene.{ADDON_ID}
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
''')


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def write_package(path, with_manifest):
    os.makedirs(path)
    with open(os.path.join(path, "__init__.py"), "w", encoding="utf-8") as fh:
        fh.write(INIT)
    if with_manifest:
        with open(os.path.join(path, "blender_manifest.toml"), "w", encoding="utf-8") as fh:
            fh.write(MANIFEST)


def validate(path):
    proc = subprocess.run([bpy.app.binary_path, "--command", "extension", "validate", path],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    last = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
    return proc.returncode, last[0]


def registered(base, name):
    return base.bl_rna_get_subclass_py(name) is not None


def load(path):
    spec = importlib.util.spec_from_file_location(ADDON_ID, os.path.join(path, "__init__.py"),
                                                  submodule_search_locations=[path])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ADDON_ID] = mod
    spec.loader.exec_module(mod)
    return mod


def run(work, args):
    dual = os.path.join(work, "dual")
    legacy = os.path.join(work, "legacy")
    write_package(dual, with_manifest=not args.drop_manifest)
    write_package(legacy, with_manifest=args.legacy_gets_manifest)

    code, line = validate(dual)
    print(f"validate dual-format: exit {code} ({line})")
    if code != 0:
        return fail("the dual-format package (manifest + bl_info) did not validate", 3)

    code, line = validate(legacy)
    print(f"validate bl_info-only: exit {code} ({line})")
    if code == 0:
        return fail("a package without blender_manifest.toml validated; the migration "
                    "step this example witnesses is gone", 4)

    mod = load(dual)
    mod.SKIP_POINTER = args.skip_pointer
    mod.CLASSES_FIRST = args.classes_first
    mod.register()
    state = (registered(bpy.types.Panel, PANEL), registered(bpy.types.PropertyGroup, GROUP),
             hasattr(bpy.types.Scene, ADDON_ID))
    print(f"after register: panel={state[0]} group={state[1]} pointer={state[2]}")
    if not all(state):
        mod.unregister()
        return fail(f"register() left panel/group/pointer = {state}", 5)
    size = getattr(bpy.context.scene, ADDON_ID).size
    if abs(size - DEFAULT_SIZE) > 1e-6:
        return fail(f"Scene.{ADDON_ID}.size reads {size}, expected the default {DEFAULT_SIZE}", 5)

    mod.unregister()
    left = {"panel": registered(bpy.types.Panel, PANEL),
            "group": registered(bpy.types.PropertyGroup, GROUP),
            "pointer": hasattr(bpy.types.Scene, ADDON_ID)}
    print(f"after unregister: {left}")
    if any(left.values()):
        # A surviving pointer is never read here: on 5.2.1 that crashed Blender.
        return fail(f"unregister() left {[k for k, v in left.items() if v]} behind", 6)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--drop-manifest", action="store_true",
                   help="falsification: the dual-format package loses its manifest")
    p.add_argument("--legacy-gets-manifest", action="store_true",
                   help="falsification: the bl_info-only package gains a manifest")
    p.add_argument("--skip-pointer", action="store_true",
                   help="falsification: register() never adds the Scene pointer")
    p.add_argument("--classes-first", action="store_true",
                   help="falsification: unregister the classes before deleting the pointer")
    args = p.parse_args(argv)

    work = tempfile.mkdtemp(prefix="addon_lifecycle_")
    try:
        code = run(work, args)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if code:
        return code
    print("addon-register-lifecycle OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
