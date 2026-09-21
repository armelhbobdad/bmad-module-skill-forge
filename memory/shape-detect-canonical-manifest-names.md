---
created: "2026-06-01 21:12"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14123, 14124, 14125, 14126]
---

# skf-shape-detect.py rejects manifests not named canonically

`skf-shape-detect.py` dispatches on the exact manifest basename: `_parse_manifest` looks `path.name` up in `_PARSERS` (`src/shared/scripts/skf-shape-detect.py:801-817`), whose keys are `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `build.gradle.kts` and `Package.swift`. Any other name, e.g. a copy staged as `hono-package.json` to avoid collisions, exits 2 with `{"error": "Unsupported manifest type: hono-package.json", "code": "UNSUPPORTED_MANIFEST"}` on stderr and nothing on stdout, so a caller that `json.load`s the output sees a bare parse error rather than the real cause. When fetching manifests from several repos for a harness or validation run, stage them under per-repo subdirectories with their canonical names instead of prefixing the filename. Neither the module docstring nor `step-shape-detect.md` states this basename constraint.
