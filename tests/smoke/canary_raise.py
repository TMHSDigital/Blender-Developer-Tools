"""Harness canary: raise at module level, outside any FATAL wrapper.

Without --python-exit-code Blender exits 0 here and the harness would record
PASS. The workflow runs this with --no-record and requires exit 1. Not a
shipped example.
"""
raise RuntimeError("harness canary: uncaught exception must be red")
