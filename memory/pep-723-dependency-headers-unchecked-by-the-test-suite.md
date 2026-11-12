---
created: "2026-10-09 02:57"
session: "a5de91ad-9e43-4a0e-8b07-235a1486d3dc"
---

# PEP 723 dependency headers unchecked by the test suite

`npm run test:python` runs pytest under `uv run --with pytest --with pyyaml --with jsonschema ...`, and the tests launch helpers with `sys.executable`. So a helper whose own PEP 723 `# dependencies` line omits a package it needs passes every test, then fails in a user's project under `uv run {script}`. A #683 review showed it: `src/skf-update-skill/scripts/skf-new-file-diff.py` sibling-loads `src/shared/scripts/skf-resolve-authoritative-files.py` through `_shared`, and that file does a top-level `import yaml`. With the header's `pyyaml` deleted the suite stayed green, while the real call exited 2 with `cannot load skf-resolve-authoritative-files.py ... No module named 'yaml'`, halting every update at Category D. Nothing checks dependency lists repo-wide: `tools/tool-requirements.js` checks only `requires-python`. When a helper starts importing or sibling-loading a module that needs a third-party package, add that package to its header and pin it with a per-script header test like `TestScriptPEP723` in `test/test-skf-new-file-diff.py`, `test/test-skf-preapply.py` or `test/test-skf-build-change-manifest.py`.
