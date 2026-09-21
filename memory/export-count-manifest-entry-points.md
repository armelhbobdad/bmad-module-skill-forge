---
created: "2026-06-04 19:30"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [15447, 15461]
---

# export_count counts manifest entry points, not symbols

In `src/shared/scripts/skf-shape-detect.py`, `export_count` is `len(package.json exports)` for Node (line ~490, falling back to 1 when only `main`/`module` exist), `len(scripts) + len(gui_scripts)` for Python (~549) and `(1 if has_lib) + len(bin_targets)` for Go (~594); measured on real targets it gives three.js → 8, lodash → 1, hono → 75. The script docstring (line 43) and `src/skf-analyze-source/references/step-shape-detect.md:42` call it "total public-facing exports", but it counts manifest entry points, so it cannot gauge API-surface size — the real symbol count only materialises during AST extraction in skf-create-skill, after scoping is decided. That is why the `export_count > 500` decomposition trigger was retired as unreachable in PR #443: decomposition is now monorepo-only (`package_count > 3`, cohesion-checked in `step-auto-scope.md` §3b) and a single large library is one skill that skf-create-skill's auto-shard splits at the 400-line ceiling. The surviving `export_count > 200 → public-api` row in the Shape → Scope Type Mapping table has the same flaw, so treat any threshold on `export_count` in the hundreds as effectively never firing.
