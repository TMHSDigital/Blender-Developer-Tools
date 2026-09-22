# exit_pre sidecar

`bpy.app.handlers.exit_pre` writes `$BDT_SMOKE_SIDECAR` as Blender dies.
Witnesses [`drivers-and-app-handlers`](../../skills/drivers-and-app-handlers/SKILL.md).
`main` does not write the file. The host runner asserts it after the
process exits (`tests/smoke/run_example.py --expect-sidecar`).

No gallery still. There is no geometry: the witness is a file that does
not exist until the process is already gone, and a render would look
identical whether the handler fired or not.

## The contract

`exit_pre` is the only handler in `bpy.app.handlers` that runs during
interpreter teardown, and it is the difference between a callback that
runs and one that silently never does. Code that relies on `atexit` for
this — saving a session log, flushing a render manifest, releasing a
licence token — is the class of bug this example exists to catch.

| Blender | `hasattr(bpy.app.handlers, "exit_pre")` |
| --- | --- |
| 4.5.11 LTS | `False` — `AttributeError` on access |
| 5.1.2 | `True` |
| 5.2.1 LTS | `True` |

Re-verified 2026-09-22 against all three binaries. `exit_pre` is also
the only exit- or quit-related name in `bpy.app.handlers` on the
versions that have it, so there is no older spelling to fall back to.

API reference:
[`bpy.app.handlers` (5.2 LTS)](https://docs.blender.org/api/current/bpy.app.handlers.html)
·
[`bpy.app.handlers` (4.5 LTS)](https://docs.blender.org/api/4.5/bpy.app.handlers.html)
— the 4.5 page lists no `exit_pre`, which is the absence this example
turns into a skip.

## Why 4.5 skips rather than fails

Exiting 77 on 4.5 is **correct by design**, not a gap in coverage. The
handler does not exist there, so there is no contract to witness and no
assertion that could meaningfully run. The catalog carries
`min_version` 5.1 and the runner treats a skip above that floor as a
FAIL, so the skip cannot quietly spread to a version that should run.
`tests/smoke/summarize.py` makes a job red if *every* example skipped,
so a repo-wide skip cannot pass either.

`--force-run` bypasses the skip so 4.5 proves the absence rather than
assuming it: the run exits 2 on `AttributeError`, and also exits 2 if
`exit_pre` turns out to exist on a version that should not have it.

## Falsifiers

The harness checks the sidecar's **contents**
(`sidecar_contains=exit_pre-ok`), not merely that a file appeared.
Most falsifiers therefore exit **0 from the script** — Blender reports
success — and the **harness** fails afterwards, which is the only place
a post-exit contract can be falsified.

| Flag | What it breaks | Script exit | Harness |
| --- | --- | --- | --- |
| `--no-handler` | nothing registered, nothing written | 0 | FAIL, no sidecar |
| `--silent-handler` | `exit_pre` registered but writes nothing | 0 | FAIL, no sidecar |
| `--wrong-text` | handler writes `nope` | 0 | FAIL, contents mismatch |
| `--write-in-main` | `from-main` written in `main`, no handler | 0 | FAIL, contents mismatch |
| `--atexit-instead` | `atexit` writes `atexit-ok` instead of `exit_pre` | 0 | FAIL, contents mismatch |
| `--force-run` on 4.5 | asserts `exit_pre` is genuinely absent | 2 | n/a |

`--write-in-main` and `--atexit-instead` are the two that matter: both
produce a file, so an existence-only check would pass them. They are why
the catalog row carries `sidecar_contains`.

## Run

Via the harness (sets `$BDT_SMOKE_SIDECAR`):

```bash
python tests/smoke/run_example.py --name exit-pre-sidecar \
  --blender blender --script examples/exit-pre-sidecar/exit_pre_sidecar.py \
  --series 5.2 --min-version 5.1 \
  --expect-sidecar /tmp/exit-pre.sidecar --sidecar-contains exit_pre-ok
```

Append `-- --wrong-text` (or any flag above) to falsify.

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
