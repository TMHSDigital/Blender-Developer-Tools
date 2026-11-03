# Security Policy

## Reporting a Vulnerability

If you discover a security issue in this repository (e.g., a snippet that demonstrates an unsafe pattern, a template that ships an over-broad permission set, or a skill that recommends an insecure practice), please report it responsibly.

**Report:** Open a [private security advisory](https://github.com/TMHSDigital/Blender-Developer-Tools/security/advisories/new) on GitHub.

Please include:

- Description of the vulnerability
- Steps to reproduce
- Which skill, rule, snippet, or template is affected
- Any suggested fix

## Scope

This repository ships Markdown skill files, MDC rule files, Python snippets, three starter templates (a Blender extension add-on, a headless batch script, and a GLB-in engine-ready asset pipeline), runnable headless examples under `examples/`, showcase scripts under `showcase/`, and an opt-in second plugin, `blender-live-session` (`live-session/`), that registers the upstream Blender Lab MCP server. The primary security concerns are:

- **Snippets or templates demonstrating insecure patterns** (executing arbitrary code from `.blend` files, loading remote scripts without validation, leaking filesystem paths into logs).
- **The extension-addon template declaring over-broad permissions** in `blender_manifest.toml` (e.g. `network`, `files`, `clipboard`, `camera`) without a documented justification.
- **Skills recommending insecure practices** (running `eval()` on driver expressions from untrusted sources, disabling Blender's auto-execute-script protection in headless workflows, embedding credentials in `.blend` custom properties).
- **Headless batch scripts** that pass user-controlled input to `subprocess` or `os.system` without sanitization.
- **Examples and showcase scripts** that do any of the above; they run headless in CI and users run them locally.
- **The `blender-live-session` plugin**: its pin and launch command in `live-session/mcp.json`, and its skill's guidance. That server executes agent-generated Python in a running Blender without guards. See [`live-session/SECURITY.md`](live-session/SECURITY.md) for what is in scope there; flaws in the upstream server itself belong upstream.

Issues with the Blender Python API itself (`bpy`, `bmesh`, `bpy_extras`) belong upstream at https://projects.blender.org and are out of scope here.

## Supported Versions

This is a content repository — Markdown, MDC, Python, and TOML files consumed
directly by an AI agent. The core plugin installs no runtime and starts no
server (the opt-in `blender-live-session` plugin launches the upstream MCP
server from a pinned commit; this repository does not host or patch it), and
there is no long-lived deployment to patch, so there are no maintenance branches and no
backports.

| Version | Supported |
|---------|-----------|
| Latest release (see [`VERSION`](VERSION)) | Yes |
| Any earlier release | No |

A confirmed fix lands on `main` and ships in the next release cut by
`release.yml`. Most consumers install the plugin, which comes from the
`plugin-dist` branch: release.yml force-pushes that branch as a single orphan
commit on each release that changes plugin content, and the branch carries no
tags, so a plugin install cannot be pinned to an older release. The remedy is to
update the plugin (Claude Code: `/plugin marketplace update
blender-developer-tools`; Cursor local plugin: `git fetch origin plugin-dist`
then `git reset --hard FETCH_HEAD` in its folder, since a force-pushed orphan
commit cannot be pulled). A
checkout of `main` pins by release tag (`vX.Y.Z`) or tracks `main`, and its
remedy is to move to the current release. Nothing older is patched in place.

## Response Timeline

We aim to acknowledge reports within 48 hours and provide a fix or mitigation within 7 days for confirmed issues.
