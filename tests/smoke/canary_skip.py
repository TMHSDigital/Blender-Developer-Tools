"""Harness canary: always skip. Legal only when --min-version is above this Blender.

Prints SMOKE_SKIP and exits 77. Not a shipped example.
"""
import sys

print("SMOKE_SKIP: harness canary (always skip)", flush=True)
sys.exit(77)
