---
created: "2026-04-09 00:27"
session: "4a1c1afc-7896-4732-8b7d-d05e14e39405"
source: claude-mem
source_table: both
source_ids: [5036, 5042, 7637, 8353, 8481]
---

# test:python is a hand-maintained explicit test-file list

`package.json` `test:python` — the only way Python tests run under `npm test`, `npm run quality`, the husky pre-commit hook (`.husky/pre-commit` runs `npm test`) and CI (`.github/workflows/quality.yaml` "Run Python tests") — is a single-line, hand-maintained list of `test/test-skf-*.py` paths passed to `uv run --with pytest --with pyyaml --with jsonschema pytest … -v`; there is no `pytest.ini`, `pyproject.toml` or `conftest.py` and no directory discovery. A new test file therefore passes when run directly but is silently never executed by the suite until its path is appended to that list (adding cases to an already-listed file needs nothing): PRs #308/#309/#310 shipped three test files that never ran until PR #311 ("wire 4 latent test files into CI") registered them. The tell is an unchanged test count after adding a file. CONTRIBUTING.md names `test:python` but never says new files must be registered there; as of v2.1.0 all 87 `test/test-skf-*.py` files are listed — `diff <(grep -o 'test/test-skf-[a-z0-9-]*\.py' package.json | sort -u) <(ls test/test-skf-*.py | sort)` should stay empty.
