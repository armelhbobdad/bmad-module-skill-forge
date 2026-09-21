---
created: "2026-05-15 17:19"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9692, 9693, 9739, 9740, 9743]
---

# fnmatch double-star mismatch for brief scope globs

Brief `scope.include`/`scope.exclude` globs are gitignore-style (`**/llms.txt`, `**/_bmad` as in `src/shared/scripts/skf-merge-ccc-exclusions.py`), but Python's `fnmatch` treats `**` as two literal `*`: `fnmatch.fnmatch("llms.txt", "**/llms.txt")` is False. `test_unresolved_reports_matching_exclude` in `test/test-skf-resolve-authoritative-files.py` failed with `IndexError` (empty `unresolved` list) until `skf-resolve-authoritative-files.py` got `_glob_to_regex()`/`glob_match()` — `**` matches zero or more path segments, `*` and `?` never cross `/`, compiled regexes are cached, and `TestGlobMatch` pins the semantics. Reuse `glob_match` for any new brief-scope matching rather than `fnmatch`. `skf-detect-scripts-assets.py::matches_scope()` still uses plain `fnmatch` for `--scope-include` (only normalised with `.as_posix()` so `scripts/*` matches on Windows), so a `**` pattern passed there silently matches nothing.
