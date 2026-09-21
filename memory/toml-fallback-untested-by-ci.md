---
created: "2026-05-26 11:07"
session: "739f5e5f-80fd-400d-8fc4-60234db96ad3"
source: claude-mem
source_table: observations
source_ids: [13047, 13048, 13056]
---

# Python 3.10 TOML fallback in skf-shape-detect.py is untested by CI

`src/shared/scripts/skf-shape-detect.py` declares `requires-python = ">=3.9"` and, when `tomllib` is unavailable (Python < 3.11; README requires >= 3.10, so 3.10 users hit it), parses `pyproject.toml`/`Cargo.toml` with the hand-written `_loads_toml_fallback` (line 382). CI never exercises that path: `.github/workflows/quality.yaml:191` and `release.yaml:98` pin `python-version: "3.12"`, and no test references `_loads_toml_fallback`. The fallback has known limits: it terminates a multi-line array at the first `]` anywhere on a line (a trailing `# version [2.28]` comment or a PEP 508 `pkg[extra]` truncates the dependency list, because comment stripping is skipped for values starting with `[`) and it ignores escape sequences and escaped quotes inside strings; these were triaged as deferred in the gitignored `_bmad-output/implementation-artifacts/deferred-work.md`. When dependency detection is wrong on 3.10, suspect the fallback parser before the shape heuristics, and do not read a green CI as evidence for 3.9/3.10.
