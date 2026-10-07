# Write a baked image datablock to disk without dropping the buffer.
# Image.save() on a GENERATED image flips source to FILE and the pixels
# re-source from disk — empty if the file was not the bake. save_render()
# writes the buffer and leaves source GENERATED.
#
# save_render() takes its format from the scene's render.image_settings, not
# from image.file_format: setting image.file_format = "OPEN_EXR" alone still
# writes the scene's format (a PNG by default). Set the scene's settings for
# the call and restore them after.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Image.html#bpy.types.Image.save_render
#   Witness: examples/image-pixels-testcard/

import bpy


def save_baked_image(image, filepath, file_format="PNG", scene=None):
    scene = scene or bpy.context.scene
    settings = scene.render.image_settings
    previous = settings.file_format
    settings.file_format = file_format
    try:
        image.save_render(filepath, scene=scene)
    finally:
        settings.file_format = previous
    return filepath
