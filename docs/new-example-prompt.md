# Prompt: Create a new Blender example

Copy everything below this line into the agent.

---

Create, ship, and merge one original, runnable example for this repository. The bar is
not "a working example"; it is an example strong enough to anchor the gallery on its own.

First, review `CLAUDE.md`, `AGENTS.md`, `ROADMAP.md`, `examples/gallery.json`,
`docs/VISUAL-STYLE.md`, and several existing examples—study the strongest ones, not
just the nearest one. Use them to understand the repository's current conventions,
integration points, visual standard, and test structure. Check all existing examples
before choosing a subject so your contribution does not duplicate or slightly
repackage something already covered.

Before editing, inspect the Git state. Start from an up-to-date `main`, preserve unrelated
work, and create a focused feature branch. Never force-push or bypass hooks. Do not include
secrets, temporary renders, caches, or unrelated files.

Subject selection. Prefer the ROADMAP candidate pool if it has entries; otherwise choose
freely. Whatever the source, the subject must pass all of these tests before you write
code:

- It witnesses a real, load-bearing API contract—something with observable behavior
  that can drift, not a convenience wrapper or a tutorial topic. The strongest subjects
  are ones AI-generated Blender code commonly gets wrong: object-mode versus edit-mode
  data lifetimes, evaluated versus original data, ordering constraints, references that
  dangle after CustomData reallocation, APIs renamed or restructured between 4.5 LTS
  and 5.1.
- Its check can fail for a real reason. Before trusting any assertion, prove it catches
  the failure it claims to catch: temporarily break the contract (skip the pose, swap
  the buffer, use the legacy path) and confirm the check exits non-zero, then restore
  it. An assertion that cannot fail witnesses nothing. State in the README what failure
  each check would catch.
- Its correctness is independently derivable. The best checks compare Blender's output
  against a closed-form or independently computed expectation (re-implemented math, a
  round-trip through a raw buffer, a known geometric invariant), not against a value
  captured from a previous run of the same code.
- Its render is legible as proof. Someone glancing at the thumbnail should be able to
  infer what contract is being demonstrated. If the render would look the same whether
  the API worked or not, redesign the scene until failure would be visible.

Where an API diverges between 4.5 and 5.1, asserting each side's actual contract is part
of the witness—version-gate explicitly and document the divergence rather than papering
over it. If you discover an undocumented hazard while authoring (a crash, a dangling
reference, an ordering constraint), that discovery belongs in the code comments and
README; it is often more valuable than the original subject.

The example must:

- run headlessly in Blender 5.1 and Blender 4.5 LTS;
- perform deterministic checks of a real Blender API contract and exit non-zero on
  failure, with numeric tolerances chosen deliberately and printed on success so CI
  logs carry the measured values;
- default to a fast check-only run and optionally render its own gallery image;
- follow repository conventions and relevant Blender safety rules;
- include concise documentation explaining what it teaches, what each check witnesses,
  what failure it would catch, and any version-gated divergence between 4.5 and 5.1;
- produce a deliberate, well-framed render rather than a mockup, primitive dump, or
  placeholder.

Complete every integration required for a shipped example. Infer the exact current
shape from neighboring examples and repository configuration, including the example
directory, README, gallery metadata and assets, plugin manifest, smoke workflow,
top-level README, and generated gallery pages. After regenerating the gallery with
`python scripts/build_gallery.py`, read the **generated** output character by
character — not only `examples/gallery.json` source fields. Open
`docs/gallery/index.html` and `docs/gallery/<name>/index.html` and inspect the
rendered `<img alt>` text and the witnesses callout for duplicated words, truncation,
and generator artifacts (the previous `teaches.split(".")[0]` bug truncated alts at
dotted API paths like `bmesh.ops`; source JSON looked fine). Keep the ROADMAP
candidate pool in sync: remove the shipped subject, and add any promising subjects
you identified but did not build. Do not hand-edit release-owned version fields or
generated pages; use the repository's generator.

Run the new example's check-only path on both supported Blender versions. Locate local
Blender binaries by checking `.scratch/` at the repo root first — prior runs download
official releases there and some machines have no system install; download an official
release into it if a needed version is missing (it is gitignored) — then system installs.
Do not probe blindly; state the exact binary path and the version the binary itself
reports for every run. Render and visually inspect the final image, regenerate the
gallery, and run all relevant repository
validation. If Blender 4.5 is unavailable locally, say so precisely and use the repository's
4.5 CI job—do not substitute another version and report it as 4.5. If the render path
requires an engine or device unavailable locally (Cycles on a GPU-less host), say so and
identify exactly which paths were exercised only in CI or by inspection. Fix every
failure you introduce.

Treat visual quality as a shipping gate with the same rigor as the checks. Conform to
`docs/VISUAL-STYLE.md` explicitly (Standard view transform, dark studio stage, AREA
key/fill/rim/wedge, designed hero materials, framing, 1280×720 → hero/preview webp).
Inspect the actual rendered pixels at full size and as the gallery thumbnail.
Iterate—the first render is a draft, not a candidate. Revise until the subject and
demonstrated API contract are immediately readable, the composition is intentional,
important geometry is not clipped, highlights are not blown out, lights or helper
objects are not visible unintentionally, and materials, lighting, background, and
camera feel designed rather than left at Blender defaults.

Contact-sheet gate (required before shipping the still): place the new hero beside
the pinned calibration set — canonical membership is listed in `CLAUDE.md`
§ Quality Gates for Example Runs — and compare stage darkness, wedge warmth,
subject fill, saturation, and thumbnail legibility side by side. Do not ship until
the new image holds up in that lineup—not merely "looks fine alone." When a new
example outclasses a member, update the pinned set in `CLAUDE.md`, its canonical
home. One successful render
command is not proof that the image is good, and neither is the second. Commit the
composite under `docs/gallery/contact-sheets/`, link it in the PR body, and report
per-criterion verdicts including mean luminance versus the calibration images — a
claim without the committed composite is not acceptable evidence.

After implementation and local verification:

1. Review the complete diff and remove accidental churn or temporary files.
2. Commit the focused change with a conventional, release-worthy `feat:` subject that
   explains why the example belongs in the repository.
3. Push the feature branch and open a pull request against `main` with a concise summary,
   the API contract witnessed, what failure each check catches (and proof you falsified
   it once), visual notes, and an exact test plan. Label explicitly what was proven by
   live run versus established by inspection only.
4. Watch every attached PR check, including validation, manifest/count checks, ecosystem
   drift, Socket Security checks, and Blender 4.5/5.1 smoke jobs. Investigate and fix
   failures within this change's scope, push fixes, and repeat until all checks pass. A
   pending or failing Socket check is unresolved — wait before merging.
5. Review PR comments and requested changes. Apply valid feedback and re-run affected
   checks. Do not merge with unresolved failures or requested changes.
6. Once the PR is mergeable and green, squash-merge it and delete the remote feature
   branch.
7. Wait for any automated release/version-sync commit triggered by the merge, then
   fast-forward local `main` to `origin/main`, and verify main HEAD is green including
   all post-merge jobs (Release, Validate, Ecosystem drift check, Deploy GitHub Pages).
   The smoke jobs are pull_request-triggered and do not re-run on the merge SHA: the
   post-merge evidence is that both smoke jobs passed on the PR head SHA that became
   the sole squash-merged commit. Do not hand-edit release-owned version fields.
8. Confirm the final working tree is clean and report the PR URL, merge commit, resulting
   version (if released), measured check values, and checks completed.

Do not stop at a proposal or ask me to choose the topic. Explore, choose, implement,
verify, ship, merge, synchronize, and report the completed result. Only stop for a real
blocker that requires user action, such as authentication, an unavailable required
runtime with no CI substitute, a merge policy requiring approval, or unrelated local
changes that cannot be safely preserved.