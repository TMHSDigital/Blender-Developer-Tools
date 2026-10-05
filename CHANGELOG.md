# Changelog

All notable changes to this project will be documented in this file.

## [0.143.10] - 2026-10-05

### Fixes

- fix(gallery): render inline code in callouts; add the asset-sheet gate to the example prompt (#422) ([`ca5fd97`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ca5fd97905c74cd35a031dfb5cb58a91282dd28d))

[Release v0.143.10](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.10)

## [0.143.9] - 2026-10-05

### Fixes

- fix(examples): free hay-bale's bmesh on every path; per-run depsgraph-export OBJ (#421) ([`db2ca4b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/db2ca4b4d876b62852447419923a46b321b96b1e))
- fix(skills): document that registered props are not ID properties on 5.0+ (#420) ([`b612f3a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b612f3ac8848ace30138c5c29b482ae8568432b7))

### Other

- docs(roadmap): keep only open candidates and define what 1.0 means (#425) ([`e0d73a9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e0d73a997bf393b6f9bfe551e02c14113d766155))

[Release v0.143.9](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.9)

## [0.143.8] - 2026-10-05

### Fixes

- fix(ci): close five gates that checked less than they claimed (#419) ([`536f60f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/536f60f895c8bed1d4522616327b24c5a9a49363))

[Release v0.143.8](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.8)

## [0.143.7] - 2026-10-05

### Fixes

- fix(snippets): export Y-up, meter glTF for Godot and Unreal too (#417) ([`74813ec`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/74813ecc93683910997a14a3f3413f42472fc872))

[Release v0.143.7](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.7)

## [0.143.6] - 2026-10-05

### Fixes

- fix(testing): bound every smoke run with a timeout and decode output as UTF-8 (#416) ([`192e1b1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/192e1b177cce4148f65bbfe7f5483bbab88f03a4))

### Other

- docs(examples): stop READMEs saying smoke skips the flag CI runs as the falsifier (#415) ([`2cdde2c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2cdde2cf8a98e855ed944434e8c009bc93f2c161))

[Release v0.143.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.6)

## [0.143.5] - 2026-10-05

### Fixes

- fix(skills): correct measured-false claims across eight skills and two rules (#414) ([`040e994`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/040e994e91a2fe5adf4d3649950686d09f763b5c))

[Release v0.143.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.5)

## [0.143.4] - 2026-10-05

### Fixes

- fix(templates): apply rotation as well as scale before grounding the origin (#412) ([`8960f3f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8960f3f44d75f74ab1fa4cf0eefbd2d6fe6a06ec))
- fix(skills): re-register driver functions on file load (#411) ([`e1d8310`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e1d8310a9b3a012d31c44b7603347c7c90e6baf8))
- fix(skills): correct four API claims that make agent code silently wrong (#410) ([`ae57f0d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ae57f0dc2f668b594509dae93d749537ff21dd90))
- fix(scripts): refuse destructive --out targets and skip fork PR labelling (#409) ([`e5f7938`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e5f7938ccf76324bfb306f060eebb42cc215efc0))

[Release v0.143.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.4)

## [0.143.3] - 2026-10-04

### Fixes

- fix(snippets): hull only the points so convex colliders come out closed (#407) ([`bc926e3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bc926e38a123994adc50bce8473f9402c6e741c7))
- fix(examples): give gn-bundle-roundtrip a falsifier that can fail (#408) ([`9548e80`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9548e800ca63eb50483137405aa81f899a3f2185))
- fix(snippets): bind the action slot on the 4.5 LTS channelbag path (#406) ([`350b75d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/350b75df6c2f8d6f4d25520ad5b35d402b37b511))

### Other

- docs: describe the smoke push trigger and the full release-owned file list (#413) ([`bdaeb95`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bdaeb954fb91bf431e73bfe973e72d6a3374b088))

[Release v0.143.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.3)

## [0.143.2] - 2026-10-04

### Fixes

- fix(site): landing showcase cards caption the piece, not the shared pipeline ([`c5880ba`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c5880bad43586c271a7de6cd2d070b0a2ff12687))
- fix(site): scrollspy marks Examples and Showcase while their sections are in view ([`a882bd6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a882bd6fa1f608b04c3b2749cfe0f0049a3d0850))
- fix(gallery): nine showcase witness callouts quoted pre-remodel numbers ([`fc087a8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fc087a86bf264895e219b42480cb6e67d317b772))

### Other

- docs(gallery): tighten the gallery index lede ([`afa5015`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/afa5015d49d7152ca2ea38b069f7c1f053ec28a8))

[Release v0.143.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.2)

## [0.143.1] - 2026-10-04

### Fixes

- fix(showcase): moka-pot gets brushed, heat-tinted aluminium ([`5a9aee8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5a9aee8b50ec34459de148572bb90eeffe9b7a5a))
- fix(showcase): remodel iron-cauldron (chain, forged head, casting band, feet, cast-iron finish) ([`e6a0d68`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e6a0d68209d29eefe3aba64994fd2b9c110d0c13))

### Other

- docs(gallery): rebuild temp-override-join contact sheet against the current calibration set ([`fe0bd2f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fe0bd2fd615a460cca6caebac81322b1fcaf5d36))
- test(smoke): each showcase row re-proves a piece-specific falsifier, not --skip-decimate ([`2cac933`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2cac93340a37ffe865bfe6101b548503417c1e1b))
- docs(showcase): asset sheets for the last 17 pieces; 76/76 now carry one ([`7602b28`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7602b2888b45a9b3b9b7cb85b11e2f59022ffc01))

[Release v0.143.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.1)

## [0.143.0] - 2026-10-04

### Features

- feat(distribution): install the plugin from a slim, bot-built plugin-dist branch ([`08c6672`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/08c6672d46bf8dfb73bd218e9392eefb59db61f7))
- feat(site): JPEG og:image on every page, a sitemap, and a sharper description ([`60f388a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/60f388a9f76fbfc729c0044ac722e36006d4346b))
- feat(distribution): plugin ships the rules as a skill; skill file refs work outside a checkout ([`cf881a7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/cf881a7fe4f7f1b71521b688a8e10029ecaca07a))
- feat(smoke): every catalog row re-proves a falsifier on every smoke run ([`275e23d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/275e23dbba94fee429dec8ef1abeef5a3eee061d))

### Fixes

- fix(smoke): version-gate the four falsifiers that target a 5.2-only API change ([`449101a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/449101a2622e9be1fb0d41826d8716895e65b279))
- fix(showcase): one canonical convex_hull_collider and export_unity; report helper drift ([`fe0fcef`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fe0fcef63f003413597fabd97066c3ed2bac3c2d))
- fix(showcase): all 76 pieces run the asset-quality floors; lint enforces it ([`60506e8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/60506e85534af496c6c5150b65b64e96b7e8ce80))
- fix(examples): gate compositor-glare and collision-hull-proxy stills; lint every gallery entry ([`2bd2041`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2bd20412059afb3dbee0dedc4c7394f6397494e4))

### Other

- chore(deps): Bump actions/cache (#317) ([`216188b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/216188bdcfb7fa4208aa6c920dc1f68aa5c2df7c))
- docs(readme): replace the 1,300-line catalog with a featured strip and the gallery ([`2335989`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/233598953e96187f47b083b48b675a3fa2f70164))
- perf(gallery): link each script instead of inlining it; LF-pin generated files ([`0bb1d1a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0bb1d1a6f47b6ff534cdf47c4175df853c2b3ef1))
- docs: one consistent Claude Code install path, plus updating and uninstalling ([`d59b154`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d59b154451856b61adcc74f176b4da3754cb61d1))
- docs(license): say plainly that building commercial or GPL add-ons is fine ([`c35d441`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c35d441024c5fb9032a4de03f10f69196f622b58))
- ci: release notes and CHANGELOG entries list what actually shipped ([`d8521f9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d8521f920055fef3fbcbe0f762a56ae153c86db5))

[Release v0.143.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.143.0)

## [0.142.4] - 2026-10-04

See [release notes](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.142.4) for details.

## [0.142.3] - 2026-10-04

### Fixes

- fix(gallery): regenerate export-preset-axis page after the #326 source change ([`9a22f58`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9a22f58c7897e64813bbce343722c8e886d34648))
- fix(content): OBJ uses export_eval_mode; USD modifier rule keys on export_subdivision ([`17c4ca1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/17c4ca16a4bc05b62cfed6697723b3b4e3d3f213))
- fix(rules): bulk-data and bmesh rules name only attributes that exist and are writable ([`f293573`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f2935733ae82ce07d11cc9e8b4c4b85236f6078e))
- fix(skills): headless guidance matches what --background actually runs ([`2d4e769`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2d4e7699fff24644ef3a89b3626f15374aa4d8f3))
- fix(skills): extension id rules match Blender's validator; permissions are not a sandbox ([`0583b45`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0583b45f96a301626f9fdcab4e65a90906457e50))
- fix(skills): procedural-materials 4.5 socket residue, Specular date, use_nodes on 5.x ([`c3ca5d8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c3ca5d8cf635197086a9b727e13f343a8395fa1a))
- fix(content): port the #297/#298 export contract to template, skill, rule, example ([`3b0f5a0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3b0f5a041240fe72bc61dd9f26571c0eac63f07f))

### Other

- ci: link gate checks the staged Pages tree; exit-code gate resolves named codes ([`7afd8a3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7afd8a3199ddb41ad31373efb4259848ec1f71ed))
- ci: validate-counts checks every stated copy of every count, incl. CLAUDE.md ([`579410a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/579410a6ffc88eed847f708add8861eac9b7b676))
- ci: bump detection reads BREAKING CHANGE footers, not prose in subjects ([`422c0e5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/422c0e5828ae3ee9f7af8d190f7559ce8a7aaa9c))
- ci: run Blender Smoke on push to main and gate direct-push releases on it ([`10fcd33`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/10fcd33182f0c1384ba4cb778d72fe552dd4ab75))

[Release v0.142.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.142.3)

## [0.142.2] - 2026-10-04

### Fixes

- fix(ci): release gate reads PR checks once and fails closed on gh errors ([`502613e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/502613e924c3e18bf301e575db26a34e27f251d9))

[Release v0.142.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.142.2)

## [0.142.1] - 2026-10-04

### Fixes

- fix(smoke): pass --python-exit-code 1 so an uncaught exception is red ([`edd6ab5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/edd6ab5074a5e5d82df681b9500ad7db83df1860))

[Release v0.142.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.142.1)

## [0.142.0] - 2026-10-04

### Features

- feat(site): center the 404 card and make Open the gallery the primary action ([`f26dbee`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f26dbeee85ad0991bcbee90939773bc893f6ee1f))

[Release v0.142.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.142.0)

## [0.141.0] - 2026-10-04

### Features

- feat(gallery): redesign the filter bar into pinned row + centered topics panel ([`03d408a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/03d408a57bcfaccbd99e562e494225bff933ff01))

[Release v0.141.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.141.0)

## [0.140.1] - 2026-10-04

### Fixes

- fix(site): Lighthouse a11y and layout-shift fixes (chip count contrast, HUD targets, font preloads) ([`0b57fe7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0b57fe7047d89f6ab691b778f6deae2f0bf01aba))

[Release v0.140.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.140.1)

## [0.140.0] - 2026-10-04

### Features

- feat(site): nav scrollspy and a five-step type scale ([`fd2aab7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fd2aab73d9e45f9c984db8684a4703a724410184))

[Release v0.140.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.140.0)

## [0.139.0] - 2026-10-04

### Features

- feat(gallery): Examples-first and By-category sorts, Back undoes filter changes ([`e801ca9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e801ca90d73f76b4bb4be0dbfea2cc3fe7bef028))

[Release v0.139.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.139.0)

## [0.138.0] - 2026-10-04

### Features

- feat(site): center section headings and short content, keep dense content left ([`ef5a630`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ef5a63056fd74c46ed59394080fb586b50576f88))

[Release v0.138.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.138.0)

## [0.137.0] - 2026-10-04

### Features

- feat(gallery): topic chip counts and removable active-filter pills ([`5a17c92`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5a17c92ea33d8bdd0c3ebc3ccf674ca902de6006))

### Other

- chore: gitignore .playwright-mcp session captures ([`36ae4a9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/36ae4a987be053583e065215063105dcc7318f22))

[Release v0.137.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.137.0)

## [0.136.0] - 2026-10-04

### Features

- feat(gallery): jump-to nav on detail pages, header-safe anchor offset ([`0f8369d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0f8369dd3f15ece1e7291f1a992c2c373c3eec84))

[Release v0.136.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.136.0)

## [0.135.0] - 2026-10-04

### Features

- feat(gallery): pin only the search row on wide screens ([`3609135`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/36091352d2abd3e8c719ec68ad5773c6b39e11c3))

[Release v0.135.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.135.0)

## [0.134.0] - 2026-10-04

### Features

- feat(gallery): showcase badge, 2-line teasers, wrapping topic chips ([`80a18f5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/80a18f506f05eaa8716c26ba0419acc6013c5b48))
- feat(site): landing hero primary CTA, install after proof, legibility fixes ([`d6aa585`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d6aa5852c9429f3fb956f88a91503242b77a4716))

[Release v0.134.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.134.0)

## [0.133.0] - 2026-10-04

### Features

- feat(site): GitHub Sponsors button in README, landing hero, and footer (#318) ([`647e066`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/647e066f52a2fa1040545a7e6f385a4f44006477))

### Other

- docs(license): MIT for snippets/ and templates/ so copy-and-adapt is lawful (#316) ([`c9bb998`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c9bb9988cf2ab90636695b0ea96eafe8c7e2481d))
- build(deps): Bump markupsafe from 3.0.2 to 3.0.3 in /scripts/site (#311) ([`c381296`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c381296f2bb8bf3858c5e230e4e6fcd527e87c01))
- chore(deps): Bump the github-actions group with 2 updates (#313) ([`5beeca4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5beeca48c58157317fe32d3478d7ebff01a143d2))

[Release v0.133.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.133.0)

## [0.132.1] - 2026-10-03

### Fixes

- fix(scripts): measure_hero_drift exits non-zero on size mismatch, unknown --only, empty run (#315) ([`89cec34`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/89cec344018496ecadb69177d0b412f1485c2442))

### Other

- ci: smoke the shipped templates, enforce catalog completeness, parse frontmatter, cache and verify Blender (#314) ([`0dbb94b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0dbb94bbb0ad9b1fb99700b96ecebfc3c19b9e4a))
- ci: gate releases on CI evidence, stand down on stale SHA, SHA-pin actions, group dependabot (#312) ([`5185e66`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5185e6623c71860030324aaa1aab8550dc41d4ff))

[Release v0.132.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.132.1)

## [0.132.0] - 2026-10-03

### Features

- feat(distribution): Claude Code plugin, rules bridge, Pages trim, count and cap gates (#310) ([`ae0d859`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ae0d859fcb6fe2eb5f3b680ecee02ba3d584c4f7))

[Release v0.132.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.132.0)

## [0.131.2] - 2026-10-03

### Fixes

- fix(content): correct 4.5 node-group API, Unreal location scale, export-preset apply, version facts (#309) ([`fefd033`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fefd0339c7f04bb333f8526142caae53ef6491d7))

[Release v0.131.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.131.2)

## [0.131.1] - 2026-10-03

### Fixes

- fix(gallery): refresh cards and README tiles for the six quality-passed pieces ([`3a13608`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3a136087292c27ffa742ef83c09b4e8af8e0d86d))
- fix(examples): boolean-exact-volume quality pass: labelled operations, ghost-glass operands, walnut plinth ([`8017850`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/80178506f41c5a8de26b47fe4412176708893f97))
- fix(examples): solidify-even-thickness quality pass: measured full-thickness line, glazed shells, legible plaques ([`5ef7e2e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5ef7e2ef779da722b8e0000c9bfd0b6e83af4396))
- fix(showcase): sawhorse-plank quality pass: tapered legs, arrised edges, steel-sheened saw, tighter frame ([`1987df5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1987df58daa817052f83cf29adeb1b55652d13d3))
- fix(showcase): ships-wheel quality pass: helm-stand pedestal, rounded rim, wheel fills the frame ([`596e8bc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/596e8bc804541a7ad71cbda3434cd30c17fbc499))
- fix(showcase): mine-cart quality pass: per-member timber grain, worn paint, ore load, even rail rust ([`294dcc5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/294dcc53d44c8c86e43a92e1bd71b276f6c570d0))
- fix(showcase): garden-gate quality pass: real oak grain, braced side on show, brace-direction witness ([`1c85142`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1c85142ceca984e8e103f1d5ceb17d15ef7f474d))

[Release v0.131.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.131.1)

## [0.131.0] - 2026-10-03

### Features

- feat(showcase): add sawhorse-plank piece ([`aca0a5a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/aca0a5a671f750b8ec12a09a97992f526785ec97))

[Release v0.131.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.131.0)

## [0.130.0] - 2026-10-03

### Features

- feat(showcase): add ships-wheel piece ([`b21a221`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b21a221a05aac2be16d7e9e98c41c48a29494aa9))

[Release v0.130.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.130.0)

## [0.129.0] - 2026-10-03

### Features

- feat(examples): add solidify-even-thickness and boolean-exact-volume (#305) ([`6ea4ed9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6ea4ed981ef4ef6fe741942e86d6809d9c532a7d))

[Release v0.129.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.129.0)

## [0.128.0] - 2026-10-02

### Features

- feat(showcase): add garden-gate piece ([`c3d778d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c3d778d57cac5401b687684108c9ac79b3702d0c))

[Release v0.128.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.128.0)

## [0.127.0] - 2026-10-02

### Features

- feat(showcase): add mine-cart piece ([`b9d3ec1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b9d3ec1d6e2339c3294c602c4a449de4fd03beec))

[Release v0.127.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.127.0)

## [0.126.0] - 2026-10-02

### Features

- feat(examples): add ray-cast-space and lattice-deform (#304) ([`f7511b1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f7511b12b169a893c4c8354ad84e196cc31e7b68))

[Release v0.126.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.126.0)

## [0.125.1] - 2026-10-02

### Fixes

- fix(site): 24px touch targets on the phone stats readout ([`e45f414`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e45f4140f0291567f1490a425b290a8ed95d4cd2))

[Release v0.125.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.125.1)

## [0.125.0] - 2026-10-02

### Features

- feat(site): shared header/footer, mobile nav, and gallery search/filter facelift ([`66a126f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/66a126f686625cf6ca08f872141a78d33e531b68))
- feat(gallery): 640px card variants of every hero, with make_thumbs.py ([`c9a3b32`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c9a3b32c7af4cf40366c33356a5d8b06e9dbcd31))

### Other

- docs: record the 640px card variant in the example and showcase wiring ([`df88d41`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/df88d4129779464ceab2c3335ce77adc0305059b))

[Release v0.125.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.125.0)

## [0.124.1] - 2026-10-02

### Fixes

- fix(showcase): refresh gallery cards and README tiles for the five quality-passed pieces ([`7e192f1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7e192f1bbf97f937465aca69f7f38c5edf9dea0a))
- fix(showcase): ([`ca0c508`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ca0c50831873d9da9b00d192d34db226773055bd))
- fix(showcase): ([`7902563`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/79025630d1ee3ffdb5a6eab2c1cb78af9ed1234a))
- fix(showcase): ([`b3949b1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b3949b1cf17daf7c94d3a33a6a8384ee6fde04a1))
- fix(showcase): ([`b7c8a7f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b7c8a7f69a2989193dcad980d75ff7e36509ba2c))
- fix(showcase): ([`70f0cc3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/70f0cc310d8658e204d183b92b86d46dc5ea56dd))

[Release v0.124.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.124.1)

## [0.124.0] - 2026-10-02

### Features

- feat(showcase): wire moka-pot, cricket-wicket, bamboo-clump, toboggan, sundial into catalog, gallery and README ([`2fe2954`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2fe2954680b8b332ffb099146337ad391961f754))
- feat(showcase): add sundial piece ([`002168e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/002168e75b12481b195842b00078b3214a272708))
- feat(showcase): add toboggan piece ([`7f71466`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7f71466c8825ce0915f7abecf1d5402477493c44))
- feat(showcase): add bamboo-clump piece ([`ac2973f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ac2973fa20bd5a123250b91b104295a24d13f85a))
- feat(showcase): add cricket-wicket piece ([`a5bee99`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a5bee995c7150b670a1d2e490f0600cf629abac5))
- feat(showcase): add moka-pot piece ([`0f6efdf`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0f6efdfd38f787b8abc57d6094738faa1876530f))

[Release v0.124.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.124.0)

## [0.123.14] - 2026-10-01

### Fixes

- fix(showcase): rebuild the anvil to London-pattern proportions ([`65146ad`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/65146ad65bce437b42be634ea1c5c4b8fc95024b))

[Release v0.123.14](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.14)

## [0.123.13] - 2026-09-30

### Fixes

- fix(showcase): anvil quality pass, forged body instead of stacked boxes ([`810d88f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/810d88f32488c7b9bd3c24208cc91bbe0fd3c016))

[Release v0.123.13](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.13)

## [0.123.12] - 2026-09-30

### Fixes

- fix(showcase): reprofile the chopping-block axe head so it reads as an axe ([`6fd9997`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6fd99971fa95c24540e6f7aa2d3c70db17700a5d))

[Release v0.123.12](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.12)

## [0.123.11] - 2026-09-30

### Fixes

- fix(showcase): chopping-block quality pass: no lid, steel head, real billets and chips ([`1c272da`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1c272daf9b53962e1839ee93fbf75d8714e77139))

[Release v0.123.11](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.11)

## [0.123.10] - 2026-09-30

### Fixes

- fix(showcase): give hay-bale packed flakes and a stem-mat end instead of felt and gashes ([`521cb91`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/521cb91a5afb1a2adef024e42c8b381a1491beca))

[Release v0.123.10](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.10)

## [0.123.9] - 2026-09-30

### Fixes

- fix(gallery): carry the new parent-inverse-orrery alt onto related-card pages ([`2f3faf8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2f3faf874a52fe6f5666e4e0495a10d9d6d896d5))
- fix(examples): parent-inverse-orrery and depsgraph-export quality pass ([`657e459`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/657e45929754b11c0abe8f17ccc358423d445a4b))

[Release v0.123.9](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.9)

## [0.123.8] - 2026-09-30

### Fixes

- fix(showcase): give traffic-cones level tyre and boot rub marks on the cones and their collars ([`bfa2d59`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bfa2d599096567a1e562e22ae52b812ad945c795))

[Release v0.123.8](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.8)

## [0.123.7] - 2026-09-30

### Fixes

- fix(showcase): wrap farm-tractor's chevron bars round the shoulder, 34 mm tall, with mud packed between them ([`6db4540`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6db4540874eed5ad42bbcd9e4a41a15387306063))

[Release v0.123.7](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.7)

## [0.123.6] - 2026-09-30

### Fixes

- fix(showcase): remodel go-kart bodywork as blue mouldings on welded strap brackets, with brake hose, throttle cable and wear ([`4be60f5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4be60f5bf781c8566c5037e3e91d1941131f7cdb))

[Release v0.123.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.6)

## [0.123.5] - 2026-09-30

### Fixes

- fix(showcase): remodel sea-stack-arch as one eroded headland mass in a sea that fills the tile ([`45170c1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/45170c17f1caf18badea38d68b04e16401be3fc6))

[Release v0.123.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.5)

## [0.123.4] - 2026-09-30

### Fixes

- fix(showcase): remodel fern-mossy-rock with a cleaved gritstone boulder and feathered, lobed moss ([`e00d72a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e00d72abec80bebcef538447f33704f9982bc8c5))

[Release v0.123.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.4)

## [0.123.3] - 2026-09-30

### Fixes

- fix(showcase): remodel broadleaf-oak as a massive mature oak with a cushioned leaf-mass crown ([`13e2ec0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/13e2ec035a29f8bc3764c53ca4cfc094e1d15ac2))

[Release v0.123.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.3)

## [0.123.2] - 2026-09-30

### Fixes

- fix(showcase): remodel mushroom-stump with a stepped felling cut, recessed peels, conforming moss and bipinnate ferns ([`6f4aab1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6f4aab133f60b32f49c506e568acb56f34fd8bbd))

[Release v0.123.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.2)

## [0.123.1] - 2026-09-30

### Fixes

- fix(gallery): regenerate stale sea-stack-arch detail page ([`9d5ec3a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9d5ec3a3373caed51ac750adcab55765e1e27bac))

[Release v0.123.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.1)

## [0.123.0] - 2026-09-30

### Features

- feat(showcase): add sea-stack-arch (nature) ([`fd8f0ca`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fd8f0cad1a151c2d86a94df7c9876097505626a5))

[Release v0.123.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.123.0)

## [0.122.0] - 2026-09-29

### Features

- feat(showcase): add fern-mossy-rock (nature) ([`45e45e0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/45e45e0d1a1133edf630f998a3ee4f850346b35d))

[Release v0.122.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.122.0)

## [0.121.0] - 2026-09-29

### Features

- feat(showcase): add farm-tractor (vehicles) ([`64ceb77`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/64ceb77d2e5d77c99982af1702bf4474775a0e15))

[Release v0.121.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.121.0)

## [0.120.0] - 2026-09-29

### Features

- feat(showcase): add broadleaf-oak (nature) ([`35ebfdc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/35ebfdc9c282dce8d82f14336816f792eb21c579))

[Release v0.120.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.120.0)

## [0.119.0] - 2026-09-29

### Features

- feat(showcase): add go-kart (vehicles) ([`39573d7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/39573d76bde4e5f66975385dbbd0d18bff9caf3e))

[Release v0.119.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.119.0)

## [0.118.0] - 2026-09-29

### Features

- feat(showcase): add mushroom-stump (nature) ([`4b2c66b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4b2c66b2b2d3b66c745873ddce962d3ef58a639f))

[Release v0.118.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.118.0)

## [0.117.0] - 2026-09-29

### Features

- feat(showcase): add traffic-cones (vehicles) ([`7ad90c9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7ad90c98402ed4d52242285e83df2cba6de93a0b))

[Release v0.117.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.117.0)

## [0.116.4] - 2026-09-29

### Fixes

- fix(showcase): give hover-bike pinned link-and-shock landing gear, aerofoil pylons and a panelled fuselage ([`b66e13b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b66e13becea7071f8de3071dd665b3489b5acb7b))

[Release v0.116.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.116.4)

## [0.116.3] - 2026-09-29

### Fixes

- fix(showcase): remodel office-chair as a mesh task chair on a chair mat beside a snake plant ([`391a5c6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/391a5c69a6a4bd941cc47f43de6fac7bba277a54))

[Release v0.116.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.116.3)

## [0.116.2] - 2026-09-29

### Fixes

- fix(showcase): remodel basketball-hoop as a court-side hoop on a painted concrete pad ([`ddde8ce`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ddde8ce73fb0faa6678a89b07291a3897b80e147))

### Other

- docs(showcase): fix wingback ordinal and two alts that describe hidden detail ([`9be99b7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9be99b7117af619c945b021df210f8b2e3a77d46))

[Release v0.116.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.116.2)

## [0.116.1] - 2026-09-29

### Fixes

- fix(showcase): remodel pine-tree as a dense, plated-bark mature Scots pine ([`4dcb601`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4dcb60187a33a7dc1dd9f54fc33ee57f9fb5a4cd))

[Release v0.116.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.116.1)

## [0.116.0] - 2026-09-29

### Features

- feat(showcase): add planet-rover (vehicles) ([`80d88b3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/80d88b3716df1c68e34311e000095e7d1cc5af26))

[Release v0.116.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.116.0)

## [0.115.0] - 2026-09-29

### Features

- feat(showcase): add wingback-armchair (household) ([`2dd464d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2dd464d883f2a6a2446671914ac03b0387f35891))

[Release v0.115.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.115.0)

## [0.114.0] - 2026-09-29

### Features

- feat(showcase): add palm-tree (nature) ([`ef32c01`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ef32c018ec6110c91fb4275b7c3d79b02def4b00))

[Release v0.114.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.114.0)

## [0.113.0] - 2026-09-29

### Features

- feat(showcase): add skate-ramp (sports) ([`f04640f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f04640f54e339fc78cfc3012e1300116da3e0780))

[Release v0.113.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.113.0)

## [0.112.0] - 2026-09-29

### Features

- feat(showcase): add road-bicycle (vehicles) ([`77375d0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/77375d0cbf8cf6c1b0dcbaaf02396f5ea3f52cd2))

[Release v0.112.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.112.0)

## [0.111.0] - 2026-09-28

### Features

- feat(showcase): add espresso-machine (household) ([`29cffbc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/29cffbcd18a5321b3294744941b475643aa265a5))

[Release v0.111.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.111.0)

## [0.110.0] - 2026-09-28

### Features

- feat(showcase): add cactus-garden (nature) ([`efc489c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/efc489c388e789bc623ec9eb6e8d937a9e3331e4))

[Release v0.110.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.110.0)

## [0.109.0] - 2026-09-28

### Features

- feat(showcase): add archery-target (sports) ([`2205044`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2205044c3f64321f8724744a47959782bc237cce))

### Other

- docs(agents): correct showcase piece count to 52 ([`d766fe0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d766fe07c0c727f12eea3490cad6705e0af54a75))

[Release v0.109.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.109.0)

## [0.108.0] - 2026-09-28

### Features

- feat(showcase): add cargo-loader (vehicles) ([`c894e0b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c894e0b2cb16553f6175cdd63cbe697b2d5e88ca))

[Release v0.108.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.108.0)

## [0.107.0] - 2026-09-28

### Features

- feat(showcase): add stand-mixer (household) ([`3f715e2`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3f715e2bf596668761e480e559455ea1b17d4e78))

[Release v0.107.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.107.0)

## [0.106.0] - 2026-09-28

### Features

- feat(showcase): add pond-edge (nature) ([`55f47fe`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/55f47fe1981bedb5f1b2729f8f260f646d8d20c6))

[Release v0.106.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.106.0)

## [0.105.0] - 2026-09-28

### Features

- feat(showcase): add bowling-pins (sports) ([`e3a3884`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e3a3884d1a8c7df758154cade97123c3959f0862))

[Release v0.105.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.105.0)

## [0.104.0] - 2026-09-28

### Features

- feat(showcase): add motor-scooter (vehicles) ([`456cf59`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/456cf598fc585568806263b8a3cdc18e2183c83d))

[Release v0.104.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.104.0)

## [0.103.0] - 2026-09-28

### Features

- feat(showcase): add floor-fan (household) ([`baceb32`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/baceb32256c38fd75c5f643c58aabf92801ec624))

[Release v0.103.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.103.0)

## [0.102.0] - 2026-09-28

### Features

- feat(showcase): add boulder-cluster (nature) ([`2074b03`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2074b0326e134c0cd43066586a226ab2556c1f55))

[Release v0.102.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.102.0)

## [0.101.0] - 2026-09-28

### Features

- feat(showcase): add weight-rack (sports) ([`bc898b4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bc898b4177687a295befbf449b19ece493b0ceed))

[Release v0.101.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.101.0)

## [0.100.0] - 2026-09-28

### Features

- feat(showcase): add hover-bike (vehicles) ([`8f68aec`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8f68aecbf35ba68a942505d3f0a10e8592198023))

[Release v0.100.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.100.0)

## [0.99.0] - 2026-09-28

### Features

- feat(showcase): add office-chair (household) ([`8202fc7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8202fc7fb1104caf02f72458f90c193af4c51d89))

[Release v0.99.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.99.0)

## [0.98.0] - 2026-09-28

### Features

- feat(showcase): add fallen-log (nature) ([`5e371e8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5e371e8cd63f17a588c8a366c2d94b161988bd1b))

[Release v0.98.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.98.0)

## [0.97.0] - 2026-09-28

### Features

- feat(showcase): add soccer-goal (sports) ([`52c15f4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/52c15f4942fcb34b42aed526f44853bf1a5e8416))

[Release v0.97.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.97.0)

## [0.96.0] - 2026-09-28

### Features

- feat(showcase): add quad-drone (vehicles) ([`2c14744`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2c147447487f66e8fc786afb4e3184e8b95f0994))

[Release v0.96.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.96.0)

## [0.95.0] - 2026-09-27

### Features

- feat(showcase): add desk-lamp (household) ([`3392d94`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3392d940d21cfdf0aa096a210e85f7f9da2040f5))

[Release v0.95.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.95.0)

## [0.94.0] - 2026-09-27

### Features

- feat(showcase): add pine-tree (nature) ([`ac418ad`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ac418ad7ff42e5d23c7c15335457622ec7f05c93))

[Release v0.94.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.94.0)

## [0.93.0] - 2026-09-27

### Features

- feat(showcase): add basketball-hoop (sports) ([`abf2134`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/abf2134f1b5d7be6dfda2065b9de4daabdef4d14))

[Release v0.93.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.93.0)

## [0.92.0] - 2026-09-27

### Features

- feat(showcase): add gallery categories and backfill pieces as village ([`d3c574f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d3c574f42b1856c0b950050d6f08d8c7916d8f9d))

[Release v0.92.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.92.0)

## [0.91.6] - 2026-09-27

### Fixes

- fix(showcase): give water-trough rippled water, bolted clipped straps, pegs and a bung ([`63ede13`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/63ede13b1d834b65bb399751021dfc5e9473f9ec))
- fix(showcase): model street-lantern as a fluted, scrolled cast-iron lamp ([`b495655`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b4956556e6317f0d5271aee06763fb3d2aeb6aae))
- fix(showcase): model hand-pump as a cast village pump with a hooped bucket ([`2e37948`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2e37948f036fcacda42cdaf204b4fad7485390b7))
- fix(showcase): give wooden-ladder through-tenons, iron tie-rods and two-tone timber ([`3f51dde`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3f51ddec65d61f741d93f45562dec4e318caac76))
- fix(showcase): set the chopping-block hero to work with split billets and chips ([`af7a90c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/af7a90c90410af9b5164e7424fc229a8371bdf67))
- fix(showcase): turn the grindstone crank to camera and fill its trough ([`506200d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/506200de55eb860eaf58d6c05f801aed4c6b0898))
- fix(showcase): dish the tavern-stool seat, stand the hero level, add a tankard ([`4756b5d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4756b5dea241e9ef9100f5e828e1fdb282447d63))

### Other

- docs(gallery): regenerate pages and contact sheets for round-four redesigns ([`b197ab7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b197ab764e945f54db002e02d28103e40114428f))

[Release v0.91.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.91.6)

## [0.91.5] - 2026-09-27

### Fixes

- fix(examples): redesign attribute-domain-shear staging as a paver patio with slate placards ([`e178446`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e17844666c25b08dc0c49b8e88611e481033abe6))
- fix(examples): redesign image-pixels-testcard as a hooded reference monitor on a walnut desk ([`6cc85f8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6cc85f8e8f22f5de326b58ca811d442b11216bb2))
- fix(examples): redesign light-link-studio as two porcelain chess kings under one linked key ([`f5effd7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f5effd72a0c5dceb63cd7daa62a4659176ca39ad))
- fix(showcase): hitching-post rail on knee braces with iron end caps ([`5a29c6f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5a29c6feb87c7c82aba342654a300cf4388489a4))
- fix(showcase): turn wooden-ladder rungs and give its wood readable grain ([`33051ef`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/33051efe59386862ab1f3faec82d53c4c5326e6b))
- fix(showcase): fence-kit hero shares one post at each joint ([`e2f3b9d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e2f3b9dd8d20e071e87fcdd5d0f667b7aacbc2cf))
- fix(showcase): frame the watchtower close and low, level it, weather its roof ([`d191ee8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d191ee8a3d59928689cd3acf76ed51bf53900a09))
- fix(showcase): make the water-trough water read as liquid and rust its iron ([`731c5a3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/731c5a37917fac1f0e9376aa1c4cfbd758f0018a))
- fix(showcase): char the campfire logs, crack the coals and soot the ring ([`c5952b8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c5952b8ba4c414dfd68fa1a96ddf8f631cd408e6))
- fix(showcase): dress the anvil hero with a polished face, a hammer and forge light ([`20849f2`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/20849f220644014365eea6ea53e32decc397536c))
- fix(showcase): paint hand-pump green enamel and rim-light its silhouette ([`8fc90b5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8fc90b5755814942e4f201c78d73d12b00a47596))
- fix(showcase): light street-lantern from inside and frame it larger ([`323ce64`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/323ce64eed78a28c9c3a38dffbb543603369560d))
- fix(examples): redesign swatch-grid as a labelled sample case on a walnut riser ([`dc04ef3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/dc04ef3531da209ef9471cc7615b2f087db30b15))
- fix(examples): redesign turntable as a lathed display turntable with a frame-tick dial ([`ecb452c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ecb452cbe04f418b386405d07fe1ac08fc6ba288))

### Other

- docs(gallery): regenerate pages and contact sheets for round-three redesigns ([`75e750d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/75e750dd122e1bba6c838c32a6d85a304f3d2f56))

[Release v0.91.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.91.5)

## [0.91.4] - 2026-09-27

### Fixes

- fix(showcase): redesign shipping-crate with stencilled cargo marks and a three-quarter hero ([`0739862`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/073986290c3e289c0b33e0cc43eb4f54ca06ca27))
- fix(showcase): redesign hitching-post with a face-nailed horseshoe ([`73499d6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/73499d63a0dd652022d73c4da04751d35a96cf22))
- fix(showcase): redesign signpost as a lettered three-finger crossroads post ([`2d9f5c5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2d9f5c5b97cea2f1b8cefd1fc9528c7e55db3cd4))
- fix(showcase): dress terrain-scatter with grass cover, tufts and pebbles ([`71b4f2b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/71b4f2bbf09e8b4837e2beef1921b86920937b19))
- fix(showcase): restage wooden-ladder on a board wall with a hung rope coil ([`e81385b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e81385b646508670e988b548ace9d45470d1ca10))
- fix(showcase): redesign fence-kit hero as a weathered three-section run ([`c34861b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c34861b14da83ef62a36e875285f4d195f95276e))
- fix(examples): redesign bake-normal-high-to-low as a map, source and LOD triptych ([`c95e0ce`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c95e0ced95cde8862f747acf8449c68e7afb2db9))
- fix(examples): redesign lightmap-uv-channel as a spoked, shafted cart beside a framed atlas display ([`2efe86b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2efe86b57f174abb8b0120c7d2522e0e3f8e3e97))
- fix(examples): redesign vertex-color-ao as a dressed-stone well with V-groove joints ([`8cf6499`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8cf649989d92a4bfa91651f4049e22e7cb755bcc))
- fix(examples): redesign soccer-ball-goldberg as a match ball on pitch turf ([`3cca51b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3cca51b43645b58c6ce14eb604eafee5a63c5e68))
- fix(examples): redesign bmesh-gear as a brass gear in a bolted gear train ([`de92629`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/de92629d154a89e1a67255157c5ce635827ac1e5))
- fix(examples): redesign grease-pencil-rosette as a neon sign on a lacquer board ([`27af6a3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/27af6a3e67abee595e1a67f4b00718eaa47b21db))
- fix(examples): redesign gn-sdf-remesh as a kitbashed vase fused by the SDF tree ([`0cd13c5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0cd13c57d4b9eedb1a50624a8e04b9fd462d402c))

### Other

- docs(gallery): regenerate pages for the shipping-crate redesign ([`3f5c956`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3f5c9568fd8b9ab9daf7012235d95cd16ab6eb42))
- docs(gallery): regenerate pages and contact sheets for round-two redesigns ([`a5fed1d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a5fed1d8ecc87ac30e822fe80122084f4b3b42b6))

[Release v0.91.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.91.4)

## [0.91.3] - 2026-09-27

### Fixes

- fix(examples): text-version-stamp falls back to DejaVuSansMono on 4.x ([`b9ccd9c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b9ccd9c1f5ccf4b023a7cf4c50fd69d13da242fc))
- fix(examples): redesign gn-socket-rename as a height gauge on a granite surface plate ([`b7068f4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b7068f49513c31559e9a9e20effdd8f5d9d9712e))
- fix(examples): redesign gn-zone-iterate as graded blocks on a plinth and a spindle ([`c03b0e5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c03b0e513da9673af93bd9c21f89ad4f8712352a))
- fix(examples): redesign color-attribute-wheel as a domed ceramic plate on a walnut easel ([`9530d78`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9530d78f8469d82a63c108d8a83c3d6455110e02))
- fix(examples): redesign cross-version-property-delete as two stage lamps lit by their ID property ([`3408e46`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3408e46715e663c1da78fb3018a78660f8ce6e57))
- fix(examples): redesign usd-export-evaluation-mode as re-imported brass goblets ([`a31a2b1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a31a2b1afa1de2e3a1adf4511c6a3adeaad3cdd8))
- fix(examples): redesign wave-displace as a cast bronze tile in a walnut frame ([`d9e6511`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d9e651119f0dd23cb96d0417234d000542b6393f))
- fix(examples): redesign driver-wave as a brass pipe-organ facade ([`cda2e0d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/cda2e0d7e7c865a3c41d8e69ff1875f342d4140f))
- fix(examples): redesign degenerate-bevel-weld hardware and tone down the collapse seam ([`d2d442d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d2d442d4118a83f784af1190ffc1042cad9bc3df))
- fix(examples): redesign custom-normals-shade edge overlay as amber drafting lines ([`3b63a5b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3b63a5b95bb03ea16305bedcf088f6ed871e08c1))

### Other

- docs(gallery): regenerate pages and contact sheets for the final redesign batch ([`d262c2a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d262c2a45cda79e729785cd06bb0d2ab86dd126c))

[Release v0.91.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.91.3)

## [0.91.2] - 2026-09-27

### Fixes

- fix(examples): redesign text-version-stamp as gold Inter numerals on a stone plinth ([`2e6948f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2e6948f9bfbc83b9f8d44120489f1241dd5c4061))
- fix(examples): redesign vse-cut-list as a program monitor over a timeline console ([`5798259`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5798259c3c57d08d7344948bbe3262c46130efd6))
- fix(examples): redesign car-mirror-symmetry as a smooth creased body with alloy wheels ([`8b83b01`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8b83b013db528fbd6f67319a2421c258ba48f69a))
- fix(examples): redesign png-exr-alpha as thin-bezel monitors on a walnut console ([`f0500ce`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f0500ceee983a7a9b4c02883d54faefaad7e8ee8))
- fix(examples): redesign uv-layer-grid as framed tile panels on studio easels ([`4a4d25c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4a4d25c838b9e41ede702f86dfbcc9d481d98df9))

### Other

- docs(gallery): regenerate pages and contact sheets for the second redesign batch ([`c4bf76d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c4bf76d266417034aceb7740e89ed70c9cc5feee))

[Release v0.91.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.91.2)

## [0.91.1] - 2026-09-27

### Fixes

- fix(examples): redesign socket-attach-points as a cobalt survey drone with carbon-weave arms ([`8a69765`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8a697657c01e90e20caa757d9ade269acd0e10dc))
- fix(examples): redesign damped-track-aim as a ring of spotlights aimed at a glowing orb ([`663fa03`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/663fa03835a51fbed7c0337e0a8ccb3956887fdc))
- fix(examples): redesign modular-kit-snap surfaces as painted, tread-plated, hazard-striped kit ([`9123f54`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9123f5448cf64e18d0ffdba8c3dcb61e1dac9599))
- fix(examples): redesign armature-bend as ribbed bellows hoses on steel flanges ([`2228491`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2228491166d9f51ca947f3ef3837b356f9b28176))

### Other

- docs(gallery): regenerate pages and contact sheets for the redesigned heroes ([`f00d2aa`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f00d2aa0d2880aac8ab308194b3488d9333238b5))
- docs(claude): record the shared palette and the site link gate ([`cbe8b90`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/cbe8b90b00a7c5f93aebfaf29aecd5f85a5305f1))
- ci(labels): list PR files via the files API, not the full diff ([`6f3f0ab`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6f3f0ab7b4783ab06a8aace86f3c4b4f68160cf1))

[Release v0.91.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.91.1)

## [0.91.0] - 2026-09-27

### Features

- feat(site): landing links, what's new, shared tokens, CI guardrails (#302) ([`70ca92f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/70ca92fc06cc7717f62459369651f1c73cf06b27))

[Release v0.91.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.91.0)

## [0.90.0] - 2026-09-27

### Features

- feat(gallery): browse controls and interaction feel (#303) ([`600e129`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/600e12934f63d75c4e8c02dc75a8c4e2aa8b8442))

[Release v0.90.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.90.0)

## [0.89.0] - 2026-09-27

### Features

- feat(gallery): detail-page navigation, code ergonomics, image polish (#300) ([`06187b9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/06187b917710db6ccafe2c473f626d99054c344d))

[Release v0.89.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.89.0)

## [0.88.0] - 2026-09-27

### Features

- feat(examples): add gn-sim-fountain (#299) ([`e7e10fb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e7e10fbb0bac1bd90ce80b8b3dd8211bc1a0fd99))

### Other

- docs(roadmap): restock the candidate pool with 41 subjects, 16 flagship (#285) ([`54e7f71`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/54e7f71481de56f108467c3abc6f0e82a2ec4dd4))

[Release v0.88.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.88.0)

## [0.87.0] - 2026-09-26

### Features

- feat(showcase): add book-trolley (#284) ([`4c30ab5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4c30ab5d424dc146fbcfa0d351c93d1f558db04f))

[Release v0.87.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.87.0)

## [0.86.0] - 2026-09-26

### Features

- feat(showcase): add bookshelf (#283) ([`6e52a0f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6e52a0f85905af2d1694d7ca50234768c086795b))

### Other

- docs(style): note that the former-reference rows predate their redesigns (#282) ([`be5916b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/be5916ba083aa751704d38fee01b5e3c10523590))

[Release v0.86.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.86.0)

## [0.85.24] - 2026-09-26

### Fixes

- fix(examples): redesign temp-override-join as a hurricane lantern joined from seven parts (#281) ([`81df35b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/81df35b06a80a5c6dd9a56581bea310237322da1))

[Release v0.85.24](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.24)

## [0.85.23] - 2026-09-26

### Fixes

- fix(examples): redesign depsgraph-export as a controller cage beside its subdivided shell (#280) ([`d570163`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d570163c29fce89b52cb55e61a62b892065624f0))

[Release v0.85.23](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.23)

## [0.85.22] - 2026-09-26

### Fixes

- fix(examples): redesign gn-instance-grid as a 3x3 macropad key field (#278) ([`3870094`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3870094dddd89f53a722b13e9a695d9f60f4248d))

[Release v0.85.22](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.22)

## [0.85.21] - 2026-09-26

### Fixes

- fix(examples): redesign gp-lineart-contour as an inked lighthouse diorama (#279) ([`e0298c4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e0298c4741cbffbfe50c524cd4759265378fc1a9))

[Release v0.85.21](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.21)

## [0.85.20] - 2026-09-26

### Fixes

- fix(examples): redesign curve-bevel-arc as a horseshoe magnet with field-line filings (#277) ([`d93ee17`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d93ee17c63dc3d1ca1b988d70eea559160796853))

[Release v0.85.20](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.20)

## [0.85.19] - 2026-09-26

### Fixes

- fix(examples): redesign shader-node-group as five dipped-glaze stoneware mugs (#276) ([`bd0671c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bd0671c62ce6c73532cb65f6a285ba4c4703d536))

[Release v0.85.19](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.19)

## [0.85.18] - 2026-09-26

### Fixes

- fix(examples): redesign gn-modifier-inputs as three GN spiral staircases (#274) ([`dbd327e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/dbd327edeb3764eb5df8bd2b728d99922d5be222))

[Release v0.85.18](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.18)

## [0.85.17] - 2026-09-26

### Fixes

- fix(examples): redesign shape-key-blend as a ceramic vase morphing jar to trumpet (#275) ([`dda157b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/dda157b4e6eb1fbf3aa42427e7d6d6ebfd289e47))

[Release v0.85.17](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.17)

## [0.85.16] - 2026-09-26

### Fixes

- fix(examples): redesign gltf-export-roundtrip as one crate under its re-imported wire cage (#273) ([`c4f7d7d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c4f7d7d760f9c296bc732bb15c8c85153bd38758))

[Release v0.85.16](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.16)

## [0.85.15] - 2026-09-26

### Fixes

- fix(examples): redesign degenerate-bevel-weld as rugged cases with a traced collapse seam (#270) ([`a0b4a70`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a0b4a70c1abbb9576359aa3fa89e7359fd3b198b))

[Release v0.85.15](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.15)

## [0.85.14] - 2026-09-26

### Fixes

- fix(examples): redesign attribute-domain-shear as striped patio parasols (#272) ([`2f6b4c6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2f6b4c6ab36154a4d76eebdbd2c34c59d62770b4))

[Release v0.85.14](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.14)

## [0.85.13] - 2026-09-26

### Fixes

- fix(examples): redesign custom-normals-shade jerry can and make the three shadings read (#271) ([`07794ae`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/07794ae0f7575f09631297ccea455c6c2bd456fb))

[Release v0.85.13](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.13)

## [0.85.12] - 2026-09-26

### Fixes

- fix(examples): redesign mesh-hygiene-audit as a flanged street valve with marked defects (#269) ([`08e1acc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/08e1acc6df71c4508c1291c4016a70bc092bbbda))

[Release v0.85.12](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.12)

## [0.85.11] - 2026-09-26

### Fixes

- fix(examples): redesign vse-gamma-cross as sequencer filmstrips on a grading monitor (#268) ([`a286d13`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a286d139311121bf47acf344f2f77898ddb2a79b))

[Release v0.85.11](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.11)

## [0.85.10] - 2026-09-26

### Fixes

- fix(examples): redesign prop-origin-transform as a street utility pedestal with a thrown conduit elbow (#267) ([`2873914`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/28739140da03ec0108c0b2ea1853046714b8d2d0))

[Release v0.85.10](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.10)

## [0.85.9] - 2026-09-26

### Fixes

- fix(examples): redesign lod-decimate-chain rocket and show LOD density (#266) ([`0989aca`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0989acacbe5095c4dfcc61f478151f8cdb8e8097))

[Release v0.85.9](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.9)

## [0.85.8] - 2026-09-26

### Fixes

- fix(examples): redesign gltf-skin-roundtrip as a mech scorpion standoff (#265) ([`e173e9d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e173e9d41510c5e50a8551548d21652b4818c1c1))

[Release v0.85.8](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.8)

## [0.85.7] - 2026-09-26

### Fixes

- fix(examples): rebuild triangulate-tangents buckler as a machined shield (#261) ([`2f4f4e0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2f4f4e0f192e74cf468324c94d82965360e698a3))

[Release v0.85.7](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.7)

## [0.85.6] - 2026-09-26

### Fixes

- fix(examples): redesign car-mirror-symmetry as a smooth-shaded stylized hatchback (#260) ([`784cda1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/784cda1b6944f83402ead3a2568cdbdf52ab8ce8))

[Release v0.85.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.6)

## [0.85.5] - 2026-09-26

### Fixes

- fix(examples): redesign vertex-weight-limit as a painted industrial arm (#264) ([`3433333`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3433333cbd812d4ead3f3cb7c1f0395d65539a96))

[Release v0.85.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.5)

## [0.85.4] - 2026-09-26

### Fixes

- fix(examples): redesign sky-texture-sun-elevation hero as a sky-lit obelisk diptych (#263) ([`9dc334c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9dc334c5d5925c5f67ff919522b2b4b1e8f5c53d))

[Release v0.85.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.4)

## [0.85.3] - 2026-09-26

### Fixes

- fix(examples): redesign export-preset-axis as a banded radio mast with measured axis gizmos (#262) ([`25108f6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/25108f6e6177241647a98ff8c6a43697d90d5516))

[Release v0.85.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.3)

## [0.85.2] - 2026-09-26

### Fixes

- fix(examples): restage swatch-grid as a tiered material library with a glowing emissive (#259) ([`7c5c01e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7c5c01e161ea546079ebe52f98b86d445f6cb1d9))

[Release v0.85.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.2)

## [0.85.1] - 2026-09-25

### Fixes

- fix(examples): bmesh-gear turned-brass finish replaces moire banding (#258) ([`d89ed5a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d89ed5a46d86feb6d44475f1da06d79513e03031))

### Other

- chore(gates): raise the asset-sheet reference bar and commit its renderer (#257) ([`6f57e76`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6f57e76751ef877bb79969df6f0c13e92320f173))

[Release v0.85.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.1)

## [0.85.0] - 2026-09-25

### Features

- feat(showcase): add butter-churn (#256) ([`a15d36a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a15d36a32e7583dfbf6b8ed9f403a615c331ea9b))

[Release v0.85.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.85.0)

## [0.84.0] - 2026-09-25

### Features

- feat(showcase): add wooden-yoke (#255) ([`ef98ce6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ef98ce6ce2b33ce0f639be190cc7f22546e49e92))

[Release v0.84.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.84.0)

## [0.83.0] - 2026-09-25

### Features

- feat(showcase): add apothecary-shelf (#254) ([`d8765fb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d8765fb462f5594f4750fa0c73c650ebdc6c9b72))

[Release v0.83.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.83.0)

## [0.82.0] - 2026-09-25

### Features

- feat(showcase): add brazier (#253) ([`35aa8fb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/35aa8fbe174805951be601652e633a9e3d4455c9))

[Release v0.82.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.82.0)

## [0.81.0] - 2026-09-25

### Features

- feat(showcase): add grain-sacks (#252) ([`0c08b89`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0c08b891e7bf3ce4db9c2495bf411cb15c4f7327))

[Release v0.81.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.81.0)

## [0.80.0] - 2026-09-25

### Features

- feat(showcase): add rope-bridge (#251) ([`e256a9a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e256a9abcc7638cf9e807f0f5daa54611fa7e8a4))

[Release v0.80.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.80.0)

## [0.79.37] - 2026-09-25

### Fixes

- fix: water-trough third quality pass; exit-pre-sidecar finding (#250) ([`c78462f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c78462f5e186c38d7cf3a37b98264b50f2e94b18))

[Release v0.79.37](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.37)

## [0.79.36] - 2026-09-25

### Fixes

- fix: wheelbarrow and gltf-skin-roundtrip quality pass (#249) ([`5683805`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5683805fb9f09864a0d8fa84b041cc0744bb26fb))

[Release v0.79.36](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.36)

## [0.79.35] - 2026-09-25

### Fixes

- fix: terrain-scatter and car-mirror-symmetry quality pass (#248) ([`418b641`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/418b641c23202e8d5e87a14404c815d2521ced71))

[Release v0.79.35](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.35)

## [0.79.34] - 2026-09-25

### Fixes

- fix(examples): re-review of the 20 judged-fine examples; seat the gear, buckler and crystal (#247) ([`38e6f1d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/38e6f1d4db4e0c9a39400cf8b73b36c1f6232048))

[Release v0.79.34](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.34)

## [0.79.33] - 2026-09-25

### Fixes

- fix: hay-bale second quality pass (#246) ([`c27713d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c27713d2332aad719f7fdb6510fbc12b81759898))

[Release v0.79.33](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.33)

## [0.79.32] - 2026-09-25

### Fixes

- fix(examples): seat the vse-cut-list monitor and stand its caption up (#245) ([`0c818a9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0c818a93edcb1e1db3a4466bd3ef933c3845a47a))

[Release v0.79.32](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.32)

## [0.79.31] - 2026-09-24

### Fixes

- fix: bake-normal-high-to-low and lightmap-uv-channel quality pass (#244) ([`87dad44`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/87dad446b370f6f81a6504af9c92d70d422b7672))

[Release v0.79.31](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.31)

## [0.79.30] - 2026-09-24

### Fixes

- fix: turntable and swatch-grid quality pass (#243) ([`52eaabb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/52eaabb33fbdc65b1f0985eb47b40f385c709b17))

[Release v0.79.30](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.30)

## [0.79.29] - 2026-09-24

### Fixes

- fix: cart, grindstone and attribute-domain-shear quality pass (#242) ([`d1caf5b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d1caf5b95e10aa8c3466eac19ec549614dafaa02))

[Release v0.79.29](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.29)

## [0.79.28] - 2026-09-24

### Fixes

- fix: wall-torch, tavern-stool and vertex-color-ao quality pass (#241) ([`eca1d96`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/eca1d962f47db4759de721bb0ce8782b42494b26))

[Release v0.79.28](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.28)

## [0.79.27] - 2026-09-24

### Fixes

- fix: park-bench, fence-kit and soccer-ball-goldberg quality pass (#240) ([`a8f121d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a8f121dba6400a5bf78cb3432de5e81a64dd67ef))

[Release v0.79.27](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.27)

## [0.79.26] - 2026-09-24

### Fixes

- fix: street-lantern, watchtower, parent-inverse-orrery and ngon-triangulate quality pass (#239) ([`99ca76d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/99ca76db2a9656f408375508869ecd35714f63ed))

[Release v0.79.26](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.26)

## [0.79.25] - 2026-09-24

### Fixes

- fix: market-stall, stone-well, gltf-export-roundtrip and prop-origin-transform quality pass (#238) ([`76a0230`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/76a0230eb13636a6bb235baa17a906a27ebc05be))

[Release v0.79.25](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.25)

## [0.79.24] - 2026-09-23

### Fixes

- fix: anvil, signpost, text-version-stamp and cross-version-property-delete quality pass (#237) ([`8799122`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/879912218b327538f41c6af294b068d2f6790bd5))

[Release v0.79.24](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.24)

## [0.79.23] - 2026-09-23

### Fixes

- fix: hitching-post, hand-pump, shader-node-group and driver-wave quality pass (#236) ([`819420e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/819420eca8501d1d7b383cff697d6cd4cd02523a))

[Release v0.79.23](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.23)

## [0.79.22] - 2026-09-23

### Fixes

- fix: wooden-ladder, wheelbarrow, curve-bevel-arc and sky-texture-sun-elevation quality pass (#235) ([`39ef779`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/39ef779de916124351ab0848a2f1deef9871b21a))

[Release v0.79.22](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.22)

## [0.79.21] - 2026-09-23

### Fixes

- fix: iron-cauldron, campfire, usd-export-evaluation-mode and gn-modifier-inputs quality pass (#234) ([`f91f50a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f91f50a5ab8a7705f54314a341d14294a59acd83))

[Release v0.79.21](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.21)

## [0.79.20] - 2026-09-23

### Fixes

- fix: wooden-barrel, wooden-bucket, wave-displace and color-attribute-wheel quality pass (#233) ([`1cd36af`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1cd36aff13a3483efbaf9c53ac65bbc022b27ec8))

[Release v0.79.20](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.20)

## [0.79.19] - 2026-09-23

### Fixes

- fix: hay-bale, treasure-chest, gn-instance-grid and temp-override-join quality pass (#232) ([`937ba1a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/937ba1ad05e33ab3899341801d8a7bef69be184e))

[Release v0.79.19](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.19)

## [0.79.18] - 2026-09-23

### Fixes

- fix: shipping-crate, shape-key-blend and vse-linear-modifiers quality pass (#231) ([`44ca4bb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/44ca4bb7c39da708f10805d5b794c52fb199e8da))

[Release v0.79.18](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.18)

## [0.79.17] - 2026-09-23

### Fixes

- fix: terrain-scatter, export-preset-axis and mesh-automasking-settings quality pass (#230) ([`223b1ee`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/223b1eee35678ef31af559416afe30395598753f))

[Release v0.79.17](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.17)

## [0.79.16] - 2026-09-23

### Fixes

- fix: water-trough, gn-sdf-remesh and eval-mesh-datablock-name quality pass (#229) ([`4e73484`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4e7348456eed41c378d56b855fab438bc70f11be))

[Release v0.79.16](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.16)

## [0.79.15] - 2026-09-23

### Fixes

- fix: stone-archway, gn-zone-iterate and coincident-vert-weld quality pass (#228) ([`9283488`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/92834881aa6adfccd39bc2c48ba6b3156e56e68b))

[Release v0.79.15](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.15)

## [0.79.14] - 2026-09-23

### Fixes

- fix: crate-stack, depsgraph-export and unapplied-scale-gltf quality pass (#227) ([`c05c6c5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c05c6c5e78c8ec0671f0d613b6417e418a6adfe3))

[Release v0.79.14](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.14)

## [0.79.13] - 2026-09-23

### Fixes

- fix(gallery): regenerate the 25 drifted heroes from their code, with contact sheets (#225) ([`c010da5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c010da529162004e79e33558aea44adcfed27b7d))
- fix(examples): resolve --output against the working directory in three render paths (#223) ([`2321b2a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2321b2a7114279e5de60a89a34fe8dbc66d4eec9))

[Release v0.79.13](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.13)

## [0.79.12] - 2026-09-23

### Fixes

- fix(gallery): describe each still in its alt text instead of the API it teaches (#221) ([`8b3ed95`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8b3ed95a38dcecc910d50af05d5d802e1d7c4e75))

[Release v0.79.12](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.12)

## [0.79.11] - 2026-09-23

### Fixes

- fix(site): subset the web fonts and give link previews a proper card (#220) ([`b2177e1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b2177e1fce7314ec98280f3777e35d431ec22502))

[Release v0.79.11](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.11)

## [0.79.10] - 2026-09-23

### Fixes

- fix(ci): deploy Pages once per release instead of twice (#219) ([`427dc0b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/427dc0bad47b0c7aa0e4aebacb70819120b6d017))

[Release v0.79.10](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.10)

## [0.79.9] - 2026-09-23

### Fixes

- fix(showcase): bring 19 previews to the 1200x675 spec and enforce hero/preview sizes (#217) ([`208e5e3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/208e5e3fe8635fe87b9869b0b8b939973a49528c))

### Other

- chore(scripts): add measure_hero_drift.py for issue #200 (#218) ([`29edf01`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/29edf0180f7ef6cf59ffc6edce8988b678985417))

[Release v0.79.9](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.9)

## [0.79.8] - 2026-09-23

### Fixes

- fix(gallery): gate committed gallery drift in CI and prune stale pages (#211) ([`7e07b17`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7e07b1799c9b08cc9042ce75b3c56b42e5b45287))

[Release v0.79.8](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.8)

## [0.79.7] - 2026-09-23

### Fixes

- fix(tests): stop exempting cart, hay-bale and stone-well from the falsifier-table check (#210) ([`5453dbb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5453dbbdc1798626d95224722b2ac5b3dadafc23))

[Release v0.79.7](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.7)

## [0.79.6] - 2026-09-23

### Fixes

- fix(site): finish the Pages review follow-ups (#209) ([`abc83c7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/abc83c7cc8619637b52a3c0fae6d3ea32c71ae87))

[Release v0.79.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.6)

## [0.79.5] - 2026-09-22

### Fixes

- fix(site): correct landing-page claims and render README tables on gallery pages (#208) ([`613be85`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/613be85a4f8d5347eee1a14a044b0c82526f4f7c))

[Release v0.79.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.5)

## [0.79.4] - 2026-09-22

### Fixes

- fix: chopping-block, gn-socket-rename and gn-bundle-roundtrip quality pass (#207) ([`4d7468f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4d7468f964cb8faf87eae9b5d69fc2d74af962c8))

[Release v0.79.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.4)

## [0.79.3] - 2026-09-22

### Fixes

- fix(showcase): rebuild cart and stone-well joints, with eight new hygiene budgets (#206) ([`480a159`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/480a159401fe643c8c2c938fa06142ccecc28537))

[Release v0.79.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.3)

## [0.79.2] - 2026-09-22

### Fixes

- fix(showcase): hay-bale quality pass with five new hygiene budgets, and exit-pre-sidecar doc accuracy (#205) ([`56b7825`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/56b7825c07c0d93311dc5aa2bb6270f5cca8c991))

[Release v0.79.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.2)

## [0.79.1] - 2026-09-22

### Fixes

- fix: correct the inverted EEVEE engine id and close the coverage gap that hid it (#204) ([`c4cd7b4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c4cd7b4db63d85975abb86e551153adbf1118f00))

[Release v0.79.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.1)

## [0.79.0] - 2026-09-22

### Features

- feat: add crate-stack and stone-archway showcase pieces (#199) ([`0cc8197`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0cc8197cad8c76cb7078c5c22559fb7d2608f1bb))

[Release v0.79.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.79.0)

## [0.78.21] - 2026-09-22

### Fixes

- fix: sign off release bumps and drop the dead Pages path filter (#198) ([`d3fba79`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d3fba79890d2a1b1c5f8c38189f8c284365dffe0))

[Release v0.78.21](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.21)

## [0.78.20] - 2026-09-22

### Fixes

- fix: make rule scoping match the documented scope (#197) ([`ebe5c4e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ebe5c4ec70262eaec0c5ef73603e5ebe9f1f64a9))

[Release v0.78.20](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.20)

## [0.78.19] - 2026-09-22

### Fixes

- fix: close the mechanical audit issues (#196) ([`4d23e70`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4d23e706cb11807aca75c3edeb0d8ac3f01829d5))

### Other

- docs: document the main branch protection model (#194) ([`6440e83`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6440e836b22c70527f83422133590ad9d65bb97f))

[Release v0.78.19](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.19)

## [0.78.18] - 2026-09-22

### Fixes

- fix: dispatch Pages after a release tag ([`02c6580`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/02c6580a63eb9c4ffdba91a0f97f413c8c1afed9))

[Release v0.78.18](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.18)

## [0.78.17] - 2026-09-21

### Fixes

- fix: correct drifted inventory counts and contributor docs ([`9bf4f1a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9bf4f1acf1188e333db16d5bdeab443a514ad5f5))

[Release v0.78.17](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.17)

## [0.78.16] - 2026-09-21

### Fixes

- fix(showcase): wooden ladder and hitching post visual quality pass (#185) ([`e921ce4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e921ce44e2c9b17d18279f9422dbba55cbcffed6))

[Release v0.78.16](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.16)

## [0.78.15] - 2026-09-21

### Fixes

- fix(showcase): wall-torch and signpost visual quality pass (#184) ([`6094505`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/60945051ae41c7aacbd54857ea21120e4f022ddb))

[Release v0.78.15](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.15)

## [0.78.14] - 2026-09-19

### Fixes

- fix(showcase): fence-kit and hand-pump visual quality pass (#183) ([`09453f5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/09453f50d4843c3f9ffd9c2a6699599c9c18ae35))

[Release v0.78.14](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.14)

## [0.78.13] - 2026-09-18

### Fixes

- fix(showcase): terrain-scatter and park-bench visual quality pass (#182) ([`8461626`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/84616261684b031ce4d3dc4768a33e84221c44a1))

[Release v0.78.13](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.13)

## [0.78.12] - 2026-09-18

### Fixes

- fix(showcase): street-lantern and water-trough visual quality pass (#181) ([`a09254c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a09254cca2bc83cd0bef25544d7172c6b6e09aa5))

[Release v0.78.12](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.12)

## [0.78.11] - 2026-09-17

### Fixes

- fix(showcase): market-stall and watchtower visual quality pass (#179) ([`1c9c022`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1c9c0220150593d5f921f8d72e285ed79e7d6b60))

[Release v0.78.11](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.11)

## [0.78.10] - 2026-09-17

### Fixes

- fix(showcase): anvil and campfire visual quality pass (#178) ([`33bb510`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/33bb510de7202cc1cc3f68860689025b75bdc2d2))

[Release v0.78.10](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.10)

## [0.78.9] - 2026-09-16

### Fixes

- fix(showcase): wooden-barrel and wooden-bucket visual quality pass (#177) ([`bd9808b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bd9808b63c4d925071bfef23fc1c432efb02880f))

[Release v0.78.9](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.9)

## [0.78.8] - 2026-09-16

### Fixes

- fix(showcase): iron-cauldron and shipping-crate visual quality pass (#176) ([`7a732f3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7a732f351ae95cf9723c40537818143bf27c0a4b))

[Release v0.78.8](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.8)

## [0.78.7] - 2026-09-16

### Fixes

- fix(showcase): treasure-chest and tavern-stool visual quality pass (#175) ([`9bdaf01`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9bdaf01c0c4f815531af77a189f9945f9ab7c1fe))

[Release v0.78.7](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.7)

## [0.78.6] - 2026-09-16

### Fixes

- fix(showcase): grindstone and wheelbarrow visual quality pass (#174) ([`0fffd74`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0fffd7457cca08dcbe9fa529e4b796e2c547dd47))

[Release v0.78.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.6)

## [0.78.5] - 2026-09-16

### Fixes

- fix(showcase): rebuild chopping-block as a log round with a felling axe (#173) ([`bb29acc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bb29acc08e0a95e239b373bc334bba6f803dd312))

[Release v0.78.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.5)

## [0.78.4] - 2026-09-16

### Fixes

- fix: seat the ladder rungs and stop the iron chamfers reading as wood (#172) ([`dec2f21`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/dec2f21bbd17c9b411800c3dddff45003d7e793f))

[Release v0.78.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.4)

## [0.78.3] - 2026-09-16

### Fixes

- fix: showcase quality pass â€” stone-well and cart (#171) ([`bc0ac6c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bc0ac6cf43a654453f15a47b98fdea5f7147909f))

[Release v0.78.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.3)

## [0.78.2] - 2026-09-16

### Fixes

- fix: rebuild hay-bale and hitching-post so the joints actually meet (#170) ([`a3aac9d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a3aac9dc59d3d4b8e139f2a5ee793d7ae9dabfb3))

[Release v0.78.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.2)

## [0.78.1] - 2026-09-15

### Fixes

- fix: hang the iron cauldron inside the tripod (#169) ([`170f3ae`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/170f3ae41da21985515c8c69913aeae1f1d2e7dd))

[Release v0.78.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.1)

## [0.78.0] - 2026-09-15

### Features

- feat: add wooden-ladder and hay-bale showcase pieces (#168) ([`a7ae15f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a7ae15f4f80510f4f58370fe7357f8bdb5751b29))

[Release v0.78.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.78.0)

## [0.77.1] - 2026-09-15

### Fixes

- fix: rebuild four weak showcase props and collapse the README grid (#167) ([`5cc7b8d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5cc7b8d5cd554baf0ec38c6e00ce8a2029d88b01))

[Release v0.77.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.77.1)

## [0.77.0] - 2026-09-15

### Features

- feat: add tavern-stool and iron-cauldron showcase pieces ([`af82b73`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/af82b736361871296304db4e9b3b515364dd1e50))

[Release v0.77.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.77.0)

## [0.76.0] - 2026-09-15

### Features

- feat: add wooden-bucket and wall-torch showcase pieces ([`c89c132`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c89c132476b33f44dcb88bac6cacb92112535b56))

[Release v0.76.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.76.0)

## [0.75.1] - 2026-09-15

### Fixes

- fix: seal the water trough and drop bellows ([`3843c23`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3843c23aab5c4466ee372d34992bedda0a9a22f2))

[Release v0.75.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.75.1)

## [0.75.0] - 2026-09-15

### Features

- feat: add bellows and chopping-block showcase pieces (#163) ([`55228f7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/55228f72b0f5241cf3221c15cf2468faba86457c))

[Release v0.75.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.75.0)

## [0.74.1] - 2026-09-14

### Fixes

- fix: rebuild trough, anvil, hand-pump, and signpost (#162) ([`f90a3cf`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f90a3cfad5b1108485e7b0bf6079dc7cf008f734))

[Release v0.74.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.74.1)

## [0.74.0] - 2026-09-14

### Features

- feat: add hand-pump and signpost showcase pieces (#161) ([`e66ec7d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e66ec7d72b18dd800dc561b08e21dd255fb0b1d6))

[Release v0.74.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.74.0)

## [0.73.0] - 2026-09-14

### Features

- feat: add hitching-post and grindstone showcase pieces (#160) ([`bcf2656`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bcf265686b8304582ccbc20f30ac2ff3324e33ff))

[Release v0.73.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.73.0)

## [0.72.0] - 2026-09-14

### Features

- feat: add anvil and water-trough showcase pieces (#159) ([`517f76f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/517f76fab0cdc8e8b236fc80cf69581d7e8973c1))

[Release v0.72.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.72.0)

## [0.71.0] - 2026-09-14

### Features

- feat: add park-bench and wheelbarrow showcase pieces (#158) ([`85ec060`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/85ec06022b40dd4ca78df93fd02be38fea5df2d2))

[Release v0.71.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.71.0)

## [0.70.1] - 2026-09-14

### Fixes

- fix: rebuild watchtower as a timber lookout with a shake roof (#157) ([`4941357`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/49413572cacf90653987dd193a3c5b05fac6a2fd))

[Release v0.70.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.70.1)

## [0.70.0] - 2026-09-13

### Features

- feat: add watchtower and cart showcase pieces (#156) ([`8905035`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8905035b997327b8dab92939dacfe70be4df8046))

[Release v0.70.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.70.0)

## [0.69.0] - 2026-09-13

### Features

- feat: add terrain-scatter and fence-kit showcase pieces (#155) ([`714fa9c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/714fa9c3e1ce4c8b56cd52e67691648dc13ca1e5))

[Release v0.69.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.69.0)

## [0.68.0] - 2026-09-13

### Features

- feat: add street-lantern and treasure-chest showcase pieces (#154) ([`caefc2f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/caefc2fc6b4fb124810cc4841c53cb6164a36da2))

[Release v0.68.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.68.0)

## [0.67.1] - 2026-09-13

### Fixes

- fix: restage campfire and stall showcase stills ([`be52857`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/be52857a304af4c392069890cad201f134c09d4f))

[Release v0.67.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.67.1)

## [0.67.0] - 2026-09-13

### Features

- feat: add campfire and market-stall showcase pieces (#152) ([`a5afb9c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a5afb9cafe11c5867629222e1cc3d39f76dfc30c))

[Release v0.67.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.67.0)

## [0.66.0] - 2026-09-13

### Features

- feat: add stone-well and wooden-barrel showcase pieces (#151) ([`44d7c40`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/44d7c400a8b54f2cf01b327b5bac44ed28f5b013))

### Other

- ci: document and gate product exit codes in README tables (#150) ([`d2780a8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d2780a866e3f0b7db9ed43721aa745ceaf360879))

[Release v0.66.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.66.0)

## [0.65.0] - 2026-09-13

### Features

- feat: enforce framing deviation at the call site (#149) ([`7d90367`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7d90367c6a91664f45defedd696d740051fd5a04))

[Release v0.65.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.65.0)

## [0.64.0] - 2026-09-13

### Features

- feat: add sibling showcase/ tree and shipping-crate piece (#148) ([`46dffec`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/46dffeca5c12df384e107fccc9937488009fd507))

[Release v0.64.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.64.0)

## [0.63.0] - 2026-09-13

### Features

- feat: add eval-mesh-datablock-name and mesh-automasking-settings examples (#147) ([`cb1f2bc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/cb1f2bc0c00c006e66c5681af08ea22a6f2ab74e))

[Release v0.63.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.63.0)

## [0.62.0] - 2026-09-13

### Features

- feat: add VSE linear-modifiers and GN socket-rename cross-version examples (#145) ([`f5649d9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f5649d9ceeaae520afbb08cb7d5f4f143cd1882a))

[Release v0.62.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.62.0)

## [0.61.0] - 2026-09-13

### Features

- feat: add CLI falsifiers and exit tables to the remaining twelve examples (#144) ([`c4714a7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c4714a7c587dde112db81a65e12bf49dbffb79fa))

[Release v0.61.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.61.0)

## [0.60.0] - 2026-09-13

### Features

- feat: add CLI falsifiers and exit tables to thirteen rigging examples (#143) ([`89ae4eb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/89ae4eb8da4b9393f3811482a4bf0cbbce1a84f9))

[Release v0.60.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.60.0)

## [0.59.0] - 2026-09-13

### Features

- feat: add CLI falsifiers and exit tables to ten mesh examples (#142) ([`fdaf467`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fdaf4674af760ecb9e82759ee2d8e225d36ffae7))

[Release v0.59.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.59.0)

## [0.58.0] - 2026-09-13

### Features

- feat: add CLI falsifiers and exit tables to six examples (#141) ([`fd3493d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fd3493ddea8e206145ae9031f3adb4ddf1515029))

[Release v0.58.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.58.0)

## [0.57.0] - 2026-09-12

### Features

- feat: add high-to-low tangent normal bake skill, snippets, and example (#140) ([`44cdf87`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/44cdf87494c51480730815a07f6ec5ca47939ae3))

### Other

- docs: write down exit-code roles and the smoke coverage model (#139) ([`20ab92d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/20ab92d0d2d2e221eac27beb3f43fe881c6f4c69))
- ci: opt-in Blender 5.1 smoke via needs-5.1 and dispatch (#137) ([`13ea521`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/13ea52182d168fd29130ed8cd020985bc8428c55))

[Release v0.57.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.57.0)

## [0.56.0] - 2026-09-12

### Features

- feat: AI asset pipeline track, Phase 3 (pipeline template) (#135) ([`b5d5893`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b5d58935c2d0d5eb136a48d2b132c8897d942c56))

[Release v0.56.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.56.0)

## [0.55.0] - 2026-09-12

### Features

- feat: AI asset pipeline track, Phase 2 (engine export presets) (#133) ([`41a82f2`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/41a82f2ce65f49e8861048b1004a8044af77318d))

[Release v0.55.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.55.0)

## [0.54.0] - 2026-09-11

### Features

- feat: AI asset pipeline track, Phase 1 (#132) ([`b293ccb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b293ccb968c0b4203e76edb32aeec29bebb91ef4))

[Release v0.54.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.54.0)

## [0.53.0] - 2026-09-10

### Features

- feat: witness n-gon, unapplied-scale, and coincident-vert pathologies ([`dd6b45e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/dd6b45ecb67c4843c090a9f064135502e3a55e82))

[Release v0.53.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.53.0)

## [0.52.0] - 2026-09-10

### Features

- feat: witness exit_pre via post-exit sidecar ([`bb5a2df`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/bb5a2df5309bf0c53c5803a749e310be92d9df01))

[Release v0.52.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.52.0)

## [0.51.0] - 2026-09-10

### Features

- feat: witness Geometry Nodes bundle round-trip ([`87d8b9a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/87d8b9a599e88bab1fd23580988bec7233336dcc))

[Release v0.51.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.51.0)

## [0.50.0] - 2026-09-09

### Features

- feat: witness Geometry Nodes zone pairing ([`0f3a1e9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0f3a1e9b3a3c106514d57928ab2ae7613caa2d90))

[Release v0.50.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.50.0)

## [0.49.0] - 2026-09-09

### Features

- feat: witness ID-property delete and USD evaluation_mode ([`764c90f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/764c90fff16743c5c5065d90f063e14fabf6a29c))

[Release v0.49.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.49.0)

## [0.48.0] - 2026-09-09

### Features

- feat: distinguish smoke skips from passes and assert post-exit sidecars ([`350e0a2`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/350e0a29b1e966cf6eccd4c6ebbd42f493bad517))

### Other

- chore: add gitattributes, CODEOWNERS, and GitHub templates ([`7d08804`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7d088049ff2f27b234e7ac250fdc00f90bedcfee))

[Release v0.48.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.48.0)

## [0.47.1] - 2026-09-09

### Fixes

- fix: teach the undocumented 5.2 COLOR strip size bake ([`1b810e1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1b810e12f804dc1c1ea4741caa3c04389c325d3b))

[Release v0.47.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.47.1)

## [0.47.0] - 2026-09-09

### Features

- feat: target Blender 5.2 LTS and witness NodesModifier input writes ([`e5b1642`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e5b1642306c1ca470a5a8428cdfa129ba4775ffb))

[Release v0.47.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.47.0)

## [0.46.1] - 2026-07-25

### Fixes

- fix: close checks that could pass without asserting anything, plus gallery-infrastructure debt (#120) ([`a827da0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a827da02763143cb4a34dca82c1b46ab05e440e9))

[Release v0.46.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.46.1)

## [0.46.0] - 2026-07-25

### Features

- feat: add vertex-color-ao example (baked occlusion in a colour attribute) (#119) ([`9ad353e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9ad353ead17967c882a09828d273dc11f65dd011))

[Release v0.46.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.46.0)

## [0.45.0] - 2026-07-24

### Features

- feat: add socket-attach-points example (spawn mount contract) (#118) ([`4bfe83b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4bfe83b7aff3cb007bf6326dc6762374651c22dd))

[Release v0.45.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.45.0)

## [0.44.0] - 2026-07-24

### Features

- feat: asset-quality gate + remodel modular-kit-snap and lightmap-uv-channel assets (#117) ([`cc1ccb8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/cc1ccb8b6303ef3958dbb4cbef75a7d7f52c291b))

[Release v0.44.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.44.0)

## [0.43.0] - 2026-07-24

### Features

- feat: add lightmap-uv-channel example (#116) ([`3390251`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/339025168156b5da150b6aeaf479e51434661346))

[Release v0.43.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.43.0)

## [0.42.0] - 2026-07-24

### Features

- feat: add modular-kit-snap example (#115) ([`916160d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/916160dc2a5cc8f8625091eec1a62cff6c05dc6d))

[Release v0.42.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.42.0)

## [0.41.0] - 2026-07-24

### Features

- feat: curate landing-page examples to a featured subset (#114) ([`ecaef2c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ecaef2c17aca9a6b1c852255bfd2cb899298c93e))

[Release v0.41.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.41.0)

## [0.40.0] - 2026-07-24

### Features

- feat: add search, density toggle, and sticky controls to gallery index (#113) ([`087bdf1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/087bdf1a7520c52747796b528b7d2697fe1f0c37))

[Release v0.40.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.40.0)

## [0.39.0] - 2026-07-23

### Features

- feat: add degenerate-bevel-weld example (#112) ([`3eb3eac`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3eb3eac726e4957854f645bdffa9cf01da42830b))

[Release v0.39.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.39.0)

## [0.38.0] - 2026-07-23

### Features

- feat: attribute-domain-shear example + count/numeric-contract housekeeping (#111) ([`9e9e7ce`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9e9e7cec83e9be7ef5e7b1219b5ab0b7247a9802))

[Release v0.38.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.38.0)

## [0.37.2] - 2026-07-23

### Fixes

- fix: recompose the four genuine framing defects (worklist drained) (#110) ([`a65cb38`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a65cb388159d6d0ab70ddda3bf8427fc0b663c06))

[Release v0.37.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.37.2)

## [0.37.1] - 2026-07-22

### Fixes

- fix: corrected framing survey + marginal camera-nudge sweep (7 examples) (#109) ([`7fd594e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7fd594eb9f4d519c3b38f817f9d087cf501c9320))

[Release v0.37.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.37.1)

## [0.37.0] - 2026-07-22

### Features

- feat: framing deviation clause + triage of the out-of-band thirteen (#108) ([`cf9ee1f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/cf9ee1ff705e4877fb81aef488afa90d6bb39620))

[Release v0.37.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.37.0)

## [0.36.0] - 2026-07-22

### Features

- feat: measurable framing gate + restage hygiene/origin heroes into the band (#107) ([`d6fa235`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d6fa235bec52c2564c319cea0a6af4a6f02932f5))

[Release v0.36.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.36.0)

## [0.35.1] - 2026-07-22

### Fixes

- fix: polish hygiene backlight and origin accessory heroes ([`285b935`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/285b935e1f411ecdaf27ff38fd023377d98af59d))

[Release v0.35.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.35.1)

## [0.35.0] - 2026-07-22

### Features

- feat: add car-mirror-symmetry example (#105) ([`9bbdd11`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9bbdd11c6fd8e0c130795bd52a88ed90c995c8af))

[Release v0.35.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.35.0)

## [0.34.0] - 2026-07-22

### Features

- feat: add soccer-ball-goldberg example (#104) ([`05d96d9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/05d96d9d510b9a89756d638cf1195b171a780739))

[Release v0.34.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.34.0)

## [0.33.1] - 2026-07-22

### Fixes

- fix: gallery render proof for hygiene + origin examples ([`449ad3d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/449ad3db1ee2253b7723caa2e57fd16567fe6544))

[Release v0.33.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.33.1)

## [0.33.0] - 2026-07-22

### Features

- feat: add prop-origin-transform example (#102) ([`c5c0043`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c5c0043d48f3290cbd087da1a4a0ee9574bae9b2))

[Release v0.33.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.33.0)

## [0.32.0] - 2026-07-22

### Features

- feat: add mesh-hygiene-audit example (#101) ([`16259fc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/16259fcf6fd91dc14cb685f482cb0db7beb65f75))

[Release v0.32.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.32.0)

## [0.31.0] - 2026-07-22

### Features

- feat: add gp-lineart-contour example (#100) ([`76262f3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/76262f3ed81fc2fc66d9a85eee844cf6e8cfec8e))

[Release v0.31.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.31.0)

## [0.30.0] - 2026-07-22

### Features

- feat: add sky-texture-sun-elevation example (#99) ([`1f6eba6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1f6eba624066c55fa2b3df75f8db5972aefbddcd))

### Other

- docs: update visual style guidelines for gallery renders ([`15dc4f7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/15dc4f7d41b9f15b3cd2512622ddcf944bbfbed8))

[Release v0.30.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.30.0)

## [0.29.1] - 2026-07-22

### Fixes

- fix: restage the game-prop pair heroes from deployed-page review (#98) ([`1a671b2`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1a671b26217dfd35aa2bd2f3a278c517f01433e8))

[Release v0.29.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.29.1)

## [0.29.0] - 2026-07-22

### Features

- feat: add custom-normals-shade example (post-4.1 shading contract) (#97) ([`0430939`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/04309393ab727bafde736316f21645d4f76153d1))

[Release v0.29.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.29.0)

## [0.28.0] - 2026-07-22

### Features

- feat: add collision-hull-proxy example (compound convex collision) (#96) ([`ed168a7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ed168a76ef2666482933d0b9327a6a4af623bfb9))

[Release v0.28.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.28.0)

## [0.27.4] - 2026-07-22

### Fixes

- fix: restage three earlier heroes as designed objects (#95) ([`9f30674`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9f30674c91550c7c8641bfff0862a57bf855e375))

[Release v0.27.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.27.4)

## [0.27.3] - 2026-07-22

### Fixes

- fix: stage the two newest heroes as designed objects (#94) ([`7e2e1ac`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7e2e1ac999ecd50e3c75004f8f2df5572fa1da65))

[Release v0.27.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.27.3)

## [0.27.2] - 2026-07-22

### Fixes

- fix: re-stage the two newest heroes to the calibration-set bar (#93) ([`b38677a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b38677a5b9897825411340862359e716cd9f2ac2))

### Other

- chore(deps): bump actions/setup-python from 6 to 7 (#89) ([`198ab43`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/198ab439d914f5c993745a3c43eb51a8854aa233))

[Release v0.27.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.27.2)

## [0.27.1] - 2026-07-21

### Fixes

- fix: reframe and relight the two newest heroes for card-scale readability (#92) ([`e8ac3b5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e8ac3b520e55d4fc3bf053ea5d9a212b368e51c9))

[Release v0.27.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.27.1)

## [0.27.0] - 2026-07-21

### Features

- feat: add light-link-studio example witnessing receiver collections in pixels (#91) ([`79d2fbc`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/79d2fbc5511bf02c224a14e959bca4f8c7b47c92))

[Release v0.27.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.27.0)

## [0.26.0] - 2026-07-21

### Features

- feat: add vse-gamma-cross example witnessing the blend-curve closed form (#90) ([`a93af61`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a93af6160d8715b88e34ef05f851b0f147d64d63))

[Release v0.26.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.26.0)

## [0.25.0] - 2026-07-20

### Features

- feat: add gltf-skin-roundtrip example witnessing the skinned export contract (#88) ([`c1a2f8d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c1a2f8d6099880cfac0c01a886e4413a37475bf2))

[Release v0.25.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.25.0)

## [0.24.0] - 2026-07-20

### Features

- feat: add triangulate-tangents example witnessing the mikktspace contract (#87) ([`7656c7f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7656c7f8d847be2a2a4d87b66a0f7d5c54e5148e))

[Release v0.24.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.24.0)

## [0.23.8] - 2026-07-20

### Fixes

- fix: make uv-layer-grid self-witness its render and restage the clipped hero (#86) ([`0fff770`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0fff77087681ecb774dc12f7c5de326c9926db51))

### Other

- docs: restore the Mesh, curves & text category lost in the README example index (#85) ([`efa8516`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/efa8516eebdb4319070b8d74536750c0d0378b34))

[Release v0.23.8](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.8)

## [0.23.7] - 2026-07-20

### Fixes

- fix: sync vertex-weight-limit README numbers to the remodeled check output (#84) ([`750b576`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/750b576265decb6dc215e22c54a11a8652d30fcb))

[Release v0.23.7](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.7)

## [0.23.6] - 2026-07-20

### Fixes

- fix: give vertex-weight-limit's arm its armor pass (#83) ([`b3d064f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b3d064f001e27ebf84f13dc19e594fca76b3157b))

[Release v0.23.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.6)

## [0.23.5] - 2026-07-19

### Fixes

- fix: rebuild the elbow as a readable hinge in vertex-weight-limit (#82) ([`d8037f5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d8037f5acd3bd30bd8c0aaf9443ab1864dead39c))

[Release v0.23.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.5)

## [0.23.4] - 2026-07-19

### Fixes

- fix: connect vertex-weight-limit's arm parts and straighten the reach (#81) ([`065bfce`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/065bfce7f63ff868434a19a72736f50d13f16c4e))

[Release v0.23.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.4)

## [0.23.3] - 2026-07-19

### Fixes

- fix: remodel vertex-weight-limit's mech arm as an actual machine (#80) ([`7b30839`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7b30839e58a8d6de32f38f81d6a580c2267c48f6))

[Release v0.23.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.3)

## [0.23.2] - 2026-07-19

### Fixes

- fix: rebalance vertex-weight-limit hero framing (#79) ([`691008a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/691008a057c53d2394faf8e864bebd3ed6f158fc))

[Release v0.23.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.2)

## [0.23.1] - 2026-07-19

### Fixes

- fix: audit game-pipeline arc heroes and stage vse-cut-list presentation (#78) ([`704b1e4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/704b1e4dba4c9c6f36314bd0ee260a11c0f230a2))

[Release v0.23.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.1)

## [0.23.0] - 2026-07-19

### Features

- feat: add vertex-weight-limit example witnessing the 4-influence skinning cap (#77) ([`5a6fbee`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5a6fbee41cfd479ca03d473f87bb122840bc0cf8))

[Release v0.23.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.23.0)

## [0.22.0] - 2026-07-19

### Features

- feat: add lod-decimate-chain example witnessing the modifier LOD contract (#76) ([`82e80b9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/82e80b9b13cb40b29f099cbfe0ea16d9101dc0f8))

[Release v0.22.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.22.0)

## [0.21.0] - 2026-07-19

### Features

- feat: add gltf-export-roundtrip example witnessing glTF interchange contracts (#75) ([`26396cd`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/26396cdd23113690ab037c5da1800c826ae70af3))

### Other

- docs: expand CLAUDE.md with mandatory context-mode routing rules ([`a483d26`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a483d26775caf12c8f9090b3d0ee94cb5ddb2c37))
- docs: add live MCP vs headless harness guidance (#74) ([`f4aaf35`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f4aaf35f74c1c1049a0ee70b25d25d08672551df))
- docs: enhance new-example-prompt with detailed guidance on subject selection and API contract validation ([`fdb9ea9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fdb9ea9ce49cfbb97b3ab265dd9ad6b0caa4574b))

[Release v0.21.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.21.0)

## [0.20.0] - 2026-07-19

### Features

- feat: add vse-cut-list example witnessing the 4.5-to-5.x sequencer API rename (#73) ([`ddd2ba7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ddd2ba72a6f87db25efe19287e615f90c58b0d2e))

### Other

- docs: make CLAUDE.md the canonical home of the pinned contact-sheet set (#72) ([`1420eb5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1420eb53716641d3290339796cdc2e7cdf1f6958))
- docs: codify operational lessons from recent runs into agent guidance (#71) ([`df004b9`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/df004b9f90a9c06fe46b0a1941875f7d9266807a))

[Release v0.20.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.20.0)

## [0.19.1] - 2026-07-19

### Fixes

- fix: restage png-exr-alpha hero into dark studio house style (#70) ([`3999f33`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3999f33c66707f0b083ca6c66f7ddbbc8c255e7d))

[Release v0.19.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.19.1)

## [0.19.0] - 2026-07-19

### Features

- feat: add png-exr-alpha float PNG false-unpremul witness ([`dcb9b0a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/dcb9b0a508ff9fae5d44387d07837edbde1d8cfb))

[Release v0.19.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.19.0)

## [0.18.1] - 2026-07-19

### Fixes

- fix: stop gallery card alts truncating on dotted API paths ([`98e86a0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/98e86a0b32a7f503e75c18a74a4bbda53a2a12cc))

### Other

- docs: version new-example prompt with VISUAL-STYLE and contact-sheet gate ([`fc48228`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fc4822894ba003d9bd2724c49da23806850f2207))

[Release v0.18.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.18.1)

## [0.18.0] - 2026-07-19

### Features

- feat: add uv-layer-grid example witnessing create_grid calc_uvs silent no-op ([`68bf1f2`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/68bf1f2640a918b66c0de0c9047998364fc8666f))

[Release v0.18.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.18.0)

## [0.17.4] - 2026-07-19

### Fixes

- fix: final gallery quality run â€” hero-material redesigns for bmesh-gear, gn-sdf-remesh, depsgraph-export (#66) ([`7371433`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/737143373b004f63df94febb4696b3f1937ee378))

[Release v0.17.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.17.4)

## [0.17.3] - 2026-07-19

### Fixes

- fix: complete the gallery quality pass â€” turntable regression, three old-era restages (#65) ([`10ecb07`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/10ecb073f61077af24e9ae0e86c18397b4964aa3))

### Other

- ci: enforce the README example count in validate-counts (#64) ([`1ac2458`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1ac24583d6cd9a057ae1e111f630898193dc8d94))
- docs: README quality-of-life pass â€” collapsible example categories, quick start, nav strip (#63) ([`6f199ef`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6f199ef076b1b78470fc3bc852f2995e040cc383))

[Release v0.17.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.17.3)

## [0.17.2] - 2026-07-19

### Fixes

- fix: gallery quality audit pass two â€” restage the seven pre-#61 examples and codify the visual style (#62) ([`a284898`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a2848981beac59e7cfd3216275ab9a8d488c08a8))

[Release v0.17.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.17.2)

## [0.17.1] - 2026-07-18

### Fixes

- fix: gallery quality audit of the six newest examples (restage color-attribute-wheel, relight armature-bend) (#61) ([`2c7051b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2c7051b0ef0e776f6202c44ff0a56660ac5a6c5c))

[Release v0.17.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.17.1)

## [0.17.0] - 2026-07-18

### Features

- feat: add image-pixels-testcard example (flat RGBA pixel buffer + save() lifecycle witness) (#60) ([`256f98d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/256f98deba6a6838ad3f2b43f67cb42b58924937))

[Release v0.17.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.17.0)

## [0.16.0] - 2026-07-18

### Features

- feat: add text-version-stamp example (TextCurve solids + self-labeling renders) (#59) ([`6b2d0f8`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6b2d0f80b98aefb3a8a1a788bdb958907651f958))

[Release v0.16.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.16.0)

## [0.15.0] - 2026-07-18

### Features

- feat: add armature-bend example (edit_bones + LBS closed-form witness) (#58) ([`01c186b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/01c186b15ece499a3c50323523851a5530308778))

[Release v0.15.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.15.0)

## [0.14.0] - 2026-07-18

### Features

- feat: add grease-pencil-rosette example (GPv3 attribute API drift witness) (#57) ([`2c4bdc4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2c4bdc4bed38ecf54070bbdd504a06949a2003b6))

[Release v0.14.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.14.0)

## [0.13.1] - 2026-07-18

### Fixes

- fix: harden example checks and close review findings across eight examples (#56) ([`b8b0a42`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/b8b0a42dc3d8bb5ee77f0b023ca814668940a6cd))

[Release v0.13.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.13.1)

## [0.13.0] - 2026-07-18

### Features

- feat: add parent-inverse-orrery example (matrix_parent_inverse contract) (#55) ([`3120077`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3120077e7d660fe8506264260399eb69a53f3332))

### Other

- docs: remove injected context-mode block from CLAUDE.md ([`4733e7f`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/4733e7f7eec9d173411976e925542f42ce622a77))

[Release v0.13.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.13.0)

## [0.12.0] - 2026-07-18

### Features

- feat: add color-attribute-wheel example (#54) ([`f3907d4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f3907d4e09c4051df039085ce6f8e3a584a175b7))

[Release v0.12.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.12.0)

## [0.11.1] - 2026-07-18

### Fixes

- fix: polish damped-track-aim gallery still and studio lighting ([`6c36858`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6c36858fc5eb65121075d11c45e9a0800f77f52d))

[Release v0.11.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.11.1)

## [0.11.0] - 2026-07-18

### Features

- feat: add damped-track-aim smoke-gated example ([`ffa9d30`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ffa9d30a5974704185a41e147bbfad384866add3))

[Release v0.11.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.11.0)

## [0.10.0] - 2026-07-18

### Features

- feat: add compositor-glare smoke-gated example ([`1317575`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/131757591c893ae5d6d1f46090810f978953f229))

[Release v0.10.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.10.0)

## [0.9.2] - 2026-07-03

### Fixes

- fix: review polish for the four newest examples + documentation currency (#51) ([`0df86fb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0df86fb20847023035545c08020289add5de22b5))

[Release v0.9.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.9.2)

## [0.9.1] - 2026-07-03

### Fixes

- fix: strengthen the four newest examples' checks and renders ([`ca97a6e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ca97a6eb8d052680f82faa122cc4c141c76a6112))

[Release v0.9.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.9.1)

## [0.9.0] - 2026-07-03

### Features

- feat: add shape-key-blend and curve-bevel-arc smoke-gated examples ([`268c3f7`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/268c3f7567fbb1fee925474e15d8cb4820d0bb26))

[Release v0.9.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.9.0)

## [0.8.0] - 2026-07-03

### Features

- feat: add temp-override-join and gn-instance-grid smoke-gated examples ([`a8f82e0`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a8f82e033d28934bd5ce230e24f44f817e1fcdb6))

### Other

- chore: ignore the local new-example prompt doc ([`df3dd6d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/df3dd6db08f73c26ab379f5f372340b9f8c38635))

[Release v0.8.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.8.0)

## [0.7.0] - 2026-07-03

### Features

- feat: two more smoke-gated examples â€” bmesh-gear and shader-node-group (#47) ([`869f600`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/869f6002ee8c9eaf2df812fce211164e3d39bd43))

[Release v0.7.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.7.0)

## [0.6.1] - 2026-07-03

### Fixes

- fix: give the four newer example renders real material identities (#46) ([`7c61ce5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/7c61ce5d7eca4179a6fe44007cabec2dea11674c))

### Other

- docs: favicon joins the viewport design system (#45) ([`e59421a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e59421afa374b55a76a47850b198949720271023))

[Release v0.6.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.6.1)

## [0.6.0] - 2026-07-03

### Features

- feat: two new smoke-gated examples â€” wave-displace and driver-wave (#44) ([`0884fce`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/0884fce4fa18d80e72b23d6e5330da8f81b0534c))

### Other

- docs: redesign the site as a Blender viewport session (#43) ([`6b822a3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6b822a358f0484bb6e43ab12a9d1eefdd34dd114))
- docs: per-example detail pages in the gallery (#42) ([`766f3af`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/766f3afe8ace7b6681920ab97c801f3cf233c48a))
- docs: vendor the landing-page build; examples showcase + full stats (#41) ([`3679858`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3679858b2a2d7009cc8d92d5322e657a11eb7d88))

[Release v0.6.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.6.0)

## [0.5.2] - 2026-07-03

### Fixes

- fix: real install steps + depsgraph-export joins the gallery (#40) ([`fc1f872`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/fc1f87229d90f1af70613909fd9a33e258675738))

[Release v0.5.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.5.2)

## [0.5.1] - 2026-07-03

### Fixes

- fix: reconcile plugin.json manifest with repo and CI-gate it (#39) ([`996083d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/996083db47c57e42a49a32fd3042fa0f14872e55))

### Other

- chore(deps): bump actions/upload-pages-artifact from 4 to 5 (#38) ([`5a96cef`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5a96cefcce92fe2316cca49138de24093254c3e3))
- chore(deps): bump actions/configure-pages from 5 to 6 (#37) ([`241ebc3`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/241ebc31947100c0f3fc94b97e0e597f49808638))
- chore(deps): bump actions/checkout from 4 to 7 (#36) ([`462dc43`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/462dc43326698cb58543296681fec0448be3b709))
- chore(deps): bump actions/setup-python from 5 to 6 (#35) ([`cadfecf`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/cadfecf520d1850359adf0e49579cad5d2fdb551))
- docs: document context-mode MCP routing rules in CLAUDE.md (#34) ([`ac9cd25`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ac9cd25c617df73035254b2605472591c3b44b28))
- docs: add repository technical audit and roadmap (#33) ([`a438b5e`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/a438b5e31feb2e24796e6f7dc95427e8afae1d3f))
- docs: uniform 16:9 gallery heroes + self-sufficient nav (#27) ([`f70a286`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f70a286fe71e24b5345c6411ffa9165961b4d8f6))
- docs: note fleet facelift + examples support ship as one change (#26) ([`ce26d07`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/ce26d07391dc6b30fa38a9e5a351d14c1207f967))
- docs: facelift the examples gallery + enrich landing meta (#25) ([`6f201ff`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6f201ff012b1fae9851216ae588b058c2abbcafd))
- docs: record fleet Pages examples support as a roadmap candidate (#24) ([`427fde6`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/427fde621ea9c91e9e27e4bd4fbef4ddf5e3c54c))
- docs: add local examples gallery on GitHub Pages (#23) ([`8c02d5c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8c02d5cedb37de4aea8449df68bdec389769a841))
- docs: refresh examples showcase with previews (#22) ([`1a5d62d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/1a5d62de5cce41069ccfc08e0b20dde53a66e8bb))

[Release v0.5.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.5.1)

## [0.5.0] - 2026-06-20

### Features

- feat: add depsgraph-evaluated export example with smoke gate (#21) ([`2ad60ca`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2ad60ca06488e9bea79c92a3ac8da21c105f7895))

[Release v0.5.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.5.0)

## [0.4.1] - 2026-06-20

### Fixes

- fix: carry material through the GN SDF remesh with Set Material (#20) ([`8b05113`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/8b05113b787b14ef59a318d02b4b04bd77b2cbdf))

### Other

- docs: decouple roadmap themes from version pins (#19) ([`2f4630c`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2f4630c54f47f4360998b0732f349c4756b6e786))
- docs: add turntable and SDF-remesh previews to README Examples (#18) ([`6eb86b1`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6eb86b139f4ea3cf7cc2c1e78e23031b99e71630))

[Release v0.4.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.4.1)

## [0.4.0] - 2026-06-20

### Features

- feat: add turntable and GN SDF-remesh examples with smoke gates (#17) ([`3775e1d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/3775e1d1cab9a775c5c5a41e7995a7cad8a0e665))

### Other

- docs: add Examples showcase to README with swatch-grid preview (#16) ([`d27a4ef`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/d27a4ef63a35aba09fda2b276f5bcde957d17ad1))

[Release v0.4.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.4.0)

## [0.3.0] - 2026-06-20

### Features

- feat: add swatch-grid example with smoke-gate coverage (#15) ([`f8cc567`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f8cc5678a9ab2c661a2491f3b7d70dc0fc386887))

### Other

- docs: note docs/chore changes do not trigger a release (#14) ([`577a300`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/577a3007a695d4c57a03e80990ebdf26be83fbcb))

[Release v0.3.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.3.0)

## [0.2.9] - 2026-06-19

### Fixes

- fix: gate release on a release-worthy conventional commit (#13) ([`f5b567a`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f5b567aa8ae71500406cba47b7d7ba1d780d1361))

### Other

- ci: align blender-smoke to actions/checkout@v7 (#12) [skip ci] ([`be66a85`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/be66a858dcf6f49ad99a36b87dd344034bcc1817))
- chore(deps): bump actions/stale from 9 to 10 (#6) [skip ci] ([`6371d3d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6371d3dd347762dbe09b5c38ca0e8531138c68d3))
- chore(deps): bump actions/checkout from 6 to 7 (#11) [skip ci] ([`e153899`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e153899693d1fb3faa09d5fb94ea69e9b4246e9d))
- ci: add Blender smoke-test workflow running examples in real Blender (#10) [skip ci] ([`9ad35cd`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9ad35cd4f0389a7c7ee0a3e69406a86fc6af7edd))

[Release v0.2.9](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.9)

## [0.2.8] - 2026-06-19

### Fixes

- fix: driver_namespace id_type and SDF-grid meshing in skills (#9) ([`f21a7d4`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/f21a7d4d6d14bb6b87c134574851a2cfd889be2b))

[Release v0.2.8](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.8)

## [0.2.7] - 2026-06-18

### Fixes

- fix: remove stray context-mode block from CLAUDE.md and substantiate verification claims (#8) ([`5f6cbdf`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5f6cbdf86766679ceacf2bb633a16077662305b9))

[Release v0.2.7](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.7)

## [0.2.6] - 2026-06-18

### Fixes

- fix: correct version-accuracy defects across skills and snippets (#7) ([`c39032d`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c39032d726f8569f3b1bc3052a23e6b69c942d6b))

[Release v0.2.6](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.6)

## [0.2.5] - 2026-06-18

### Other

- docs: add mandatory routing rules for context-mode and update tool usage guidelines ([`881e17b`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/881e17b055f6b97b9d7be3a59b6afbba7bd70b97))

[Release v0.2.5](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.5)

## [0.2.4] - 2026-06-13

### Other

- chore: add .cursor-plugin/plugin.json manifest (#5) ([`9aa2adb`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/9aa2adbee7f91f3f083c4ad64c64d064e6062840))

[Release v0.2.4](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.4)

## [0.2.3] - 2026-06-13

### Other

- chore: onboard to Developer-Tools-Directory standards 1.10.0 (#4) ([`e6324e5`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/e6324e50e76926a09174fc4e9e1a0f77de6ae971))

[Release v0.2.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.3)

## [0.2.2] - 2026-06-13

### Fixes

- fix: correctness pass on Blender skills, snippets, and docs (#3) ([`c801f77`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/c801f77f00b0e7060c5d300fc6fee790547dd39e))

[Release v0.2.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.2)

## [0.2.1] - 2026-06-13

### Other

- docs: add horizontal rule to README for improved section separation ([`2619f16`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/2619f16d58af5c69c4acaaab73cf8ae7add15759))

[Release v0.2.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.1)

## [0.2.0] - 2026-04-26

### Features

- feat: v0.2.0 content expansion, 4 skills, 2 rules, 1 template, 7 snippets ([`5a05f16`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/5a05f16427239777d5a2044525365c9b7f21eda7))

[Release v0.2.0](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.2.0)

## [0.1.3] - 2026-04-26

### Fixes

- fix: remove paths-ignore from release.yml so content edits fire release pipeline (#2) ([`6b2c190`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6b2c1908a084a530db11ac66b4d28cc6f73d18a0))

[Release v0.1.3](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.1.3)

## [0.1.2] - 2026-04-26

### Fixes

- fix: backfill DCO and inbound license grant section in CONTRIBUTING.md (#1) ([`6563afa`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/6563afadb81fb94107f9f90d27746efdd02fe041))
- fix: correct README license badge to CC-BY-NC-ND-4.0 and bump version badge to 0.1.1 ([`eb09c30`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/eb09c30fbc7463cca84e34e75004a809c12640d7))

[Release v0.1.2](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.1.2)

## [0.1.1] - 2026-04-26

### Fixes

- fix: correct license to CC-BY-NC-ND-4.0 and complete ecosystem standard files ([`98f4cfe`](https://github.com/TMHSDigital/Blender-Developer-Tools/commit/98f4cfe20831056d32abcab577d2498030d75bb5))

[Release v0.1.1](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.1.1)

## [0.1.0] - 2026-04-26

Initial release. 8 skills, 4 rules, 1 template, and 10 snippets covering Blender 5.1 Python development with 4.5 LTS fallback support.

### Added

- 8 skills: `addon-scaffolding`, `operators`, `ui-panels`, `custom-properties`, `mesh-editing-and-bmesh`, `headless-batch-scripting`, `slotted-actions-animation`, `geometry-nodes-python`
- 4 rules: `prefer-data-over-ops-in-loops`, `always-free-bmesh`, `target-extensions-platform-format`, `type-annotate-props-and-defend-context`
- 1 template: `extension-addon-template` demonstrating Extensions Platform format with `register_classes_factory`, a `PointerProperty` binding, and symmetric `register`/`unregister`
- 10 snippets covering canonical object creation and deletion, depsgraph evaluated mesh, bmesh load-edit-free, `temp_override` context, `foreach_set` vertex bulk write, `register_classes_factory`, `PointerProperty` binding, cross-version property delete, and the `action_ensure_channelbag_for_slot` slotted-actions bridge
- CI/CD: `validate.yml` (with `validate-counts`), `drift-check.yml` (consuming `drift-check@v1.9`), `release.yml` (consuming `release-doc-sync@v1`), `label-sync.yml` (self-healing per-label `gh label create --force`)
- `dependabot.yml` covering the `github-actions` ecosystem
- Standards-version markers at `1.9.1` throughout
