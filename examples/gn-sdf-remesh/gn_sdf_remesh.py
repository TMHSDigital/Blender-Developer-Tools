"""Geometry Nodes SDF remesh -- a runnable BDT example.

Builds the `build_remesh_via_sdf` pattern from the geometry-nodes-python skill
(`GeometryNodeMeshToSDFGrid` -> `GeometryNodeGridToMesh` at the SDF zero-level), attaches it
as a NODES modifier to an input mesh, and evaluates via the depsgraph. It witnesses the F2
fix: an SDF grid is meshed with **Grid to Mesh**, not Volume to Mesh.

By default it runs only the cheap, frame-independent correctness check (no render): the
evaluated vertex count must be > 0 AND differ from the base mesh -- proving the remesh
produced geometry. Exits non-zero on failure. This is the check the CI smoke gate runs on
both builds.

    blender --background --python gn_sdf_remesh.py --                  # correctness check only
    blender --background --python gn_sdf_remesh.py -- --output r.png   # also render the result
    blender --background --python gn_sdf_remesh.py -- --output r.png --engine cycles  # GPU-less
"""
import bpy, sys, os, argparse

def get_eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'

def build_remesh_via_sdf(voxel_size=0.1, threshold=0.0, material=None):
    tree = bpy.data.node_groups.new("SDFRemesh", 'GeometryNodeTree')
    tree.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi = tree.nodes.new('NodeGroupInput'); go = tree.nodes.new('NodeGroupOutput')
    mesh_to_sdf = tree.nodes.new('GeometryNodeMeshToSDFGrid')
    grid_to_mesh = tree.nodes.new('GeometryNodeGridToMesh')
    mesh_to_sdf.inputs["Voxel Size"].default_value = voxel_size
    grid_to_mesh.inputs["Threshold"].default_value = threshold
    tree.links.new(gi.outputs["Geometry"], mesh_to_sdf.inputs["Mesh"])
    link = tree.links.new(mesh_to_sdf.outputs["SDF Grid"], grid_to_mesh.inputs["Grid"])
    # GN-generated geometry carries no material, so the input mesh's material is dropped on
    # remesh. Re-apply it inside the tree with a Set Material node (the GN-native fix).
    out_socket = grid_to_mesh.outputs["Mesh"]
    if material is not None:
        set_mat = tree.nodes.new('GeometryNodeSetMaterial')
        set_mat.inputs["Material"].default_value = material
        tree.links.new(out_socket, set_mat.inputs["Geometry"])
        out_socket = set_mat.outputs["Geometry"]
    tree.links.new(out_socket, go.inputs["Geometry"])
    return tree, link.is_valid

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_torus_add(location=(0, 0, 1.0), major_radius=1.2, minor_radius=0.5)
    obj = bpy.context.active_object
    for p in obj.data.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new("Clay"); mat.use_nodes = True
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (0.45, 0.55, 0.85, 1)
    b.inputs['Roughness'].default_value = 0.45
    obj.data.materials.append(mat)
    return obj

def render_still(obj, path, engine):
    import bmesh
    sc = bpy.context.scene
    fme = bpy.data.meshes.new("Floor"); bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0); bm.to_mesh(fme); bm.free()
    floor = bpy.data.objects.new("Floor", fme); bpy.context.collection.objects.link(floor)
    w = bpy.data.worlds.new("W"); w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.06, 0.08, 1); sc.world = w
    aim = bpy.data.objects.new("Aim", None); aim.location = (0, 0, 1.0); bpy.context.collection.objects.link(aim)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.location = (0, -6.5, 3.0)
    bpy.context.collection.objects.link(cam); sc.camera = cam
    c = cam.constraints.new('TRACK_TO'); c.target = aim; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
    for nm, loc, en in [("K", (-4, -5, 7), 900), ("F2", (5, -4, 2), 350)]:
        ld = bpy.data.lights.new(nm, 'AREA'); ld.energy = en; ld.size = 5.0
        lo = bpy.data.objects.new(nm, ld); lo.location = loc; bpy.context.collection.objects.link(lo)
        lc = lo.constraints.new('TRACK_TO'); lc.target = aim; lc.track_axis = 'TRACK_NEGATIVE_Z'; lc.up_axis = 'UP_Y'
    sc.render.engine = 'CYCLES' if engine == 'cycles' else get_eevee_engine_id()
    if sc.render.engine == 'CYCLES':
        try: sc.cycles.samples = 16
        except Exception: pass
    else:
        try: sc.eevee.taa_render_samples = 16
        except Exception: pass
    sc.render.resolution_x = 1280; sc.render.resolution_y = 720
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render the remeshed result to this PNG")
    p.add_argument("--engine", choices=["auto", "cycles"], default="auto")
    args = p.parse_args(argv)

    eid = get_eevee_engine_id()
    expected = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'
    bpy.context.scene.render.engine = eid
    if bpy.context.scene.render.engine != expected:
        print(f"ERROR: EEVEE id {eid} != expected {expected}", file=sys.stderr); return 5

    obj = build()
    base = len(obj.data.vertices)
    src_mat = obj.data.materials[0] if obj.data.materials else None
    tree, link_valid = build_remesh_via_sdf(material=src_mat)
    obj.modifiers.new("sdf", 'NODES').node_group = tree
    dg = bpy.context.evaluated_depsgraph_get(); ev = obj.evaluated_get(dg)
    m = ev.to_mesh(); evc = len(m.vertices)
    mat_names = [mm.name for mm in m.materials if mm is not None]
    ev.to_mesh_clear()
    print(f"link_valid={link_valid} base_vcount={base} eval_vcount={evc} materials={mat_names}")
    if not (link_valid and evc > 0 and evc != base):
        print("ERROR: SDF remesh produced no/unchanged geometry", file=sys.stderr); return 3
    # the Set Material node must carry the input material onto the remeshed result
    if src_mat is not None and src_mat.name not in mat_names:
        print(f"ERROR: material '{src_mat.name}' dropped by remesh", file=sys.stderr); return 6

    if args.output:
        if not render_still(obj, args.output, args.engine):
            print("ERROR: render produced no file", file=sys.stderr); return 4
        print(f"rendered {args.output} ({os.path.getsize(args.output)} bytes)")
    print("gn-sdf-remesh OK")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        import traceback; traceback.print_exc()
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr); sys.exit(1)
