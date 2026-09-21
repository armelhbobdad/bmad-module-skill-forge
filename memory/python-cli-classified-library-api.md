---
created: "2026-05-26 11:06"
session: "739f5e5f-80fd-400d-8fc4-60234db96ad3"
source: claude-mem
source_table: observations
source_ids: [13044, 13049, 13061]
---

# Python CLI tools classify as library-API in skf-shape-detect.py

`_parse_pyproject_toml` in `src/shared/scripts/skf-shape-detect.py` hardcodes `"has_bin": False` (line ~558) and counts `[project.scripts]` / `[project.gui-scripts]` entries into `export_count` rather than as a bin signal. So a Python CLI with entry points and no framework dependency (flask/django/fastapi…) is classified `library-API`, never `reference-app`; `step-shape-detect.md` lists only npm `bin`, Rust `[[bin]]` and framework deps as reference-app signals. A dead `if not has_bin` branch was removed in review but the classification was deliberately left unchanged, with no test for the scripts case (`test_python_library_without_scripts` in `test/test-skf-shape-detect.py` is the only Python baseline). Treat it as a known gap, not a bug to fix in passing: the shape feeds auto-scope's shape→scope mapping, auto-brief and the decomposition thresholds, so changing it changes downstream behaviour and needs a test.
