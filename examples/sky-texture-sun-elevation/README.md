# Sky Texture Sun Elevation

A runnable example that builds a World whose Background Color is driven by
`ShaderNodeTexSky`, then proves `sun_elevation` is load-bearing with two tiny
Cycles EXR zenith probes. The gallery still is a sky study: a red-granite
gnomon obelisk on a paved plaza, lit by nothing but the sky, shown at both
elevations side by side so the contract reads at thumbnail scale.

**What it witnesses:** the Sky Texture contract AI-generated lighting code most
often gets wrong across the 4.5 LTS → 5.1 window.

- **Sky must drive Background Color.** A near-black Background Strength alone
  is not a sky — the check asserts the Sky → Background → World Output links.
- **`sky_type` renamed.** 4.5 LTS uses `NISHITA`; 5.1 replaced it with
  `MULTIPLE_SCATTERING` (Nishita's successor). Assigning `NISHITA` on 5.1 fails;
  the enum no longer lists it.
- **`dust_density` → `aerosol_density`.** 4.5 exposes `dust_density`; 5.1 raises
  `AttributeError` and ships `aerosol_density` instead. AI code still emits
  `dust_density`.
- **`sun_elevation` brightens zenith.** Two CPU Cycles OPEN_EXR probes with a
  straight-up camera, Background Strength 0.05 (unclipped), compare zenith
  luminance at 8° vs 55°. Measured rise **2.25x** on 5.1.2 and **1.50x** on
  4.5.11 LTS (gate ≥ 1.25).

**What each check catches on failure:** broken Sky→Background link (exit 6),
wrong `sky_type` for the running version (exit 3), lost `sun_elevation`
round-trip (exit 4), `dust_density` / `NISHITA` present on the wrong side of
5.0 (exit 5), a non-working sky (zenith floor, exit 7), and an elevation that
does not brighten zenith (exit 8 — rise below 1.25).

**Version witness:** `sky_type` and the dust/aerosol rename are the divergence;
`sun_elevation` itself is stable. Zenith rise differs by model (Nishita vs
multiple scattering) but clears the same gate on both binaries.

## Stage deviation

The World carries a Nishita / multiple-scattering Sky Texture instead of the
default near-black Background, and there are no studio lights: the contract
*is* the sky, so the sky's sun disc is the key and its dome is the fill. The
still is a diptych, 8° | 55°, split by a dark 12 px rule, with one Background
Strength (0.035) for both panels so `sun_elevation` is the only variable. If
it did not take, the two panels would render identical.

What reads at a glance: at 8° a deep navy sky with a dusk glow on the left
horizon, the obelisk's sun face raked orange, the plaza nearly dark and the
shadow running long out of frame; at 55° a bright blue sky, a sunlit plaza,
and a short shadow ending on the bronze meridian scale inlaid in the paving.
The ground runs to the horizon, so there is no void below it.

Layer 1 still holds: `view_transform='Standard'`, designed materials (red
granite, limestone, bronze, matte gilt, brick-pattern paving), a chosen 35 mm
camera on a `TRACK_TO` aim, no helpers in frame. Standard does not compress
highlights, so the render path fails with exit 12 if more than 0.05 % of the
still clips to white. The committed still has zero clipped pixels. The
pyramidion is matte gilt rather than metal: a metallic cap Fresnel-glinted
the 55° sun to pure white at grazing angles, whatever its roughness. Mean
luma is about 0.20, reported against the calibration set as information
under this deviation.

The sky's `sun_rotation` is a compass bearing, measured clockwise from +Y.
The first draft assumed the opposite convention and put the shadow on the
wrong side. `_sun_rotation_for_shadow` holds the measured mapping.

## Framing

Each 640 × 720 panel is its own frame, and the gnomon is measured in it
through `examples/gallery_framing.py` (exit 10). Both panels share geometry
and camera, so one measurement covers both. On 5.2.1 the fill is
x 0.566 / y 0.794 and the margins are left 0.100, right 0.334,
bottom 0.044, top 0.161. The ground, plaza and meridian inlay are stage.

## Run

```bash
# Zenith-luminance correctness check (tiny Cycles CPU EXR probes) — the CI check:
blender --background --python sky_texture_sun_elevation.py --

# Falsifier: Sky→Background unlinked. Must exit non-zero (world links).
blender --background --python sky_texture_sun_elevation.py -- --unlink-sky

# Also render the gallery diptych (Cycles; framing gate exit 10, clip gate exit 12):
blender --background --python sky_texture_sun_elevation.py -- --output sky.png
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | `sky_type` is not the identifier for this Blender |
| 4 | `sun_elevation` round-trip failed |
| 5 | `dust_density` / `aerosol_density` / `NISHITA` / `MULTIPLE_SCATTERING` trap |
| 6 | Sky → Background → World Output links broken (`--unlink-sky` lands here) |
| 7 | High-elevation zenith luma below floor |
| 8 | Zenith luma did not rise with elevation |
| 9 | `--output` produced no file |
| 10 | `--output` framing violation (`gallery_framing`, per panel) |
| 12 | `--output` still clips to white under Standard (> 0.05 % of pixels) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--unlink-sky`, so exits 10 and 12 are
render-path only.
