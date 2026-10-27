# Extension user data and online access, the way the Extensions Platform
# expects. Paste into an extension's package (it uses __package__, which is
# "bl_ext.<repo>.<id>" once installed).
#
# - The install directory is replaced on every upgrade, so never write next
#   to __file__. extension_path_user() names extensions/.user/<repo>/<id>,
#   which survives upgrades (and is deleted when the extension is removed).
# - It raises ValueError for a package that is not an extension (a legacy
#   add-on folder), so legacy code paths need their own fallback.
# - Network access needs the "network" permission in blender_manifest.toml
#   AND bpy.app.online_access, which is False unless the user allowed it or
#   Blender runs with --online-mode.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.utils.html#bpy.utils.extension_path_user
#   https://docs.blender.org/api/current/bpy.app.html#bpy.app.online_access

import json
import os

import bpy


def settings_path(filename="settings.json"):
    """A writable file that survives upgrades of this extension."""
    directory = bpy.utils.extension_path_user(__package__, path="", create=True)
    return os.path.join(directory, filename)


def load_settings(default=None):
    path = settings_path()
    if not os.path.isfile(path):
        return dict(default or {})
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_settings(data):
    with open(settings_path(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def fetch_if_allowed(url):
    """Return the body of `url`, or None when the user has not allowed online access."""
    if not bpy.app.online_access:
        return None
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read()
