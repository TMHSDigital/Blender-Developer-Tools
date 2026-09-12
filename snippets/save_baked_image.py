# Write a baked image datablock to disk without dropping the buffer.
# Image.save() on a GENERATED image flips source to FILE and the pixels
# re-source from disk — empty if the file was not the bake. save_render()
# writes the same PNG and leaves source GENERATED.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Image.html#bpy.types.Image.save_render
#   Witness: examples/image-pixels-testcard/

import bpy


def save_baked_image(image, filepath, file_format="PNG"):
    image.file_format = file_format
    image.save_render(filepath)
    return filepath
