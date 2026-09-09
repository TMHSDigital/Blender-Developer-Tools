# Cross-version property delete

A pair of machined specimen tags that witnesses the custom **ID-property**
delete contract from
[`cross-version-property-delete.py`](../../snippets/cross-version-property-delete.py)
and [`custom-properties`](../../skills/custom-properties/SKILL.md) — not the
snippet's `__main__`, which keys off `context.active_object` and prints
nothing in `--background`.

The IDs are built with `bpy.data.objects.new`. The Keep tag still carries
`["accession"] = 42` (emissive enamel). The Clear tag had `del obj["accession"]`
(empty pocket). Same `del` on 4.5 LTS and 5.x; there is no version branch.

**What it witnesses:** `property_unset` is a TypeError on a custom ID key and
does **not** remove it. `del id_block[key]` does. After factory-empty, there is
no `active_object`.

**What failure each check would catch:**

- exit 2 — someone set an active object; the snippet `__main__` would have
  been the only path
- exit 3 — the ID property never landed
- exit 4 — `property_unset` removed the key or failed to raise
- exit 7 — `del` did not run (`--skip-delete` / `--unset-instead` falsify
  this: measured `clear_has=True`)

## Run

```bash
blender --background --python cross_version_property_delete.py --
blender --background --python cross_version_property_delete.py -- --output tags.png
```

`--skip-delete` and `--unset-instead` are falsification switches: both leave
the Clear plate tagged and exit 7.

The `--output` render path measures framing against the Layer 1 band via
`examples/gallery_framing.py` (exit 10 on violation) before writing the still.
