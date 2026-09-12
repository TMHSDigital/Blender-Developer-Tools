# AI asset pipeline template.
#
# Run with:
#   blender --background --python pipeline.py -- \
#       --input /path/to/source.glb \
#       --outdir /path/to/out \
#       --preset unity \
#       --lod-budgets 1024,256,64 \
#       --collider convex \
#       --draco
#
# Everything after the `--` token is forwarded to this script as sys.argv.
# Anything before `--` is consumed by Blender itself.
#
# GLB in, engine-ready LOD set plus optional collider out. Provider-agnostic.
# Templates are standalone (not a package). Helpers below are duplicated from:
#   snippets/decimate_to_budget.py  (evaluated_triangle_count, decimate_to_budget)
#   snippets/lod_chain.py           (make_lod_chain; itself duplicates the above)
#   snippets/convex_hull_collider.py
#   snippets/export_preset_unity.py / export_preset_godot.py / export_preset_unreal.py
# Cleanup order follows skills/ai-mesh-cleanup/SKILL.md.
# Exit codes follow templates/headless-batch-script-template/script.py:
#   0 success, 2+ distinct failure modes, argparse usage also exits 2.
#
# References:
#   docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
#   docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
#   docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx

import argparse
import os
import sys

import bmesh
import bpy


def parse_args(argv):
    """Parse args after the `--` separator that Blender passes through."""
    if "--" in argv:
        script_args = argv[argv.index("--") + 1:]
    else:
        script_args = []

    parser = argparse.ArgumentParser(
        description="Import a GLB, clean it, emit LODs and a collider, export.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the source .glb file.",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Directory to write LOD and collider files into.",
    )
    parser.add_argument(
        "--preset",
        required=True,
        choices=["unity", "godot", "unreal"],
        help="Engine export preset.",
    )
    parser.add_argument(
        "--lod-budgets",
        default="1024,256,64",
        help="Comma-separated decreasing triangle budgets (default: 1024,256,64).",
    )
    parser.add_argument(
        "--collider",
        choices=["convex", "box", "none"],
        default="convex",
        help="Collider to emit (default: convex).",
    )
    parser.add_argument(
        "--draco",
        action="store_true",
        help="Enable glTF Draco mesh compression on export.",
    )
    return parser.parse_args(script_args)


def parse_budgets(text):
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return None
    try:
        budgets = [int(p) for p in parts]
    except ValueError:
        return None
    if any(b <= 0 for b in budgets):
        return None
    if any(budgets[i] <= budgets[i + 1] for i in range(len(budgets) - 1)):
        return None
    return budgets


def scene_units_are_meters(scene):
    units = scene.unit_settings
    if units.system not in {"METRIC", "NONE"}:
        return False
    return abs(units.scale_length - 1.0) < 1e-6


def scale_is_identity(obj, tol=1e-6):
    sx, sy, sz = obj.scale
    return abs(sx - 1.0) < tol and abs(sy - 1.0) < tol and abs(sz - 1.0) < tol


def apply_object_transform(obj):
    with bpy.context.temp_override(
        object=obj, active_object=obj, selected_objects=[obj]
    ):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def origin_to_base(obj):
    mesh = obj.data
    n = len(mesh.vertices)
    if n == 0:
        return
    flat = [0.0] * (n * 3)
    mesh.vertices.foreach_get("co", flat)
    min_z = min(flat[2::3])
    for i in range(n):
        flat[i * 3 + 2] -= min_z
    mesh.vertices.foreach_set("co", flat)
    mesh.update()
    obj.location.z += min_z


def recalc_normals(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        obj.data.update()
    finally:
        bm.free()


def evaluated_triangle_count(obj):
    # Duplicated from snippets/decimate_to_budget.py
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def decimate_to_budget(obj, target_tris):
    # Duplicated from snippets/decimate_to_budget.py
    current = evaluated_triangle_count(obj)
    if current == 0 or current <= target_tris:
        return None
    ratio = min(1.0, target_tris / current)
    mod = obj.modifiers.new("DecimateBudget", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    return mod


def make_lod_chain(obj, budgets):
    # Duplicated from snippets/lod_chain.py
    lods = []
    for i, budget in enumerate(budgets):
        mesh = obj.data.copy()
        lod = bpy.data.objects.new(f"{obj.name}_LOD{i}", mesh)
        lod.matrix_world = obj.matrix_world.copy()
        bpy.context.scene.collection.objects.link(lod)
        decimate_to_budget(lod, budget)
        lods.append(lod)
    return lods


def convex_hull_collider(obj, name=None):
    # Duplicated from snippets/convex_hull_collider.py
    mesh = bpy.data.meshes.new(name or f"{obj.name}_Collider")
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        result = bmesh.ops.convex_hull(bm, input=bm.verts)
        interior = result.get("geom_interior") or []
        unused = result.get("geom_unused") or []
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        if unused:
            bmesh.ops.delete(bm, geom=unused, context="VERTS")
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    collider = bpy.data.objects.new(name or f"{obj.name}_Collider", mesh)
    bpy.context.scene.collection.objects.link(collider)
    collider.matrix_world = obj.matrix_world.copy()
    return collider


def box_collider(obj, name=None):
    mesh_in = obj.data
    n = len(mesh_in.vertices)
    if n == 0:
        return None
    flat = [0.0] * (n * 3)
    mesh_in.vertices.foreach_get("co", flat)
    xs, ys, zs = flat[0::3], flat[1::3], flat[2::3]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    size = (max_x - min_x, max_y - min_y, max_z - min_z)
    center = (
        0.5 * (min_x + max_x),
        0.5 * (min_y + max_y),
        0.5 * (min_z + max_z),
    )
    mesh = bpy.data.meshes.new(name or f"{obj.name}_BoxCollider")
    bm = bmesh.new()
    try:
        geom = bmesh.ops.create_cube(bm, size=1.0)
        for vert in geom["verts"]:
            vert.co.x = vert.co.x * size[0] + center[0]
            vert.co.y = vert.co.y * size[1] + center[1]
            vert.co.z = vert.co.z * size[2] + center[2]
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    collider = bpy.data.objects.new(name or f"{obj.name}_BoxCollider", mesh)
    bpy.context.collection.objects.link(collider)
    collider.matrix_world = obj.matrix_world.copy()
    return collider


def apply_selected_mesh_transforms():
    # Duplicated from snippets/export_preset_unity.py
    for obj in list(bpy.context.selected_objects):
        if obj.type != "MESH":
            continue
        apply_object_transform(obj)


def select_only(obj):
    for other in bpy.data.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def export_preset(filepath, preset, draco):
    apply_selected_mesh_transforms()
    if preset == "unity":
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True,
            export_yup=True,
            export_apply=True,
            export_draco_mesh_compression_enable=draco,
            export_animations=False,
        )
        return
    if preset == "godot":
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True,
            export_yup=False,
            export_apply=True,
            export_draco_mesh_compression_enable=draco,
            export_animations=False,
        )
        return
    for obj in list(bpy.context.selected_objects):
        if obj.type != "MESH":
            continue
        obj.scale = (
            obj.scale[0] * 100.0,
            obj.scale[1] * 100.0,
            obj.scale[2] * 100.0,
        )
    apply_selected_mesh_transforms()
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_draco_mesh_compression_enable=draco,
        export_animations=False,
    )


def glb_magic_ok(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == b"glTF"
    except OSError:
        return False


def main():
    args = parse_args(sys.argv)

    budgets = parse_budgets(args.lod_budgets)
    if budgets is None:
        print(
            "ERROR: --lod-budgets must be comma-separated positive ints, strictly decreasing",
            file=sys.stderr,
        )
        return 4

    if not os.path.isfile(args.input):
        print(f"ERROR: input file missing: {args.input}", file=sys.stderr)
        return 2

    if not glb_magic_ok(args.input):
        print(f"ERROR: input is not a readable GLB: {args.input}", file=sys.stderr)
        return 3

    if not os.path.isdir(args.outdir):
        print(f"ERROR: outdir is not a directory: {args.outdir}", file=sys.stderr)
        return 6

    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.import_scene.gltf(filepath=args.input.replace("\\", "/"))
    except RuntimeError as exc:
        print(f"ERROR: glTF import failed: {exc}", file=sys.stderr)
        return 3

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not meshes:
        print("ERROR: no mesh objects in the input GLB", file=sys.stderr)
        return 5

    print(f"Found {len(meshes)} mesh object(s): {[o.name for o in meshes]}")

    scene = bpy.context.scene
    if not scene_units_are_meters(scene):
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        print("Set scene units to metric meters")

    hero = max(meshes, key=evaluated_triangle_count)
    if not scale_is_identity(hero):
        apply_object_transform(hero)
        print(f"Applied object scale/rotation on {hero.name}")
    origin_to_base(hero)
    recalc_normals(hero)
    src_tris = evaluated_triangle_count(hero)
    print(f"evaluated_tris={src_tris} object={hero.name}")

    lods = make_lod_chain(hero, budgets)
    for lod, budget in zip(lods, budgets):
        print(
            f"{lod.name} budget={budget} evaluated_tris={evaluated_triangle_count(lod)}"
        )

    collider = None
    if args.collider == "convex":
        collider = convex_hull_collider(hero)
        print(f"collider={collider.name} verts={len(collider.data.vertices)}")
    elif args.collider == "box":
        collider = box_collider(hero)
        print(f"collider={collider.name} verts={len(collider.data.vertices)}")

    written = []
    try:
        for i, lod in enumerate(lods):
            select_only(lod)
            path = os.path.join(args.outdir, f"lod{i}.glb").replace("\\", "/")
            export_preset(path, args.preset, args.draco)
            written.append(path)
            print(f"Wrote {path}")
        if collider is not None:
            select_only(collider)
            path = os.path.join(args.outdir, "collider.glb").replace("\\", "/")
            export_preset(path, args.preset, args.draco)
            written.append(path)
            print(f"Wrote {path}")
    except RuntimeError as exc:
        print(f"ERROR: glTF export failed: {exc}", file=sys.stderr)
        return 6

    for path in written:
        if not (os.path.isfile(path) and os.path.getsize(path) > 0):
            print(f"ERROR: export produced no file: {path}", file=sys.stderr)
            return 6

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
