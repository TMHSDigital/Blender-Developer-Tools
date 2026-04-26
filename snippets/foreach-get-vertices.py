# Bulk vertex read via mesh.vertices.foreach_get into a numpy buffer.
# Pre-allocate the buffer; do not let foreach_get allocate per call.
# See rule: use-foreach-set-for-bulk-data.
# Refs: docs.blender.org/api/current/bpy.types.bpy_prop_collection.html

import numpy as np


def read_vertex_coords(mesh):
    """Return an (N, 3) float32 numpy array of vertex coordinates."""
    n = len(mesh.vertices)
    flat = np.empty(n * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", flat)
    return flat.reshape((n, 3))


def read_vertex_normals(mesh):
    n = len(mesh.vertices)
    flat = np.empty(n * 3, dtype=np.float32)
    mesh.vertices.foreach_get("normal", flat)
    return flat.reshape((n, 3))
