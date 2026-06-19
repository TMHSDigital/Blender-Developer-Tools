# Reproduction of the headless-batch-scripting SKILL worked example (fixed v0.2.7),
# copied into scratch. Renders frames to PNG with the version-correct EEVEE id.
import argparse, os, sys, bpy

def parse_frames(spec):
    frames = []
    for chunk in spec.split(","):
        if "-" in chunk:
            lo, hi = chunk.split("-", 1); frames.extend(range(int(lo), int(hi)+1))
        else:
            frames.append(int(chunk))
    return frames

def main():
    argv = sys.argv
    argv = argv[argv.index("--")+1:] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", default="1")
    parser.add_argument("--engine", default="CYCLES", choices=["CYCLES", "EEVEE"])
    args = parser.parse_args(argv)

    scene = bpy.context.scene
    if args.engine == "EEVEE":
        scene.render.engine = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'
    else:
        scene.render.engine = args.engine
    print(f"engine={scene.render.engine}")
    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_x = 128; scene.render.resolution_y = 128
    out_dir = os.path.dirname(args.output) or "."
    os.makedirs(out_dir, exist_ok=True)
    for frame in parse_frames(args.frames):
        scene.frame_set(frame)
        scene.render.filepath = args.output.replace("####", f"{frame:04d}")
        bpy.ops.render.render(write_still=True)
        print(f"Rendered frame {frame} -> {scene.render.filepath}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
