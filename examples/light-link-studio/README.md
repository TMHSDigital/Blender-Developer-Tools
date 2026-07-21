# Light Link Studio

A runnable example that stages one key light linked to a hero sphere beside an
identical decoy, renders the studio twice in one pass, and proves the whole
light-linking contract **in pixels** — the feature AI-generated staging code
most often misses or misaddresses.

**What it witnesses:** the light-linking contract and the traps around it.

1. **The API is on the light OBJECT, not the Light datablock.**
   `ld.light_linking` is an AttributeError on both versions (verified); the
   path is `obj.light_linking.receiver_collection` (ObjectLightLinking, with
   `blocker_collection` alongside). Assignment reads back through the API.
2. **Linked, the key lights only the receiver collection.** Render one:
   hero well-lit, decoy at the fill floor — hero/decoy luminance ratio
   **4.0x** (gate ≥ 3x), measured at each sphere's *projected* center so
   framing can't move the sample off the subject.
3. **Unlinked (same check), the restriction vanishes surgically.** Render
   two: the decoy rises **244–251%** while the hero drifts **0.0%** — the
   link restricts without dimming anything else. The shipped check therefore
   demonstrates both states, not just one.
4. **The engine note, verified rather than assumed.** Light linking also
   works on EEVEE Next — measured 5.5x linked ratio on 4.5.11 EEVEE Next and
   5.9x on 5.1.2 EEVEE, matching Cycles within sampling noise. The check
   still pins Cycles for deterministic tiny-sample CPU renders; luminance
   gates need `view_transform = 'Standard'` (AgX compresses the ratios).

**What each check catches on failure:** inverting the link to the decoy
collection (exit 6 — hero drops to 0.179, ratio collapses to 0.22x), an
RNA move of the API onto the Light datablock (exit 3, guarded), a lost
assignment read-back (exit 5), a link that doesn't restrict (exit 7, rise
below 50%), and a non-surgical restriction (exit 8, hero drift above 5%).

**Version witness:** ObjectLightLinking API and the measured ratios match on
Blender 4.5 LTS and 5.1 (4.0x linked both; rise 244% vs 251% within sampling
noise).

The render is the contract at a glance: the blazing orange hero over the
LINKED plaque, the cold steel decoy over UNLINKED — one key, one hero.

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
