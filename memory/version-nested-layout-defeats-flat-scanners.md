---
created: "2026-05-23 21:27"
session: "8d69e137-3fdd-40ad-b913-20486596f67b"
source: claude-mem
source_table: observations
source_ids: [11384, 11386, 11402, 11403]
---

# Version-nested skills layout defeats flat SKILL.md scanners

Exported skills live at `{skills_output_folder}/{name}/{version}/{name}/SKILL.md` with a `{name}/active` symlink (`src/knowledge/version-paths.md`), so any helper that walks the skills folder and checks `skills/{child}/SKILL.md` finds nothing. `src/shared/scripts/skf-enumerate-stack-skills.py` did exactly that and returned `{"skills": [], "cycles": [], "warnings": []}` on a real project while its flat-layout test fixtures passed; commit 62a94a18 added `_resolve_package_dir` (the `active` symlink first, then the highest semver directory). When writing or testing a new scanner over the skills folder, reuse that resolver or `resolve_active_version` in `src/shared/scripts/skf-skill-inventory.py`, and build fixtures with `_make_nested_skill` from `test/test-skf-enumerate-stack-skills.py` — a flat fixture cannot catch this failure.
