"""Extension package lifecycle — a runnable example.

Takes the repo's extension template through what an extension meets after
its first run, each step in a throwaway Blender user directory
(BLENDER_USER_RESOURCES) so nothing touches the real install:

1. ``blender --command extension validate`` then ``build`` produce a zip.
2. ``validate`` passes a manifest whose ``wheels`` entry names a file that
   does not exist; only ``build`` rejects it. CI must build, not just
   validate.
3. ``server-generate`` writes the repository listing (index.json) for a
   static extension server.
4. Installed, the add-on imports as ``bl_ext.user_default.<id>`` and
   ``bpy.utils.extension_path_user(__package__)`` names a directory beside
   the install tree, not inside it, so data written there survives the
   package being replaced on update.
5. ``bpy.app.online_access`` is False unless Blender runs with
   ``--online-mode`` (or the user allows online access).

Check-only: no gallery still. The witnesses are exit codes and paths.

    blender --background --python extension_package_lifecycle.py --
    blender --background --python extension_package_lifecycle.py -- --ship-wheel
    blender --background --python extension_package_lifecycle.py -- --data-next-to-file
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "..", "templates", "extension-addon-template"))
EXT_ID = "example_addon"
REPO = "user_default"
PACKAGE = f"bl_ext.{REPO}.{EXT_ID}"
MISSING_WHEEL = './wheels/not_shipped-1.0-py3-none-any.whl'
TIMEOUT = 300


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def blender(args, user_dir=None):
    """Run a child Blender; return (exit code, combined output)."""
    env = dict(os.environ)
    if user_dir:
        env["BLENDER_USER_RESOURCES"] = user_dir
    r = subprocess.run([bpy.app.binary_path, "--factory-startup", *args],
                       capture_output=True, text=True, env=env, timeout=TIMEOUT)
    return r.returncode, r.stdout + r.stderr


def child_python(expr, user_dir, extra=()):
    """Run `expr` in a background child Blender; return the lines it tagged with RESULT."""
    code, out = blender(["--background", *extra, "--python-expr", expr], user_dir)
    return code, [l[len("RESULT "):] for l in out.splitlines() if l.startswith("RESULT ")], out


def copy_template(dst):
    shutil.copytree(TEMPLATE, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dst


def check_build(work):
    src = copy_template(os.path.join(work, "src"))
    dist = os.path.join(work, "dist")
    os.makedirs(dist)
    code, out = blender(["--command", "extension", "validate", src])
    print(f"validate template: exit {code}")
    if code != 0:
        print(out)
        return fail("the template does not validate", 3), None
    code, out = blender(["--command", "extension", "build", "--source-dir", src, "--output-dir", dist])
    zips = [f for f in os.listdir(dist) if f.endswith(".zip")]
    print(f"build template: exit {code} -> {zips}")
    if code != 0 or zips != [f"{EXT_ID}-0.1.0.zip"]:
        print(out)
        return fail(f"build produced {zips}, expected {EXT_ID}-0.1.0.zip", 3), None
    with zipfile.ZipFile(os.path.join(dist, zips[0])) as z:
        names = set(z.namelist())
    print(f"zip members: {sorted(names)}")
    if not {"blender_manifest.toml", "__init__.py"} <= names:
        return fail("the zip lacks blender_manifest.toml or __init__.py at its root", 3), None
    return 0, dist


def check_wheel_trap(work, ship_wheel):
    """validate parses the manifest; only build opens the files it names."""
    src = copy_template(os.path.join(work, "wheel_src"))
    manifest = os.path.join(src, "blender_manifest.toml")
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write(f'\nwheels = ["{MISSING_WHEEL}"]\n')
    if ship_wheel:  # falsification: the named wheel exists, so build has nothing to reject
        wheel = os.path.normpath(os.path.join(src, MISSING_WHEEL))
        os.makedirs(os.path.dirname(wheel))
        with zipfile.ZipFile(wheel, "w") as z:
            z.writestr("not_shipped/__init__.py", "")
            z.writestr("not_shipped-1.0.dist-info/METADATA",
                       "Metadata-Version: 2.1\nName: not_shipped\nVersion: 1.0\n")
    out_dir = os.path.join(work, "wheel_dist")
    os.makedirs(out_dir)
    v_code, _ = blender(["--command", "extension", "validate", src])
    b_code, b_out = blender(["--command", "extension", "build", "--source-dir", src, "--output-dir", out_dir])
    shipped = os.listdir(out_dir)
    print(f"{'shipped' if ship_wheel else 'missing'} wheel: validate exit {v_code}, "
          f"build exit {b_code}, output {shipped}")
    if v_code != 0:
        return fail("validate rejects the package; the validate-is-not-a-gate trap this "
                    "example names is gone", 4)
    if b_code == 0 or shipped:
        return fail(f"build accepted the package (exit {b_code}, output {shipped}); "
                    "only build can reject a wheel the manifest names but the source lacks", 4)
    return 0


def check_listing(dist):
    code, out = blender(["--command", "extension", "server-generate", "--repo-dir", dist])
    index = os.path.join(dist, "index.json")
    if code != 0 or not os.path.isfile(index):
        print(out)
        return fail("server-generate wrote no index.json", 5)
    with open(index, encoding="utf-8") as fh:
        listing = json.load(fh)
    entries = [(e.get("id"), e.get("archive_url")) for e in listing.get("data", [])]
    print(f"listing: {entries}")
    if entries != [(EXT_ID, f"./{EXT_ID}-0.1.0.zip")]:
        return fail(f"listing {entries} does not name the built package", 5)
    return 0


def check_install(dist, user_dir, data_next_to_file):
    zip_path = os.path.join(dist, f"{EXT_ID}-0.1.0.zip")
    code, out = blender(["--command", "extension", "install-file", "-r", REPO, "-e", zip_path], user_dir)
    if code != 0:
        print(out)
        return fail("install-file failed", 6), None
    pick = "os.path.dirname(m.__file__)" if data_next_to_file else \
        "bpy.utils.extension_path_user(m.__package__, create=True)"
    expr = (
        "import bpy, importlib, os; "
        f"m = importlib.import_module('{PACKAGE}'); "
        "print('RESULT', m.__package__); "
        "print('RESULT', os.path.dirname(m.__file__)); "
        f"d = {pick}; "
        "open(os.path.join(d, 'settings.json'), 'w').write('{\"kept\": true}'); "
        "print('RESULT', d)"
    )
    code, res, out = child_python(expr, user_dir)
    if code != 0 or len(res) != 3:
        print(out)
        return fail("the installed extension did not import and report its paths", 6), None
    pkg, install_dir, data_dir = res
    print(f"installed package={pkg!r}\n  install dir={install_dir}\n  data dir={data_dir}")
    if pkg != PACKAGE:
        return fail(f"__package__ is {pkg!r}, expected {PACKAGE!r}", 6), None
    inside = os.path.normcase(os.path.abspath(data_dir)).startswith(
        os.path.normcase(os.path.abspath(install_dir)))
    if inside:
        return fail("user data lives inside the extension's install directory, which an update replaces", 7), None
    expected_tail = os.path.join("extensions", ".user", REPO, EXT_ID)
    if not os.path.normcase(data_dir).endswith(os.path.normcase(expected_tail)):
        return fail(f"data dir {data_dir} is not .../{expected_tail}", 7), None

    # Upgrade in place: install a 0.2.0 build over 0.1.0, as an update does.
    marker = os.path.join(install_dir, "written_at_runtime.txt")
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write("lost on upgrade")
    code, v2_zip = build_version(dist, "0.2.0")
    if code:
        return code, None
    code_up, out = blender(["--command", "extension", "install-file", "-r", REPO, "-e", v2_zip], user_dir)
    kept = os.path.isfile(os.path.join(data_dir, "settings.json"))
    marker_kept = os.path.isfile(marker)
    print(f"upgrade to 0.2.0 (exit {code_up}): user data kept={kept}, file beside __file__ kept={marker_kept}")
    if code_up != 0:
        print(out)
        return fail("installing 0.2.0 over 0.1.0 failed", 6), None
    if marker_kept:
        return fail("the upgrade did not replace the install directory; the premise is gone", 7), None
    if not kept:
        return fail("user data did not survive the upgrade", 7), None

    # Removing the extension deletes its user directory too.
    code_rm, _ = blender(["--command", "extension", "remove", f"{REPO}.{EXT_ID}"], user_dir)
    gone = not os.path.exists(data_dir)
    print(f"remove (exit {code_rm}): user data deleted={gone}")
    if code_rm != 0:
        return fail("extension remove failed", 6), None
    if not gone:
        return fail("remove did not delete the extension's user directory", 7), None
    return 0, data_dir


def build_version(dist, version):
    """Build the template again with a bumped version; return the new zip."""
    src = copy_template(os.path.join(os.path.dirname(dist), f"src_{version}"))
    manifest = os.path.join(src, "blender_manifest.toml")
    with open(manifest, encoding="utf-8") as fh:
        text = fh.read()
    with open(manifest, "w", encoding="utf-8") as fh:
        fh.write(text.replace('version = "0.1.0"', f'version = "{version}"', 1))
    out_dir = os.path.join(os.path.dirname(dist), f"dist_{version}")
    os.makedirs(out_dir)
    code, out = blender(["--command", "extension", "build", "--source-dir", src, "--output-dir", out_dir])
    zip_path = os.path.join(out_dir, f"{EXT_ID}-{version}.zip")
    if code != 0 or not os.path.isfile(zip_path):
        print(out)
        return fail(f"could not build {version}", 3), None
    return 0, zip_path


def check_online(user_dir):
    expr = "import bpy; print('RESULT', bpy.app.online_access)"
    _, default, _ = child_python(expr, user_dir)
    _, online, _ = child_python(expr, user_dir, extra=["--online-mode"])
    print(f"online_access: default={default} --online-mode={online}")
    if default != ["False"] or online != ["True"]:
        return fail("online_access is not False by default and True under --online-mode", 8)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--ship-wheel", action="store_true",
                   help="falsification: create the wheel the manifest names, so build succeeds")
    p.add_argument("--data-next-to-file", action="store_true",
                   help="falsification: store user data beside __file__")
    args = p.parse_args(argv)
    print(f"blender={bpy.app.version_string} template={TEMPLATE}")

    work = tempfile.mkdtemp(prefix="bdt_ext_")
    try:
        user_dir = os.path.join(work, "user")
        code, dist = check_build(work)
        if code:
            return code
        code = check_wheel_trap(work, args.ship_wheel)
        if code:
            return code
        code = check_listing(dist)
        if code:
            return code
        code, _ = check_install(dist, user_dir, args.data_next_to_file)
        if code:
            return code
        code = check_online(user_dir)
        if code:
            return code
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("extension-package-lifecycle OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
