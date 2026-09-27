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
    blender --background --python gn_sdf_remesh.py -- --no-sdf         # must fail
    blender --background --python gn_sdf_remesh.py -- --output r.png   # also render the result
    blender --background --python gn_sdf_remesh.py -- --output r.png --engine cycles  # GPU-less
"""
import bpy, sys, os, math, argparse

# Shared Layer 1 framing measurement (render path only) -- see
# gallery_framing.py for the __file__-relative import shim this relies on.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402

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

def build_vase_kit(name):
    """Render-only input: a vase blocked out the way a modeller kitbashes it --
    foot, belly, neck, lip and two handles as separate primitives that simply
    overlap, joined into one mesh with interior faces and hard intersection
    seams everywhere. Each part keeps its own bisque tone so the seams read.
    The same `build_remesh_via_sdf` tree then fuses it into one watertight
    shell: the thing an SDF remesh is actually for."""
    tones = [("Clay.Foot", (0.30, 0.13, 0.07)), ("Clay.Belly", (0.62, 0.30, 0.15)),
             ("Clay.Neck", (0.78, 0.62, 0.42)), ("Clay.Lip", (0.86, 0.78, 0.62)),
             ("Clay.Handle", (0.45, 0.20, 0.10))]
    mats = []
    for mname, rgb in tones:
        m = bpy.data.materials.new(mname); m.use_nodes = True
        mb = m.node_tree.nodes.get('Principled BSDF')
        mb.inputs['Base Color'].default_value = (*rgb, 1)
        mb.inputs['Roughness'].default_value = 0.85   # unfired clay: matte
        mats.append(m)
    parts = []

    def add(op, mat_i, **kw):
        op(**kw)
        ob = bpy.context.active_object
        ob.data.materials.append(mats[mat_i])
        for poly in ob.data.polygons:
            poly.use_smooth = True
        parts.append(ob)
        return ob

    add(bpy.ops.mesh.primitive_cylinder_add, 0, vertices=48, radius=0.42, depth=0.22,
        location=(0, 0, 0.11))
    belly = add(bpy.ops.mesh.primitive_uv_sphere_add, 1, segments=48, ring_count=24,
                radius=0.72, location=(0, 0, 0.82))
    belly.scale = (1.0, 1.0, 0.86)
    add(bpy.ops.mesh.primitive_cylinder_add, 2, vertices=40, radius=0.27, depth=0.72,
        location=(0, 0, 1.62))
    add(bpy.ops.mesh.primitive_torus_add, 3, major_segments=48, minor_segments=16,
        major_radius=0.30, minor_radius=0.075, location=(0, 0, 1.98))
    for sx in (-1.0, 1.0):
        add(bpy.ops.mesh.primitive_torus_add, 4, major_segments=40, minor_segments=14,
            major_radius=0.30, minor_radius=0.065, location=(sx * 0.58, 0, 1.36),
            rotation=(math.radians(90), 0, 0))
    with bpy.context.temp_override(active_object=parts[0], selected_editable_objects=parts,
                                   selected_objects=parts):
        bpy.ops.object.join()
    kit = parts[0]
    kit.name = name
    return kit


def render_still(obj, path, engine):
    import bmesh
    sc = bpy.context.scene
    # The torus the check measured leaves the stage; the render proves the
    # same tree on a subject where fusing is visible.
    bpy.context.collection.objects.unlink(obj)

    kit = build_vase_kit("VaseKit")
    glaze = bpy.data.materials.new("Glaze"); glaze.use_nodes = True
    g = glaze.node_tree.nodes.get('Principled BSDF')
    g.inputs['Base Color'].default_value = (0.03, 0.16, 0.30, 1)   # cobalt glaze
    g.inputs['Roughness'].default_value = 0.12
    try:
        g.inputs['Coat Weight'].default_value = 0.6
    except KeyError:
        pass
    fused = bpy.data.objects.new("VaseFused", kit.data.copy())
    bpy.context.collection.objects.link(fused)
    # Same builder, finer voxels than the check's 0.1 so the fused shell
    # holds the handles' profile; the glaze rides in on Set Material.
    tree, _ok = build_remesh_via_sdf(voxel_size=0.018, material=glaze)
    fused.modifiers.new("sdf", 'NODES').node_group = tree
    kit.location.x = -1.45
    fused.location.x = 1.45
    dg = bpy.context.evaluated_depsgraph_get()
    em = fused.evaluated_get(dg).to_mesh()
    fused_v = len(em.vertices)
    zmin = min(v.co.z for v in em.vertices)
    fused.evaluated_get(dg).to_mesh_clear()
    fused.location.z = -zmin + 0.12
    kit.location.z = -min(v.co.z for v in kit.data.vertices) + 0.12
    # the kit's own edges as a thin dark cage: UV rings and torus loops
    # running straight through each other, the topology the remesh replaces
    cage_mat = bpy.data.materials.new("Cage"); cage_mat.use_nodes = True
    cm = cage_mat.node_tree.nodes.get('Principled BSDF')
    cm.inputs['Base Color'].default_value = (0.05, 0.03, 0.02, 1)
    cm.inputs['Roughness'].default_value = 0.6
    cage = bpy.data.objects.new("VaseKitCage", kit.data.copy())
    cage.data.materials.clear(); cage.data.materials.append(cage_mat)
    for poly in cage.data.polygons:
        poly.material_index = 0
    cage.location = kit.location
    wire = cage.modifiers.new("cage", 'WIREFRAME')
    wire.thickness = 0.005; wire.offset = 1.0; wire.use_even_offset = True
    bpy.context.collection.objects.link(cage)
    print(f"render: kit_verts={len(kit.data.vertices)} fused_verts={fused_v} "
          f"kit_mats={len(kit.data.materials)}")

    # walnut potter's bats under each piece
    wood = bpy.data.materials.new("Walnut"); wood.use_nodes = True
    wn = wood.node_tree
    wb = wn.nodes.get('Principled BSDF')
    wave = wn.nodes.new('ShaderNodeTexWave'); wave.inputs['Scale'].default_value = 1.2
    wave.inputs['Distortion'].default_value = 1.5
    wave.inputs['Detail'].default_value = 4.0
    ramp = wn.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (0.13, 0.065, 0.03, 1)
    ramp.color_ramp.elements[1].color = (0.20, 0.105, 0.05, 1)
    wn.links.new(wave.outputs['Fac'], ramp.inputs['Fac'])
    wn.links.new(ramp.outputs['Color'], wb.inputs['Base Color'])
    wb.inputs['Roughness'].default_value = 0.5
    bats = []
    for x in (-1.45, 1.45):
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.95, depth=0.12,
                                            location=(x, 0, 0.06))
        bat = bpy.context.active_object
        bat.data.materials.append(wood)
        bev = bat.modifiers.new("bev", 'BEVEL'); bev.width = 0.025; bev.segments = 3
        bats.append(bat)

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

    aim = bpy.data.objects.new("Aim", None); aim.location = (0, 0, 1.05)
    bpy.context.collection.objects.link(aim)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 58.0
    cam.location = (0.9, -9.4, 3.0)
    bpy.context.collection.objects.link(cam); sc.camera = cam
    c = cam.constraints.new('TRACK_TO'); c.target = aim; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'

    def light(nm, loc, en, sz, col, target=aim):
        ld = bpy.data.lights.new(nm, 'AREA'); ld.energy = en; ld.size = sz; ld.color = col
        lo = bpy.data.objects.new(nm, ld); lo.location = loc
        bpy.context.collection.objects.link(lo)
        lc = lo.constraints.new('TRACK_TO'); lc.target = target
        lc.track_axis = 'TRACK_NEGATIVE_Z'; lc.up_axis = 'UP_Y'
    # shaped warm key, faint cool fill, cool rim for the glaze silhouette,
    # warm wedge raking the back wall (docs/VISUAL-STYLE.md)
    light("Key", (-4.5, -4.5, 5.0), 520, 3.0, (1.0, 0.95, 0.88))
    light("Fill", (5, -4, 2.2), 90, 7.0, (0.75, 0.85, 1.0))
    light("Rim", (2.5, 3.5, 4.0), 260, 2.5, (0.62, 0.78, 1.0))
    wd = bpy.data.lights.new("Wedge", 'AREA'); wd.energy = 520; wd.size = 6.0
    wd.color = (1.0, 0.72, 0.45)
    wo = bpy.data.objects.new("Wedge", wd); wo.location = (2.5, 5.5, 4.0)
    wo.rotation_euler = (math.radians(-68), 0, math.radians(190))
    bpy.context.collection.objects.link(wo)

    sc.render.engine = 'CYCLES' if engine == 'cycles' else get_eevee_engine_id()
    if sc.render.engine == 'CYCLES':
        try: sc.cycles.samples = 32
        except Exception: pass
    else:
        try: sc.eevee.taa_render_samples = 64
        except Exception: pass
    sc.render.resolution_x = 1280; sc.render.resolution_y = 720
    # Blender resolves a relative filepath against the blend-file directory, which
    # for a --background run with no .blend is the drive root, not the cwd.
    path = os.path.abspath(path)
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = path
    # AgX would wash the cobalt glaze toward slate (docs/VISUAL-STYLE.md)
    sc.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate before the beauty render (exit 10 on violation)
    fcode = gallery_framing.check_framing(sc, cam, hero=[kit, fused],
                                          elements=[kit, fused] + bats, stage=[floor, wall])
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 4


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render the remeshed result to this PNG")
    p.add_argument("--engine", choices=["auto", "cycles"], default="auto")
    p.add_argument("--no-sdf", action="store_true",
                   help="skip attaching the SDF remesh modifier (must fail)")
    args = p.parse_args(argv)

    # EEVEE-id inversion witnessed for real: the OTHER era's id must be
    # rejected by this build, the helper's accepted
    eid = get_eevee_engine_id()
    wrong = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE'  # engine-id-exempt: the wrong-era id this example asserts is rejected
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
    if not args.no_sdf:
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
        rcode = render_still(obj, args.output, args.engine)
        if rcode:
            if rcode == 4:
                print("ERROR: render produced no file", file=sys.stderr)
            return rcode
        print(f"rendered {args.output} ({os.path.getsize(args.output)} bytes)")
    print("gn-sdf-remesh OK")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        import traceback; traceback.print_exc()
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr); sys.exit(1)
