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

This repository ships Markdown skill files, MDC rule files, Python snippets, and one Blender extension add-on template. The primary security concerns are:

- **Snippets or templates demonstrating insecure patterns** (executing arbitrary code from `.blend` files, loading remote scripts without validation, leaking filesystem paths into logs).
- **The extension-addon template declaring over-broad permissions** in `blender_manifest.toml` (e.g. `network`, `files`, `clipboard`, `camera`) without a documented justification.
- **Skills recommending insecure practices** (running `eval()` on driver expressions from untrusted sources, disabling Blender's auto-execute-script protection in headless workflows, embedding credentials in `.blend` custom properties).
- **Headless batch scripts** that pass user-controlled input to `subprocess` or `os.system` without sanitization.

Issues with the Blender Python API itself (`bpy`, `bmesh`, `bpy_extras`) belong upstream at https://projects.blender.org and are out of scope here.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1.0 | No        |

## Response Timeline

We aim to acknowledge reports within 48 hours and provide a fix or mitigation within 7 days for confirmed issues.
