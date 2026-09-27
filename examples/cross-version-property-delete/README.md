# Cross-version property delete

A pair of stage lamps that witnesses the custom **ID-property**
delete contract from
[`cross-version-property-delete.py`](../../snippets/cross-version-property-delete.py)
and [`custom-properties`](../../skills/custom-properties/SKILL.md) — not the
snippet's `__main__`, which keys off `context.active_object` and prints
nothing in `--background`.

The IDs are two stage-lamp housings built with `bpy.data.objects.new`. The
Keep lamp still carries `["accession"] = 42`; the Clear lamp had
`del obj["accession"]`. Same `del` on 4.5 LTS and 5.x; there is no version
branch.

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

Both lamps hang in U-yokes from one T-stand. The render path reads each
housing's `keys()` after the check has run, so the still is driven by the
checked IDs, not staged from the expected outcome. A lamp that still
carries the property gets an emissive lens and a real SPOT light along its
beam axis, which pools warm light on the placard below it. A lamp without
the property keeps a dark lens and casts nothing. Each placard is set in
the bundled DejaVu Sans Mono and shows the line of code that produced its
lamp's state. Only render-side geometry (stand, yokes, lenses, placards) is
added in the render path; the check reads ID properties, never geometry.

## Run

```bash
blender --background --python cross_version_property_delete.py --
blender --background --python cross_version_property_delete.py -- --output lamps.png
```

`--skip-delete` and `--unset-instead` are falsification switches: both leave
the Clear lamp tagged and exit 7.

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
| 6 | Keep lamp lost the ID property |
| 7 | Clear lamp still has the ID property (`--skip-delete` / `--unset-instead` land here) |
| 10 | Gallery framing violation |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--skip-delete`, or `--unset-instead`.
