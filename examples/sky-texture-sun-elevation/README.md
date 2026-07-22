# Sky Texture Sun Elevation

A runnable example that builds a World whose Background Color is driven by
`ShaderNodeTexSky`, then proves `sun_elevation` is load-bearing with two tiny
Cycles EXR zenith probes — and stages a dual-elevation gallery diptych so the
contract is visible at thumbnail scale.

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

World carries a Nishita / multiple-scattering Sky Texture instead of the
default near-black Background — the contract *is* the sky. Gallery still is a
dual-elevation diptych (8° | 55°) so failure (identical panels) is visible at
thumbnail scale. Layer 1 still holds: `view_transform='Standard'`, designed
terracotta materials, chosen camera, no helpers in frame.

## Run

```bash
# Zenith-luminance correctness check (tiny Cycles CPU EXR probes) — the CI check:
blender --background --python sky_texture_sun_elevation.py --

# Also render the gallery diptych (Cycles):
blender --background --python sky_texture_sun_elevation.py -- --output sky.png
```

It exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1.
