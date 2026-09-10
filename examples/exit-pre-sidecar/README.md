# exit_pre sidecar

`bpy.app.handlers.exit_pre` writes `$BDT_SMOKE_SIDECAR` as Blender dies.
Witnesses [`drivers-and-app-handlers`](../../skills/drivers-and-app-handlers/SKILL.md).
`main` does not write the file. The host runner asserts it after the
process exits (`tests/smoke/run_example.py --expect-sidecar`).

5.1+. 4.5 LTS: `AttributeError` — no `exit_pre`. Skip
(`SMOKE_SKIP: exit_pre requires Blender 5.1+`, exit 77, catalog
`min_version` 5.1). `--force-run` bypasses the skip so 4.5 fails
accessing the handler list.

No gallery still. There is no geometry.

**What failure each check would catch:**

- exit 77 — Blender &lt; 5.1 and not `--force-run`
- exit 2 — `--force-run` on 4.5 (`exit_pre` missing)
- harness FAIL missing sidecar — `--silent-handler` / `--no-handler`
- harness FAIL wrong contents — `--wrong-text` (`nope`), `--write-in-main`
  (`from-main`), `--atexit-instead` (`atexit-ok`)

The harness checks **contents** (`sidecar_contains=exit_pre-ok`), not
existence only. A file written from `main` or `atexit` is red.

## Run

Via the harness (sets `$BDT_SMOKE_SIDECAR`):

```bash
python tests/smoke/run_example.py --name exit-pre-sidecar \
  --blender blender --script examples/exit-pre-sidecar/exit_pre_sidecar.py \
  --series 5.2 --min-version 5.1 \
  --expect-sidecar /tmp/exit-pre.sidecar --sidecar-contains exit_pre-ok
```
