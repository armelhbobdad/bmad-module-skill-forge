---
created: "2026-05-15 17:17"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9687, 9688, 9696, 9752, 9755]
---

# Windows CI POSIX-path and CRLF fixture trap

The `python (windows-latest)` job in `.github/workflows/quality.yaml` fails while ubuntu passes whenever a `src/shared/scripts` helper emits, fnmatch-compares, or a test asserts on `str(Path)`: Windows yields `scripts\\deploy.sh`, so `--scope-include scripts/*` never matched, and `test-skf-resolve-authoritative-files.py::TestHeuristicScan::test_prunes_excluded_dirs` expected `{'src/llms.txt'}` but got `{'src\\\\llms.txt'}`. Normalize with `path.relative_to(root).as_posix()` on both the emitting and asserting side (see `matches_scope` in `skf-detect-scripts-assets.py`; fix commits d6b4de5d, 2c06c716, 21e9470f). Separately, fixtures feeding size or SHA-256 assertions must be written with `path.write_bytes(content.encode("utf-8"))`, not `Path.write_text()`, which translates LF to CRLF on Windows (`test-skf-hash-content.py` saw 26 bytes instead of 24 and classified UNCHANGED as MODIFIED_FILE). `.gitattributes` forces LF for checked-in files but does nothing for files a test writes at runtime.
