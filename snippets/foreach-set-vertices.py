# Bulk vertex injection via mesh.vertices.foreach_set("co", flat_array).
# Roughly 1000x faster than a Python loop assigning v.co for large
# meshes. The array must be a flat sequence of length 3 * vertex_count
# (x0, y0, z0, x1, y1, z1, ...) and dtype=float32 if numpy.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.vertices

import numpy as np
import bpy


def build_grid_mesh(name="Grid", size=100):
    coords = np.zeros((size * size, 3), dtype=np.float32)
    xs, ys = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    coords[:, 0] = xs.ravel()
    coords[:, 1] = ys.ravel()
    coords[:, 2] = np.sin(xs.ravel() * 0.1) * np.cos(ys.ravel() * 0.1)

    mesh = bpy.data.meshes.new(name=name)
    mesh.vertices.add(size * size)
    mesh.vertices.foreach_set("co", coords.ravel())
    mesh.update()

    obj = bpy.data.objects.new(name=name, object_data=mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


if __name__ == "__main__":
    build_grid_mesh()
