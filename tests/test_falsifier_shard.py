"""Tests for tests/check_falsifier_targets.py --shard (the weekly sweep fan-out, #482).

Run: python tests/test_falsifier_shard.py -v
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_falsifier_targets as cft  # noqa: E402


class ShardTest(unittest.TestCase):
    def test_shards_partition_every_piece_exactly_once(self):
        pieces = [name for name, _r, _s in cft.piece_paths()]
        self.assertGreater(len(pieces), 0)
        for n in (1, 2, 4, 7):
            seen = []
            for k in range(n):
                seen += [p for i, p in enumerate(pieces) if cft.in_shard(i, (k, n))]
            self.assertEqual(sorted(seen), sorted(pieces), f"N={n}")

    def test_no_shard_keeps_everything(self):
        self.assertTrue(all(cft.in_shard(i, None) for i in range(10)))

    def test_parse_shard(self):
        self.assertEqual(cft.parse_shard("0/4"), (0, 4))
        self.assertEqual(cft.parse_shard("3/4"), (3, 4))
        for bad in ("4/4", "-1/4", "1/0", "x", "1/2/3"):
            with self.assertRaises(argparse.ArgumentTypeError, msg=bad):
                cft.parse_shard(bad)


if __name__ == "__main__":
    unittest.main()
