# Site design — the Blender viewport system

The whole site (landing page `docs/index.html` via `scripts/site/`, gallery
`docs/gallery/` via `scripts/build_gallery.py`) shares one design system: the
site reads as a Blender viewport session. This replaced the earlier purple
fleet-template look (2026-07-03); the previous plan to upstream that look into
the shared template was dropped — the fleet template only scaffolds new tools,
and each tool's site evolves independently after that.

## Vocabulary

- **Conceit**: topbar = Blender's topbar, footer = its status bar, sections =
  its panels (caret + mono label headers), hero = a viewport with a
  perspective grid floor, red-X/green-Y origin lines, and HUD overlays in the
  corners (mode, axis gizmo, statistics overlay with the pack counts, render
  status `smoke-gated · exit 0`).
- **Color**: Blender panel grays (`#1a1b1e` bg, `#222327` panel, `#3a3b40`
  border). ONE accent: selection orange `#ff8c19` (Blender's selected-object
  outline; cards use it as a hover outline). Axis colors
  `#ff3352 / #8bdc00 / #2890ff` appear only in the gizmo and grid origin
  lines — they encode, never decorate. Dark only; there is no theme toggle.
- **Type**: Barlow Condensed 600 uppercase for display; Inter for body;
  JetBrains Mono for every HUD label, stat, name, and chip. Fonts are
  self-hosted in `scripts/site/fonts/` and deployed to `docs/fonts/` by the
  landing build — gallery pages reference them at `../fonts/` / `../../fonts/`.
- **Copy**: benefit-led headers ("Every render here is a CI artifact"), the
  smoke-gate claim is the headline thesis.

Keep both builders in this system when editing either; the tokens are
duplicated (template.html.j2 and build_gallery.py SHELL) — change them in
both places.
