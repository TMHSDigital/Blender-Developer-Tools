# Light Link Studio

A runnable example that stages one key light linked to a hero sphere beside an
identical decoy, renders the studio twice in one pass, and proves the whole
light-linking contract **in pixels** — the feature AI-generated staging code
most often misses or misaddresses.

**What it witnesses:** the light-linking contract and the traps around it.

- **The API is on the light OBJECT, not the Light datablock.**
  `ld.light_linking` is an AttributeError on both versions (verified); the
  path is `obj.light_linking.receiver_collection` (ObjectLightLinking, with
  `blocker_collection` alongside). Assignment reads back through the API.
- **Linked, the key lights only the receiver collection.** Render one:
  hero well-lit, decoy at the fill floor — hero/decoy luminance ratio
  **3.6x** (gate ≥ 3x), measured at each sphere's **projected** center so
  framing can't move the sample off the subject.
- **Unlinked (same check), the restriction vanishes surgically.** Render
  two: the decoy rises **233–238%** while the hero drifts **0.1–0.3%** — the
  link restricts without dimming anything else. The shipped check therefore
  demonstrates both states, not just one. The rise figure is noisy by
  construction: the decoy's unlit base sits near the fill floor, so small
  absolute shifts in that base swing the relative rise between versions and
  runs — the gate is a conservative ≥ 50%.
- **The engine note, verified rather than assumed.** Light linking also
  works on EEVEE — measured with an EEVEE luminance probe (the shipped
  scene with `render.engine` swapped: `BLENDER_EEVEE` on 5.x,
  `BLENDER_EEVEE_NEXT` on 4.x) at **3.8x** linked ratio on both 4.5.11
  EEVEE Next and 5.1.2 EEVEE, matching Cycles within sampling noise. The
  shipped check still pins Cycles for deterministic tiny-sample CPU
  renders; luminance gates need `view_transform = 'Standard'` (AgX
  compresses the ratios).

**What each check catches on failure:** inverting the link to the decoy
collection (exit 6 — hero/decoy ratio collapses to 0.39x), an
RNA move of the API onto the Light datablock (exit 3, guarded), a lost
assignment read-back (exit 5), a link that doesn't restrict (exit 7, rise
below 50%), and a non-surgical restriction (exit 8, hero drift above 5%).

**Version witness:** ObjectLightLinking API and the measured ratios match on
Blender 4.5 LTS and 5.1 (3.7x vs 3.6x linked; rise 238% vs 233% — inside the
rise noise described above).

The render is the contract at a glance: the spheres staged as studio
specimens on matching turned-metal pedestals — the blazing orange hero over
its LINKED placard with the warm floor inlay marking the linked light's
footprint, the cold steel decoy over UNLINKED with its inlay dark, a warm
pool raking the wall behind them — one key, one hero.

## Run

```bash
# Two-render correctness check (tiny Cycles CPU renders) — the CI check:
blender --background --python light_link_studio.py --

# Also render the gallery still (Cycles, deterministic samples):
blender --background --python light_link_studio.py -- --output linked.png
```

It exits non-zero on failure (API moved, assignment lost, ratio below gate,
insufficient unlink rise, or hero drift). The `blender-smoke` workflow runs
the check on Blender 4.5 LTS and 5.1.
