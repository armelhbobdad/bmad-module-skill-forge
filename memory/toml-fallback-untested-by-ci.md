---
created: "2026-05-26 11:07"
session: "739f5e5f-80fd-400d-8fc4-60234db96ad3"
source: claude-mem
source_table: observations
source_ids: [13047, 13048, 13056]
---

# skf-shape-detect.py lost its TOML fallback: every helper declares Python 3.11

`src/shared/scripts/skf-shape-detect.py` used to declare `requires-python = ">=3.9"` and, without `tomllib`, parse `pyproject.toml` and `Cargo.toml` with a hand-written `_loads_toml_fallback` that CI never ran (CI ran 3.12). It misread a PEP 508 extra (`requests[socks]`), a `]` in a trailing comment, escaped quotes and dotted keys (`pest.workspace = true`), which changed the shape analyze-source's auto-scope picked (#562). uv picks each script's interpreter from its PEP 723 header and honours a `.python-version` pin above the script only when the pin satisfies that header, so a low header let a project pinned to 3.10 reach the fallback although the docs said 3.11. Since #562 and #576 the fallback is deleted, the script imports `tomllib` unconditionally, every header under `src/` declares `>=3.11`, `node tools/tool-requirements.js --check` (in `npm test`, `npm run quality` and the quality workflow's validate job) fails on any `requires-python` header below Python's minimum in `src/shared/tool-requirements.yaml`, and the quality workflow runs the Python tests on 3.11. A new script declares `requires-python = ">=3.11"`; never add a stdlib fallback for an older Python.
