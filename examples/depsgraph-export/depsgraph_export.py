"""Candidate B: depsgraph-evaluated export (SCRATCH).

Witnesses the depsgraph lifetime contract AND that modifiers actually ship in exports. Builds
a cube with a SUBSURF modifier, measures the evaluated mesh via evaluated_get().to_mesh()
(paired with to_mesh_clear()), exports through wm.obj_export, and asserts the exported vertex
count equals the EVALUATED (modifier-applied) count and is strictly greater than the base.
"""
import bpy, bmesh, sys, os, argparse

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: write the exported OBJ here (else a temp path)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Cube"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new("Cube", me); bpy.context.collection.objects.link(obj)
    obj.modifiers.new("ss", 'SUBSURF').levels = 2
    base = len(obj.data.vertices)

    # depsgraph lifetime contract: evaluate, read, then release with to_mesh_clear
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    eval_vcount = len(em.vertices)
    ev.to_mesh_clear()  # must be paired; releases the temporary mesh

    import tempfile
    out = args.output or os.path.join(tempfile.gettempdir(), "depsgraph_export.obj")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    # obj_export writes the evaluated (modifier-applied) geometry by default
    bpy.ops.wm.obj_export(filepath=out, export_selected_objects=False)
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        print("ERROR: no OBJ written", file=sys.stderr); return 4
    exported = 0
    with open(out) as f:
        for line in f:
            if line.startswith("v "): exported += 1

    print(f"base_vcount={base} eval_vcount={eval_vcount} exported_vcount={exported}")
    if not (eval_vcount > base):
        print("ERROR: evaluated mesh did not apply the modifier", file=sys.stderr); return 3
    if exported != eval_vcount:
        print(f"ERROR: export ({exported}) != evaluated ({eval_vcount}); modifier did not ship",
              file=sys.stderr); return 5
    print("depsgraph-export OK")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
