# Blender Developer Tools (Claude Code plugin build)

Generated from https://github.com/TMHSDigital/Blender-Developer-Tools by
`scripts/build_plugin_dist.py` on every release. Do not edit this branch; it
is force-pushed. It carries only what the plugin loads: skills, the
`blender-rules` skill generated from `rules/`, snippets, templates and licenses.
Examples, the showcase and the gallery live on `main`.

```text
/plugin marketplace add TMHSDigital/Blender-Developer-Tools@plugin-dist
/plugin install blender-developer-tools@blender-developer-tools
```

Cursor: clone this branch into `~/.cursor/plugins/local/blender-developer-tools`
and reload the window (Customize then lists the 18 skills and 9 rules).

Skills reference bundled files as `${CLAUDE_PLUGIN_ROOT}/snippets/...`, which
Claude Code expands to this plugin's install directory. In Cursor, read it as
the root of this clone. Other repo links are pinned to the release tag.
