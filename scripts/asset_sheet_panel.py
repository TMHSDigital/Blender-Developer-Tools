"""Blender side of ``scripts/asset_sheet.py``: one neutral asset-sheet panel.

Stages an example (or showcase piece) through its own documented ``--output``
path, captures the scene that was rendered, keeps only the hero asset's mesh
objects, then re-stages them alone: grey sweep, plain three-light studio,
three-quarter view fitted to the asset's real extent, no labels, no comparison
props. Renders one 640x360 panel. Isolating the asset from its staging is the
point of the gate — a strong scene can carry a weak model.

Not run directly. The host script passes everything through the environment
so the argv after ``--`` stays exactly the example's documented flags:

    BDT_SHEET_SCRIPT  path to the example's .py
    BDT_SHEET_SELECT  regex matched against mesh object names (the asset)
    BDT_SHEET_EXCLUDE optional regex of names to drop from that match
    BDT_SHEET_OUT     panel PNG to write
"""
import importlib.util
import math
import os
import re
import sys

import bmesh
import bpy
from mathutils import Vector

RES_X, RES_Y = 640, 360

script = os.environ["BDT_SHEET_SCRIPT"]
inc_re = os.environ["BDT_SHEET_SELECT"]
exc_re = os.environ.get("BDT_SHEET_EXCLUDE") or None
out_png = os.path.abspath(os.environ["BDT_SHEET_OUT"])

# examples import their shared helpers through a __file__-relative shim; the
# showcase ones do the same, so the module only needs to load from its path
spec = importlib.util.spec_from_file_location("sheet_mod", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

captured = []


@bpy.app.handlers.persistent
def _pre(scene, depsgraph=None):
    captured.append(scene.name)


bpy.app.handlers.render_pre.append(_pre)
code = mod.main()
bpy.app.handlers.render_pre.remove(_pre)
if code not in (None, 0):
    print(f"sheet: staging run exited {code}", file=sys.stderr)
    sys.exit(3)

sc = bpy.data.scenes[captured[-1]] if captured else bpy.context.scene
asset = [ob for ob in sc.objects
         if ob.type == "MESH" and re.search(inc_re, ob.name)
         and not (exc_re and re.search(exc_re, ob.name))]
print(f"sheet: asset objects {[ob.name for ob in asset]}")
if not asset:
    print(f"sheet: no mesh object matches {inc_re!r}", file=sys.stderr)
    sys.exit(4)

# The measurable floors of the isolated asset, as information for the
# calibration table in docs/VISUAL-STYLE.md § Asset quality. The gate itself
# runs on each example's own render path; nothing is enforced here.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "examples"))
import gallery_asset_quality as aq  # noqa: E402

parts, _ = aq.measure_parts(asset)
mats = aq.measure_materials(asset)[0]
edge90 = aq.measure_edge90(asset)[0]
print(f"sheet: floors parts={parts} materials={mats} edge90={edge90:.3f}")

# A skinned asset deforms through an Armature modifier whose rig is removed
# below; without this it would fall back to its rest pose (a scorpion with
# its tail stretched out flat). Bake the pose it was staged in.
_deps = bpy.context.evaluated_depsgraph_get()
for ob in asset:
    if any(m.type == "ARMATURE" for m in ob.modifiers):
        baked = bpy.data.meshes.new_from_object(ob.evaluated_get(_deps))
        ob.modifiers.clear()
        ob.data = baked

# Restage in place. Deleting the scene would wipe the datablocks the asset
# needs, so unparent the asset (world transform kept) and remove the rest.
for ob in asset:
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw
keep = set(asset)
for ob in list(sc.objects):
    if ob not in keep:
        bpy.data.objects.remove(ob, do_unlink=True)
bpy.context.view_layer.update()

mn, mx = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for ob in asset:
    for c in ob.bound_box:
        w = ob.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, w))
        mx = Vector(map(max, mx, w))
center = (mn + mx) / 2
dim = max((mx - mn).length, 0.1)

sweep = bpy.data.materials.new("Sweep")
sweep.use_nodes = True
bsdf = sweep.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.09, 0.09, 0.095, 1.0)
bsdf.inputs["Roughness"].default_value = 0.8
floor_me = bpy.data.meshes.new("SweepFloor")
bm = bmesh.new()
try:
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, mn.z))
    bm.to_mesh(floor_me)
finally:
    bm.free()
floor_me.materials.append(sweep)
sc.collection.objects.link(bpy.data.objects.new("SweepFloor", floor_me))

world = bpy.data.worlds.new("SheetWorld")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.035, 0.04, 1.0)
sc.world = world


def aim(ob, point):
    ob.rotation_euler = (point - ob.location).normalized().to_track_quat("-Z", "Y").to_euler()


def area(name, offset, energy, size, col):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size, ld.color = energy * (dim / 3) ** 2, size * dim, col
    ob = bpy.data.objects.new(name, ld)
    ob.location = center + Vector(offset) * dim * 1.5
    sc.collection.objects.link(ob)
    aim(ob, center)


area("Key", (-0.5, -0.7, 1.0), 500, 1.2, (1.0, 1.0, 1.0))
area("Fill", (0.9, -0.4, 0.5), 180, 1.6, (0.9, 0.95, 1.0))
area("Rim", (0.3, 0.9, 0.8), 280, 1.0, (1.0, 1.0, 1.0))

cam_data = bpy.data.cameras.new("SheetCam")
cam_data.lens, cam_data.sensor_width = 50, 36.0
cam = bpy.data.objects.new("SheetCam", cam_data)
# Fit the true extent at the real FOV rather than a bbox-diagonal guess, so
# tall and wide assets land at comparable scale across panels. Horizontal
# extent is the worst case: a 3/4 view can present either face.
hfov = 2.0 * math.atan(cam_data.sensor_width / (2.0 * cam_data.lens))
vfov = 2.0 * math.atan(cam_data.sensor_width * (RES_Y / RES_X) / (2.0 * cam_data.lens))
span = mx - mn
dist = max(math.hypot(span.x, span.y) / (2.0 * math.tan(hfov / 2.0)),
           max(span.z, 1e-3) / (2.0 * math.tan(vfov / 2.0))) * 1.18
cam.location = center + Vector((-0.55, -0.77, 0.38)).normalized() * dist
sc.collection.objects.link(cam)
aim(cam, center)
sc.camera = cam

sc.render.engine = "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"
sc.eevee.taa_render_samples = 32
sc.render.resolution_x, sc.render.resolution_y = RES_X, RES_Y
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = out_png
# Standard, as every gallery render: AgX would wash the panel toward grey
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
sc.view_settings.exposure = 0.0
sc.render.use_compositing = False
bpy.ops.render.render(write_still=True, scene=sc.name)
print(f"sheet: panel written {out_png}")
