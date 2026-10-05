# Geometry Nodes simulation-zone ballistic fountain

A two-tier stone fountain whose twenty jets are integrated by a Simulation
Zone, witnessing the
[`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md)
frame contract: **a Simulation Zone only advances when the scene steps one
frame at a time.** The evaluated state at frame N is not a function of N.
AI code that calls `scene.frame_set(N)` and reads positions gets a silently
wrong answer.

Each droplet is a point with a `vel` attribute. Per step the zone applies the
constant-gravity update that is exact for any `dt`:

```
p += v*dt - 0.5*g*dt^2 * z
v -= g*dt * z
```

so at frame `f` every point must lie on the closed-form ballistic arc
`p0 + v0*t - 0.5*g*t^2*z` and carry `v0 - g*t*z`, with
`t = (f - frame_start) / fps`. The check recomputes both from the launch data
(8 crown jets thrown up and out, 12 rim jets arcing inward; `g = 9.81`,
24 fps, 24 steps = 1.0 s).

## Measured behavior

Identical on 4.5.11 LTS, 5.1.2 and 5.2.1 LTS. The Simulation Zone and its
cache/bake operators have **not** diverged across the three, so there is no
version branch; the probes that established this are the checks below.

| Call sequence | What the zone does |
| --- | --- |
| `frame_set(frame_start)` | body runs once with Delta Time 0 — state reset to the input |
| `frame_set(f)` then `frame_set(f + 1)` | one step, `dt = 1/fps` |
| `frame_set(start)` then `frame_set(N)`, no cache | **one** step, `dt = 1/fps`: frame N shows the frame-2 state |
| `simulation_nodes_cache_calculate_to_frame(selected=True)` headless | poll fails: logs `Invalid operator call`, returns `{'PASS_THROUGH'}`, **does not raise**; frames between the two cached endpoints then read as a linear interpolation of them |
| `simulation_nodes_cache_bake(selected=True)` under `temp_override` | bakes `frame_start..frame_end` (`PACKED`, in memory, no directory); any `frame_set` order then reads the exact per-frame state |

Two silent traps, then. The jump is 1.68–2.42 m off the true frame-25 arc
here. The tempting cache operator "succeeds" without raising and leaves
interpolated garbage between cached frames (2.42 m / 9.40 m/s off).

**Tolerance.** `TOL = 1e-4` m and m/s. The state is float32 accumulated over
24 steps; the measured worst case is 6.6e-7 m and 1.4e-6 m/s, so the band is
~150× the observed error and ~2000× below the smallest broken case (Euler,
0.204 m). The trap must also clear `TRAP_GAP_FLOOR = 0.25` m from the true
arc, so a rounding difference can never pass as the trap.

**What failure each check would catch:**

- exit 3 — the zone is unpaired or drops points: `pair_with_output` not
  called evaluates to 0 points (`--unpair`)
- exit 4 — the integrator is not the exact constant-gravity update: naive
  `p += v*dt` drifts by `g*dt*t/2`, 0.2044 m at t = 1 s (`--euler`)
- exit 5 — a direct frame jump did **not** reproduce the one-step trap — e.g.
  because a bake was already present (`--prebake-trap`). This is what keeps
  the trap claim above honest on every version CI runs
- exit 6 — random-access reads after a cache fill miss the arc, or the fill
  operator did not return `FINISHED`: `calculate_to_frame` headless
  (`--calc-to-frame`)

**The render is the proof.** Every droplet bead in the still is a recorded
simulated position from the stepped run (check 4). The thin line each string
of beads is threaded on is the closed-form arc, drawn from the launch data,
not from the simulation. A drifting integrator would pull the late beads off
their line — by 0.20 m at the pool for `--euler`, as check 4 measures (that
flag exits before rendering, so this is computed, not a rendered still).

## Run

```bash
blender --background --python gn_sim_fountain.py --
blender --background --python gn_sim_fountain.py -- --output fountain.png
```

The `--output` render path measures framing via `examples/gallery_framing.py`
(exit 10 on violation).

## Falsifiers

Each breaks one thing and exits the code of the check it targets, on all
three versions.

| Flag | Breaks | Target check | Exit |
| --- | --- | --- | --- |
| `--unpair` | Simulation Input never paired with its Output | zone evaluates one point per jet | 3 |
| `--euler` | drops the `-0.5*g*dt^2` position term | stepped frames on the closed-form arc | 4 |
| `--prebake-trap` | bakes before the direct jump | unbaked jump runs exactly one step | 5 |
| `--calc-to-frame` | fills the cache with `calculate_to_frame`, not a bake | baked random access on the arc | 6 |

## Exit codes

Per-script sequential checks. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Point count or frame-start state off the launch data |
| 4 | Stepped frames off the closed-form arc (position or velocity) |
| 5 | Direct jump did not reproduce the one-step trap |
| 6 | After the cache fill, random-access frames off the arc (or fill not `FINISHED`) |
| 10 | Gallery framing violation |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`. Its catalog falsifiers are the three in the table above: `--euler` (expects exit 4), `--prebake-trap` (expects exit 5) and `--calc-to-frame` (expects exit 6).
