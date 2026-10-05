# Timers, modal operators and threads

Proves the event-loop contracts behind long-running add-on work. Timers and
modal operators only run where Blender has an event loop, which
`--background` lacks. So the script runs two child Blenders: one in
`--background`, one windowed. The windowed child quits itself from a timer and
reports what happened as JSON. Check-only: the witnesses are call counts,
thread identity and registration state, which no render shows.

Follows [`timers-modal-and-threading`](../../skills/timers-modal-and-threading/SKILL.md),
whose snippet is [`thread-queue-timer.py`](../../snippets/thread-queue-timer.py).
Child-process scaffolding matches
[`extension-package-lifecycle`](../extension-package-lifecycle/).

**What it witnesses:**

- In a `--background` child a timer registered with `first_interval=0.0`
  reports `is_registered() == True` and never runs.
- In the windowed child, a timer returning `None` runs once, and one returning
  `0.05` until its third call runs three times. Neither is registered
  afterwards.
- A worker thread puts its result in a `queue.Queue`; a timer drains it on the
  main thread (`threading.current_thread() is threading.main_thread()`) and
  creates a mesh from it.
- A modal operator started with `INVOKE_DEFAULT` under
  `temp_override(window=...)` returns `{'RUNNING_MODAL'}`, receives three
  `TIMER` events from `event_timer_add`, returns `{'FINISHED'}` and removes
  its timer.
- `wm.read_factory_settings` run from a timer keeps the timer registered with
  `persistent=True` and drops the plain one.

**What failure each check would catch:**

- exit 3 — the `--background` child failed, or its timer ran (the no-event-loop premise is gone)
- exit 4 — the windowed child wrote no result: no display, a crash, or a timeout
- exit 5 — timer return values not honoured (`--return-zero-once` lands here:
  the run-once timer returns `0.0`, which re-runs it)
- exit 6 — the worker's result was not applied exactly once on the main thread
- exit 7 — the modal operator did not tick to `FINISHED` and remove its timer
- exit 8 — a file load did not keep only the persistent timer (`--non-persistent`
  lands here: the keeper is registered without `persistent=True`)

The windowed child needs a display. CI runs smoke under xvfb; on a desktop a
Blender window opens for a few seconds.

## Re-verified

| Measurement | 4.5.11 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- |
| `--background` timer: registered / ran | yes / no | yes / no | yes / no |
| run-once / repeat-until-3 call counts | 1 / 3 | 1 / 3 | 1 / 3 |
| worker result applied on main thread | yes | yes | yes |
| modal: invoke, `TIMER` ticks, result, timer removed | `RUNNING_MODAL`, 3, `FINISHED`, yes | same | same |
| after file load: persistent / plain registered | yes / no | yes / no | yes / no |
| default exit | 0 | 0 | 0 |
| `--return-zero-once` / `--non-persistent` exit | 5 / 8 | 5 / 8 | 5 / 8 |

Under `--return-zero-once` the run-once timer ran 5 times on 5.2.1 before the
file load removed it.

## API reference

- [`bpy.app.timers`](https://docs.blender.org/api/current/bpy.app.timers.html)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.app.timers.html))
- [`WindowManager.event_timer_add`](https://docs.blender.org/api/current/bpy.types.WindowManager.html#bpy.types.WindowManager.event_timer_add)
- [Modal operators](https://docs.blender.org/api/current/bpy.types.Operator.html#modal-execution)
- [Threading gotchas](https://docs.blender.org/api/current/info_gotchas_threading.html)

## Run

```bash
blender --background --python timers_modal_threading.py --
blender --background --python timers_modal_threading.py -- --return-zero-once
blender --background --python timers_modal_threading.py -- --non-persistent
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | `--background` child failed, or its timer ran |
| 4 | Windowed child wrote no result |
| 5 | Timer return values not honoured (`--return-zero-once` lands here) |
| 6 | Worker result not applied once on the main thread |
| 7 | Modal operator did not finish and remove its timer |
| 8 | File load did not keep only the persistent timer (`--non-persistent` lands here) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke passes no extra flags on the happy path. Its catalog falsifiers are
`--return-zero-once` (expects exit 5) and `--non-persistent` (expects exit 8).
