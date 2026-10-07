# Timers, modal operators and threads

Proves the event-loop contracts behind long-running add-on work. Timers and
modal operators only run where Blender has an event loop, which
`--background` lacks. So the script runs two child Blenders: one in
`--background`, one windowed. The windowed child quits itself from a timer and
reports what happened as JSON. Check-only: the witnesses are call counts,
thread idents and registration state, which no render shows.

Follows [`timers-modal-and-threading`](../../skills/timers-modal-and-threading/SKILL.md),
whose snippet is [`thread-queue-timer.py`](../../snippets/thread-queue-timer.py).
Child-process scaffolding matches
[`extension-package-lifecycle`](../extension-package-lifecycle/).

**What it witnesses:**

- In a `--background` child a timer registered with `first_interval=0.0`
  reports `is_registered() == True` and never runs.
- In the windowed child, a timer returning `None` runs once, and one returning
  `0.05` until its third call runs three times. Neither is registered
  afterwards. Registration is read **before** the file load in step 5, because
  `read_factory_settings` drops every plain timer and would make the read
  `False` whatever the return values were.
- Three worker threads run at once, the
  [`thread-queue-timer.py`](../../snippets/thread-queue-timer.py) pattern: two
  return values and one raises `ValueError`. Each worker records
  `threading.get_ident()`; so does the code that touches `bpy`. Every result
  and the error are handled on the script's main-thread ident, which no worker
  shares. A check of `threading.current_thread() is threading.main_thread()`
  inside a timer would be true by construction, since timers always run on the
  main thread; comparing idents is what can fail.
- Both results are applied (a mesh each), the error is reported on the main
  thread, the pending count reaches 0, and the drain timer unregisters itself:
  no result is stranded and nothing polls forever.
- A modal operator started with `INVOKE_DEFAULT` under
  `temp_override(window=...)` returns `{'RUNNING_MODAL'}`, receives three
  `TIMER` events from `event_timer_add`, returns `{'FINISHED'}` and removes
  its timer.
- `wm.read_factory_settings` run from a timer keeps the timer registered with
  `persistent=True` and drops the plain one.

**What failure each check would catch:**

- exit 3 — the `--background` child failed, or its timer ran
  (`--windowed-background-child` lands here: the same child with a window has
  an event loop, so its timer fires)
- exit 4 — the windowed child wrote no result: no display, a crash, or a timeout
- exit 5 — timer return values not honoured (`--return-zero-once` lands here
  on the call count: `0.0` re-runs the timer; `--return-late-once` lands here
  on registration alone: returning `30.0` keeps the count at 1, but the timer
  is still registered before the file load)
- exit 6 — a worker result or error was handled off the main thread
  (`--apply-in-worker` lands here: the worker applies its own result, so the
  recorded ident is the worker's)
- exit 7 — the modal operator did not tick to `FINISHED` and remove its timer
  (`--no-event-timer` lands here: without `event_timer_add` no `TIMER` event
  ever arrives)
- exit 8 — a file load did not keep only the persistent timer (`--non-persistent`
  lands here: the keeper is registered without `persistent=True`)
- exit 9 — not every concurrent job's result was applied (`--stop-after-first`
  lands here: the old drain returns `None` after one result and strands the
  other in the queue)
- exit 12 — the raising job was not reported, or the drain was still polling
  (`--no-catch` lands here: the old worker dies without `put()`, the pending
  count never reaches 0 and the drain stays registered)

The windowed child needs a display. CI runs smoke under xvfb; on a desktop a
Blender window opens for a few seconds.

## Re-verified

| Measurement | 4.5.11 | 5.2.1 |
| --- | --- | --- |
| `--background` timer: registered / ran | yes / no | yes / no |
| run-once / repeat-until-3 call counts | 1 / 3 | 1 / 3 |
| run-once / repeat registered before the file load | no / no | no / no |
| 3 workers: idents distinct from main | yes | yes |
| results applied (job: values) | heights: 3, labels: 2 | same |
| `ValueError` reported, on the main ident | yes | yes |
| pending / drain registered before the file load | 0 / no | 0 / no |
| modal: invoke, `TIMER` ticks, result, timer removed | `RUNNING_MODAL`, 3, `FINISHED`, yes | same |
| after file load: persistent / plain registered | yes / no | yes / no |
| default exit | 0 | 0 |
| `--windowed-background-child` exit | 3 | 3 |
| `--return-zero-once` / `--return-late-once` exit | 5 / 5 | 5 / 5 |
| `--apply-in-worker` / `--no-event-timer` / `--non-persistent` exit | 6 / 7 / 8 | 6 / 7 / 8 |
| `--stop-after-first` / `--no-catch` exit | 9 / 12 | 9 / 12 |

Under `--return-zero-once` the run-once timer ran 21 times on 4.5.11 and 30
times on 5.2.1 before the file load removed it. Under `--return-late-once` it
ran once and was still registered. Under `--stop-after-first` one result was
applied, and the drain unregistered with 2 jobs pending. Under `--no-catch` no
error was reported, the pending count stayed at 1, and the drain was still
registered. 5.1 was last measured before these cases existed (all original
checks matched 5.2.1); CI covers it on the weekly cron.

## API reference

- [`bpy.app.timers`](https://docs.blender.org/api/current/bpy.app.timers.html)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.app.timers.html))
- [`WindowManager.event_timer_add`](https://docs.blender.org/api/current/bpy.types.WindowManager.html#bpy.types.WindowManager.event_timer_add)
- [Modal operators](https://docs.blender.org/api/current/bpy.types.Operator.html#modal-execution)
- [Threading gotchas](https://docs.blender.org/api/current/info_gotchas_threading.html)

## Run

```bash
blender --background --python timers_modal_threading.py --
blender --background --python timers_modal_threading.py -- --windowed-background-child
blender --background --python timers_modal_threading.py -- --return-zero-once
blender --background --python timers_modal_threading.py -- --return-late-once
blender --background --python timers_modal_threading.py -- --apply-in-worker
blender --background --python timers_modal_threading.py -- --no-event-timer
blender --background --python timers_modal_threading.py -- --non-persistent
blender --background --python timers_modal_threading.py -- --stop-after-first
blender --background --python timers_modal_threading.py -- --no-catch
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | `--background` child failed, or its timer ran (`--windowed-background-child` lands here) |
| 4 | Windowed child wrote no result |
| 5 | Timer return values not honoured (`--return-zero-once`, `--return-late-once` land here) |
| 6 | A worker result or error was handled off the main thread (`--apply-in-worker` lands here) |
| 7 | Modal operator did not finish and remove its timer (`--no-event-timer` lands here) |
| 8 | File load did not keep only the persistent timer (`--non-persistent` lands here) |
| 9 | Not every concurrent job's result was applied (`--stop-after-first` lands here) |
| 12 | Raising job not reported, or the drain kept polling (`--no-catch` lands here) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke passes no extra flags on the happy path. Its catalog falsifiers are
`--windowed-background-child` (exit 3), `--return-zero-once` and
`--return-late-once` (exit 5), `--apply-in-worker` (exit 6),
`--no-event-timer` (exit 7), `--non-persistent` (exit 8),
`--stop-after-first` (exit 9) and `--no-catch` (exit 12).
