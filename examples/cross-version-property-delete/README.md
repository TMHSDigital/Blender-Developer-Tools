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

## Staging

The two tags now hang from the stand's bar on steel rods. The bar used
to run 0.17 m behind the plates with nothing joining them, and the
"rings" were solid discs, so the plates hung on air. The bar spans both
plates, the post rises to it, and the base is as wide as what it
carries. Render path only: the check reads ID properties, never
geometry.

## Run

```bash
blender --background --python cross_version_property_delete.py --
blender --background --python cross_version_property_delete.py -- --output tags.png
```

`--skip-delete` and `--unset-instead` are falsification switches: both leave
the Clear plate tagged and exit 7.

The `--output` render path measures framing against the Layer 1 band via
`examples/gallery_framing.py` (exit 10 on violation) before writing the still.

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage; also an active object existed after the data-API build |
| 3 | Custom ID property did not land |
| 4 | `property_unset` on a custom ID key did not TypeError, or it deleted the key |
| 5 | `del` did not report removal |
| 6 | Keep plate lost the ID property |
| 7 | Clear plate still has the ID property (`--skip-delete` / `--unset-instead` land here) |
| 10 | Gallery framing violation |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--skip-delete`, or `--unset-instead`.
