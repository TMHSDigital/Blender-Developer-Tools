# Showcase

Budget-conformance props. **Not examples.**

An example witnesses one API contract and carries a falsifier that makes a
real assertion fail. A recognizable crate witnesses no API contract.
Forcing one into `examples/` produces a vacuous check. Showcase pieces
assert that generated geometry meets **declared asset budgets**.

"It rendered without error" is not an assertion. A tolerance so wide
nothing can violate it is not an assertion.

This directory is a sibling of `examples/`, not nested under it. The
manifest key is `showcase`. Counts are separate from the example total.

## Conventions

Every piece is a directory `showcase/<name>/` with a script, a README that
includes an exit-code table, a falsifier, a `catalog.json` row, a gallery
entry in `showcase/gallery.json`, and a rendered still.

- **Deterministic.** Fixed seed (or no RNG). Identical output across runs
  on the same binary, and across Blender 4.5, 5.1, and 5.2. If a value
  legitimately cannot match across versions, the piece README names it,
  states a tolerance, and justifies it. DECIMATE COLLAPSE triangle counts
  are the usual suspect — prefer ratio bands, not exact counts.
- **Budgets declared** in the script as named constants and documented in
  the piece README. Suggested axes: triangle count, material count, UV
  bounds, bounding-box dimensions, LOD ratios, collider triangle ceiling,
  export file written.
- **Assertions recompute** those budgets from the generated result. They
  never restate constants the script set (`if n == DECLARED` where `n` was
  assigned `DECLARED` is not a check).
- **Falsifier** breaks one pipeline stage so a **named** budget fails and
  the piece exits its documented code. Prove default and falsifier on
  4.5.11, 5.1.2, and 5.2.1.
- **Exit codes** are file-local: `0` success, argparse `2`, `3` and above
  in check order. `9` is legal. FATAL `sys.exit(1)` is a crash, never a
  named check.
- **Rendered still and gallery entry.** Showcase pieces are visual by
  definition. The pathology / sidecar exemption does not apply. Call
  `examples/gallery_framing.check_framing` on the `--output` path only.
  Do not pass `deviation=`. Do not move or modify `gallery_framing.py` —
  import it by resolving the repo root (see the shipping-crate script).
- **Composition.** The README names which shipped skills and snippets the
  piece composes. Duplicated helpers stay inlined or copied; showcase
  scripts do not import snippets as a package.

## Layout

```text
showcase/
  README.md              # this file
  gallery.json           # this tree's gallery index (pieces[])
  <name>/
    <name>.py
    README.md
    preview.webp
```

Hero stills live at `docs/gallery/assets/<name>-hero.webp` like examples.
`scripts/build_gallery.py` merges `showcase/gallery.json` into the same
`docs/gallery/` site as examples, tagged `showcase`.

## Smoke

`tests/smoke/catalog.json` takes opaque script paths. A showcase row is
enough; `blender-smoke.yml` has no path filter and runs the whole catalog
on every PR. Measure wall-clock before adding the next piece.
