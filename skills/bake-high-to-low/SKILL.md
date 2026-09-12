---
name: bake-high-to-low
description: Cage-bake high-poly surface detail onto a low-poly target as a tangent-space normal map. Cycles CPU, selected-to-active, active image node, UV layer, save_render. Targets 5.2 LTS with 4.5 LTS fallback.
standards-version: 1.10.0
---

# Bake High to Low

## Trigger

Use this skill when the user:

- Wants a tangent-space normal map from a dense source onto a game-resolution mesh
- Mentions cage bake, `use_selected_to_active`, `cage_extrusion`, or `bpy.ops.object.bake`
- Has an LOD from `DECIMATE COLLAPSE` (or a retopo) and needs the missing surface detail in a map
- Is about to call bake from EEVEE, on GPU in CI, or with `bake_type=`

This skill is the bake step. It composes `ai-mesh-cleanup` (identity scale, applied transforms, a UV layer that already exists) and the LOD contract in `examples/lod-decimate-chain/` / `snippets/decimate_to_budget.py` (collapse onto a budget; UVs survive well enough to bake). It does not unwrap, transfer UVs, or pack an atlas — those are a later phase. It does not generate meshes.

## The core misunderstanding

Baking is not a render. EEVEE has no bake path. The operator writes into the **active Image Texture node** of the **active** object's material, not into a file and not into "the selected image datablock." A missing UV layer, the wrong object active, or a node that is not `nodes.active` finishes without error and leaves a blank or unchanged image.

The pass type RNA is `type`, not `bake_type`. `bake_type` is not on `bpy.ops.object.bake`. Passing it is a TypeError.

Cycles bake is stochastic. Pixel buffers are not byte-identical across 4.5 / 5.1 / 5.2, even at one sample on CPU. Assert with tolerances and a flat-source control, not a hash.

## RNA (verified)

Live dump of `bpy.ops.object.bake.get_rna_type()` on 4.5.11 LTS, 5.1.2, and 5.2.1 LTS: **22 properties, identical identifiers and enums.** No version shim. The kwargs below are the contract.

Docs:

- 5.2: https://docs.blender.org/api/current/bpy.ops.object.html#bpy.ops.object.bake
- 5.1: https://docs.blender.org/api/5.1/bpy.ops.object.html#bpy.ops.object.bake
- 4.5: https://docs.blender.org/api/4.5/bpy.ops.object.html#bpy.ops.object.bake

`cage_object` is a **string name**, never an Object pointer.

## The canonical pattern

Every step is a silent-failure point. Do them in this order.

### 1. Engine and device

```python
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.cycles.use_denoising = False
```

Do not rely on the default device. Headless CI has no GPU. `samples = 1` is enough for a statistical check; raise it for production maps, not for smoke.

### 2. Target: UV layer, image, active Image Texture node

The low-poly object needs a UV layer (`mesh.uv_layers`). Confirm it; do not unwrap here.

```python
img = bpy.data.images.new("BakeNrm", 128, 128, alpha=True, float_buffer=False)
img.colorspace_settings.name = "Non-Color"

mat = bpy.data.materials.new("BakeTarget")
mat.use_nodes = True
nodes = mat.node_tree.nodes
tex = nodes.new("ShaderNodeTexImage")
tex.image = img
nodes.active = tex
tex.select = True

if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)
```

The Image Texture does **not** need to be linked into Principled for the bake to land. It must be `nodes.active`. After the bake, wire `ShaderNodeNormalMap` for display or export; do not plug Image Texture Color into Principled Normal.

Snippet: `snippets/setup_bake_target_image.py`.

### 3. Selection: high selected, low active

```python
high.select_set(True)
low.select_set(True)
bpy.context.view_layer.objects.active = low
```

`use_selected_to_active=True` bakes **selected** sources onto the **active** target. Reverse that and the map is empty or self-bakes the low.

### 4. Cage normal bake

```python
result = bpy.ops.object.bake(
    type="NORMAL",
    use_selected_to_active=True,
    cage_extrusion=0.20,
    use_cage=False,
    normal_space="TANGENT",
    margin=4,
    margin_type="ADJACENT_FACES",
    use_clear=True,
    target="IMAGE_TEXTURES",
)
```

`cage_extrusion` inflates the active object along its normals so rays hit the high mesh. It must clear the high-frequency amplitude (ribs at 0.10 need extrusion > 0.10; 0.20 is the worked value). If extrusion alone skims past concavities, set `use_cage=True` and `cage_object="CageName"` (the object's `.name`). Do not pass the Object.

`margin_type` is `ADJACENT_FACES` or `EXTEND`. Prefer `ADJACENT_FACES` at UV seams.

Snippet: `snippets/bake_normal_high_to_low.py`.

### 5. Save the datablock

The bake writes the image **in memory**. `Image.save()` on a `GENERATED` image flips `source` to `'FILE'` and drops the buffer — the trap `examples/image-pixels-testcard/` witnesses. Use `save_render()`:

```python
img.file_format = "PNG"
img.save_render(filepath)
```

Snippet: `snippets/save_baked_image.py`. Folded save is the wrong size: the trap is its own contract.

## Common mistakes

| Wrong | Right |
| --- | --- |
| `bake_type='NORMAL'` | `type='NORMAL'` |
| `scene.render.engine = 'BLENDER_EEVEE'` then bake | `CYCLES` only |
| GPU / default device in CI | `scene.cycles.device = 'CPU'` |
| Low selected, high active | High selected, low **active** |
| Image Texture present but not `nodes.active` | Set `nodes.active = tex` |
| No UV layer | Confirm `mesh.uv_layers` before bake |
| `Image.save()` after bake | `Image.save_render(path)` |
| Hash / byte-compare maps across versions | Fraction / MAD vs `(0.5, 0.5, 1.0)` plus a flat-source control |

## Version notes

Bake operator RNA is identical on 4.5 LTS, 5.1, and 5.2 LTS. Branch on `bpy.app.version` only for unrelated neighbors (EEVEE engine id for a gallery still, NodesModifier inputs). Do not invent a bake shim.

Witness: `examples/bake-normal-high-to-low/`. `--flat-source` feeds an undisplaced high into the same detail assertion and must exit non-zero.
