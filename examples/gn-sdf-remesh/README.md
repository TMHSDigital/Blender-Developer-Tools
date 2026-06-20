# Geometry Nodes SDF Remesh

A runnable example that remeshes an input mesh through an OpenVDB SDF grid using the
`build_remesh_via_sdf` pattern from the
[`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md) skill:
`GeometryNodeMeshToSDFGrid` → `GeometryNodeGridToMesh` at the SDF zero-level, attached as a
NODES modifier and evaluated via the depsgraph.

**Which fix it witnesses:** an SDF grid is meshed with **Grid to Mesh**, not Volume to Mesh
(the `Mesh to SDF Grid` output is a grid socket; `Volume to Mesh` takes a volume-geometry
socket, so wiring the grid there is an invalid link that yields no geometry). `Grid to Mesh`
has the matching grid input.

## Run

```bash
# Cheap correctness check only (no render) — the CI smoke check:
blender --background --python gn_sdf_remesh.py --

# Also render the remeshed result (EEVEE on a GPU host; --engine cycles on GPU-less hosts):
blender --background --python gn_sdf_remesh.py -- --output remesh.png
blender --background --python gn_sdf_remesh.py -- --output remesh.png --engine cycles
```

By default it runs only the **frame-independent correctness check**: the depsgraph-evaluated
vertex count must be > 0 AND differ from the base mesh (the remesh produced geometry). It
exits non-zero on failure — the same check the `blender-smoke` workflow runs on Blender 4.5
LTS and 5.1.
