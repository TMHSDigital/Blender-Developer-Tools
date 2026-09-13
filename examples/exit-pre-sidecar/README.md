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

The harness checks **contents** (`sidecar_contains=exit_pre-ok`), not
existence only. A file written from `main` or `atexit` is red. Several
falsifiers exit 0 from the script so the **harness** can fail after Blender
dies.

## Run

Via the harness (sets `$BDT_SMOKE_SIDECAR`):

```bash
python tests/smoke/run_example.py --name exit-pre-sidecar \
  --blender blender --script examples/exit-pre-sidecar/exit_pre_sidecar.py \
  --series 5.2 --min-version 5.1 \
  --expect-sidecar /tmp/exit-pre.sidecar --sidecar-contains exit_pre-ok
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `77` is the smoke skip protocol, not a product check.

| Code | Meaning |
| --- | --- |
| 0 | Success (including `--silent-handler` / `--no-handler` / `--wrong-text` / `--write-in-main` / `--atexit-instead`, which the harness then fails) |
| 1 | Uncaught exception (FATAL wrapper); also `$BDT_SMOKE_SIDECAR` unset |
| 2 | argparse / usage; also `--force-run` on Blender &lt; 5.1 (`exit_pre` missing or unexpectedly present) |
| 77 | `SMOKE_SKIP:` `exit_pre` requires Blender 5.1+ |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS (5.1 on the
weekly cron, the `needs-5.1` PR label, or manual dispatch) and skips on 4.5
LTS. Smoke does not pass the falsifier flags.
