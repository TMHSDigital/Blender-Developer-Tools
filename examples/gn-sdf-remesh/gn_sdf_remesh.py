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
import bpy, sys, os, math, argparse

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
    bpy.ops.mesh.primitive_torus_add(location=(0, 0, 0.55), major_radius=1.2, minor_radius=0.5)
    obj = bpy.context.active_object
    for p in obj.data.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new("Ceramic"); mat.use_nodes = True
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (0.45, 0.025, 0.05, 1)  # crimson ceramic
    b.inputs['Roughness'].default_value = 0.16  # glossy: the SDF facets read by their glints
    obj.data.materials.append(mat)
    return obj

def render_still(obj, path, engine):
    import bmesh
    sc = bpy.context.scene
    fme = bpy.data.meshes.new("Floor"); bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0); bm.to_mesh(fme)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Studio"); fmat.use_nodes = True
    fb = fmat.node_tree.nodes.get('Principled BSDF')
    fb.inputs['Base Color'].default_value = (0.03, 0.032, 0.037, 1)  # dark staged studio
    fb.inputs['Roughness'].default_value = 0.7
    fme.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", fme); bpy.context.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", fme.copy()); wall.location = (0, 9.0, 0)
    wall.rotation_euler = (1.5708, 0, 0); bpy.context.collection.objects.link(wall)
    w = bpy.data.worlds.new("W"); w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.021, 0.025, 1); sc.world = w
    aim = bpy.data.objects.new("Aim", None); aim.location = (0, 0, 0.5); bpy.context.collection.objects.link(aim)
    # off-axis and low: the remesh facets are the API evidence, and they only
    # read when a raking key skims them from the side
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.location = (2.6, -5.2, 1.5)
    bpy.context.collection.objects.link(cam); sc.camera = cam
    c = cam.constraints.new('TRACK_TO'); c.target = aim; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
    # low raking warm key so every facet catches a distinct glint, faint cool
    # fill (docs/VISUAL-STYLE.md)
    for nm, loc, en, sz, col in [("K", (-5, -3.5, 2.8), 480, 3.0, (1.0, 0.96, 0.9)),
                                 ("F2", (5, -4, 2), 110, 7.0, (0.75, 0.85, 1.0))]:
        ld = bpy.data.lights.new(nm, 'AREA'); ld.energy = en; ld.size = sz; ld.color = col
        lo = bpy.data.objects.new(nm, ld); lo.location = loc; bpy.context.collection.objects.link(lo)
        lc = lo.constraints.new('TRACK_TO'); lc.target = aim; lc.track_axis = 'TRACK_NEGATIVE_Z'; lc.up_axis = 'UP_Y'
    # warm wedge raking the back wall, aimed past the torus at the wall
    wd = bpy.data.lights.new("Wedge", 'AREA'); wd.energy = 380; wd.size = 6.0; wd.color = (1.0, 0.76, 0.5)
    wo = bpy.data.objects.new("Wedge", wd); wo.location = (2.5, 5.5, 4.0)
    wo.rotation_euler = (math.radians(-68), 0, math.radians(190)); bpy.context.collection.objects.link(wo)
    sc.render.engine = 'CYCLES' if engine == 'cycles' else get_eevee_engine_id()
    if sc.render.engine == 'CYCLES':
        try: sc.cycles.samples = 32
        except Exception: pass
    else:
        try: sc.eevee.taa_render_samples = 64
        except Exception: pass
    sc.render.resolution_x = 1280; sc.render.resolution_y = 720
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = path
    # AgX would wash the crimson toward brick (docs/VISUAL-STYLE.md)
    sc.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render the remeshed result to this PNG")
    p.add_argument("--engine", choices=["auto", "cycles"], default="auto")
    args = p.parse_args(argv)

    # EEVEE-id inversion witnessed for real: the OTHER era's id must be
    # rejected by this build, the helper's accepted
    eid = get_eevee_engine_id()
    wrong = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE'
    try:
        bpy.context.scene.render.engine = wrong
        print(f"ERROR: wrong-era EEVEE id '{wrong}' was accepted", file=sys.stderr); return 5
    except TypeError:
        pass  # correctly rejected
    bpy.context.scene.render.engine = eid  # raises TypeError if the helper's id is invalid

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
