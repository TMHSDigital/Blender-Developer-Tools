# VSE Cut List

A runnable example that witnesses the **sequencer API rename between Blender
4.5 LTS and 5.x** — the single most common way AI-generated VSE code dies on a
modern Blender. Every tutorial-era snippet does
`scene.sequence_editor.sequences.new_effect(..., frame_end=...)`; on 5.x that
path is gone twice over (`sequences` removed, `frame_end` kwarg rejected),
and on 4.5 the modern spelling (`strips`, `length=`) is already the only one
the new collection accepts.

**What it witnesses:** a deterministic cut list — three color programs A/B/C,
a GAMMA_CROSS fed by a dedicated source pair T1/T2, a scene strip, and a text
strip — asserted against closed-form spans on each version's canonical
accessors, then re-asserted after a save/reload round-trip:

1. **Accessor rename** — 5.x: `sequence_editor.sequences` raises
   AttributeError; only `.strips` exists. 4.5: both accessors exist and see
   the same strips (the transition bridge).
2. **Creation signature** — `strips.new_effect(...)` ends a strip with
   `frame_end=` on 4.5 but `length=` on 5.x; the wrong kwarg raises TypeError
   on each side (asserted, not assumed). 5.x also rejects the removed
   `TRANSFORM` effect type — per-strip `strip.transform` (StripTransform)
   places strips in the frame on both versions.
3. **Frame-range closed form** — every strip's (start, end, duration) matches
   the authored end-exclusive span: `frame_final_*` on 4.5;
   `left_handle`/`right_handle`/`duration` on 5.x, where the `frame_final_*`
   names are deprecated aliases (removal announced for 6.0) that must still
   read equal — the bridge is asserted lossless, with the RNA
   `is_deprecated` flag checked on 5.x and its absence checked on 4.5.
4. **Effect wiring** — `input_1`/`input_2` (not `input1`) on both versions,
   in authored order, and the cross clamped to exactly the T1/T2 overlap.
5. **Scene strip** — 4-arg `new_scene(name, scene, channel, frame_start)` on
   both versions (no `length`/`frame_end` kwarg); default span is the source
   scene's frame range; the strip sources a *separate* Stage scene.
6. **Round-trip** — spans, channels, colors, GC wiring, text, and mosaic
   transforms (pixel-unit offsets, tol 1e-3) all survive
   `save_as_mainfile` → `open_mainfile`.
7. **Compositing (`--check-pixels`)** — a 96×54 render asserts each mosaic
   cell center carries its strip color (tol 0.1), the cross cell is a true
   mid blend (strictly between the sources on every channel), and a margin
   point matches neither cross source — because a consumed input compositing
   independently would paint it full-frame.

**What each check catches on failure:**

- *Accessor* — `.sequences` returning on 5.x, or the 4.5 bridge seeing
  different contents (falsified: the legacy path on 5.1.1 raises
  `AttributeError: 'SequenceEditor' object has no attribute 'sequences'`).
- *Creation* — Blender re-accepting a removed kwarg silently, or the
  TRANSFORM enum returning (falsified: calling `new_effect(frame_end=...)` on
  5.1.1 raises `TypeError: ... expected (name, type, channel, frame_start,
  length, input1, input2)`).
- *Spans* — end-inclusive vs end-exclusive off-by-one, retiming drift
  (falsified: expecting GC span (25, 34) exited 5 with measured
  `GC span (25, 33, 8) != closed form (25, 34, 9)` — note the cross was
  *clamped* to the 8-frame overlap, itself a witnessed behavior).
- *Wiring* — swapped or dropped cross inputs (falsified: `input1=t2,
  input2=t1` exited 7 with measured `inputs=(T2, T1), expected T1 -> T2`).
- *Round-trip* — serialization dropping strip data (falsified: corrupting the
  text strip before save exited 10 via the reloaded re-assert).
- *Pixels* — a broken span or cell transform dropping a cell, a frozen cross,
  or a consumed input leaking back into the composite (found by authoring:
  GC below T1/T2 let T2 paint the whole wall teal).

**Hazards discovered while authoring** (all witnessed by the checks above):

- A GAMMA_CROSS asked to outlast its inputs' overlap is **silently clamped**
  to the overlap — request length 9 over a (25, 33) overlap, get (25, 33).
- A scene strip pointing at its **own** scene is a feedback loop and renders
  transparent (alpha 0) — the "stage" is silently absent. Source a separate
  scene.
- Effect strips **consume** their inputs: input strips never composite on
  their own channel, and the effect's transform applies on top of the
  inputs' transforms. Consumption requires the effect on a channel **above**
  its inputs; below, they keep painting independently.
- An empty `bpy_prop_collection` is falsy — `se.strips or se.sequences`
  silently falls through to the legacy accessor on an empty timeline. Always
  branch on `hasattr`.

**Version divergence:** the whole example is the divergence — gated on the
`bpy.app.version` tuple (`>= (5, 0, 0)`), never on `version_string`
(`"4.5.11 LTS"` is not bare semver). Each side asserts its own canonical
contract plus the other side's removal/bridge state. Measured values are
identical on 4.5.11 and 5.1.1, including the pixel witness.

**Render:** the program wall *is* the sequencer output at frame 29 (mid
cross) — crimson A, teal B, amber long-runner C, and the 50/50 cross blend,
over the Stage scene strip showing the dark studio. An off-by-one in
end-exclusive span math drops its cell to the dark stage; the caption strip
carries the closed form. The hero presents that authentic frame on a
reference monitor in a dark-studio editing bay — the pixels on the screen
are the genuine sequencer output (evidence); only the bay around them is
staged (presentation). Rendered locally with EEVEE (GPU host); the checks
and `--check-pixels` need no GPU (Cycles CPU).

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python vse_cut_list.py --

# Compositing witness on a tiny render (Cycles CPU, CI-safe):
blender --background --python vse_cut_list.py -- --check-pixels --engine cycles

# Also render the still (EEVEE on a GPU host; --engine cycles on GPU-less):
blender --background --python vse_cut_list.py -- --output vse.png
```

It exits non-zero on failure and prints every measured value and tolerance on
success, so CI logs carry the numbers. The `blender-smoke` workflow runs the
check and the pixel witness on Blender 4.5 LTS and 5.1.
