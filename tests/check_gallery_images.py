"""Every gallery entry's hero and preview webp must be the specified size.

CLAUDE.md fixes the sizes: hero 1280x720 (docs/gallery/assets/), preview
1200x675 (next to the entry's script). Nothing enforced them, and 19 of the
28 showcase previews shipped at the hero size (#214).

Stdlib only, so it runs on a bare CI runner: the WebP header is parsed
directly (RIFF container; VP8, VP8L and VP8X chunks).

Exit codes: 0 clean, 1 a size or format is wrong, 2 usage.
"""
from __future__ import annotations

import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = (("examples/gallery.json", "examples"), ("showcase/gallery.json", "pieces"))
EXPECTED = {"hero": (1280, 720), "preview": (1200, 675)}


def webp_size(path: str) -> tuple[int, int]:
    """(width, height) from a WebP file header. Raises ValueError otherwise."""
    with open(path, "rb") as f:
        head = f.read(30)
    if len(head) < 30 or head[:4] != b"RIFF" or head[8:12] != b"WEBP":
        raise ValueError("not a RIFF/WEBP file")
    chunk = head[12:16]
    if chunk == b"VP8X":  # extended: 24-bit canvas size minus one
        w = int.from_bytes(head[24:27], "little") + 1
        h = int.from_bytes(head[27:30], "little") + 1
        return w, h
    if chunk == b"VP8L":  # lossless: 14-bit fields after the 0x2f signature
        if head[20] != 0x2F:
            raise ValueError("bad VP8L signature")
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":  # lossy: keyframe start code, then 14-bit sizes
        if head[23:26] != b"\x9d\x01\x2a":
            raise ValueError("bad VP8 start code")
        w, h = struct.unpack("<HH", head[26:30])
        return w & 0x3FFF, h & 0x3FFF
    raise ValueError(f"unknown WebP chunk {chunk!r}")


def main() -> int:
    failures, checked = [], 0
    for rel, key in SOURCES:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            entries = json.load(f)[key]
        for entry in entries:
            for field, want in EXPECTED.items():
                path = entry.get(field)
                if not path:
                    failures.append(f"{entry['name']}: no '{field}' path in {rel}")
                    continue
                checked += 1
                try:
                    got = webp_size(os.path.join(ROOT, path))
                except (OSError, ValueError) as exc:
                    failures.append(f"{entry['name']}: {field} {path}: {exc}")
                    continue
                if got != want:
                    failures.append(
                        f"{entry['name']}: {field} {path} is {got[0]}x{got[1]}, "
                        f"expected {want[0]}x{want[1]}"
                    )
    for msg in failures:
        print(f"  ERROR: {msg}")
    if failures:
        print(f"\n{len(failures)} gallery image(s) off spec "
              "(hero 1280x720, preview 1200x675).")
        return 1
    print(f"gallery image sizes ok: {checked} image(s) across both gallery.json files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
