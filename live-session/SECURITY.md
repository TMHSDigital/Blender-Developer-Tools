# Security Policy: blender-live-session

`blender-live-session` is the opt-in second plugin in the Blender Developer
Tools marketplace. It registers the official Blender Lab MCP server
([lab/blender_mcp](https://projects.blender.org/lab/blender_mcp)) and ships one
skill for using it. The repository-wide policy in the root
[`SECURITY.md`](../SECURITY.md) applies; this file covers what is specific to
this plugin.

## What this plugin runs

- `mcp.json` starts the server with `uvx` from a full 40-hex commit pin on
  projects.blender.org, with `--exclude-newer` so its dependencies resolve to
  what was reviewed with that pin. `tests/check_manifest_meta.py` enforces both,
  and `mcp-server.yml` installs and handshakes with the pinned server weekly.
- The server connects to a running Blender over `localhost`, through the MCP
  add-on, and executes Python the agent generates **in that Blender, without
  guards**. Attach it only to scratch scenes, never to files you cannot afford
  to lose. The skill in `skills/live-blender-session/` has the agent read the
  scene before touching it and save (or save a copy) before any mutating call.

## Reporting

- **This plugin** (the pin, `mcp.json`, the manifests, or the skill recommending
  something unsafe): open a
  [private security advisory](https://github.com/TMHSDigital/Blender-Developer-Tools/security/advisories/new).
- **The MCP server or its Blender add-on:** report upstream at
  [projects.blender.org/lab/blender_mcp](https://projects.blender.org/lab/blender_mcp).
  We move the pin once a fix lands upstream.

Supported versions and response times are the same as the root policy: the
latest release only.
