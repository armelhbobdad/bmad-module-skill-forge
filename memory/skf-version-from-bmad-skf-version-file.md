---
created: "2026-03-28 14:45"
session: "1ec27677-8973-4242-a981-f2583a616495"
source: claude-mem
source_table: both
source_ids: [2902, 2904, 2924, 4474, 4476, 4478]
---

# Installed SKF version comes from _bmad/skf/VERSION

The standalone installer writes a single-line `{project-root}/_bmad/skf/VERSION` on every install/update (`tools/cli/lib/installer.js`, end of `copySrcFiles`) and records the same value under `version` in `_bmad/_config/skf-manifest.yaml`; it never copies `package.json` into `_bmad/skf/`, so a `_bmad/skf/package.json` probe can never succeed in an installed project. Wiring the health-check environment field to package.json was corrected by the user: "However, the SKF version should really be retrieved from package.json? every installation set the version for example in _bmad/skf/VERSION." `src/shared/health-check.md:310` now reads VERSION only, while `src/skf-create-skill/references/compile.md:144-147` and `src/skf-quick-skill/references/compile.md:69-71` still list `_bmad/skf/package.json` ahead of VERSION in their fallback chains — VERSION is the step that actually resolves. A development checkout of this repo has no `_bmad/skf/` (SKF is not installed into itself), so any version-resolution change has to be checked against a project where SKF is installed.
