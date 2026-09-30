---
created: "2026-04-09 00:27"
session: "4a1c1afc-7896-4732-8b7d-d05e14e39405"
source: claude-mem
source_table: both
source_ids: [5036, 5042, 7637, 8353, 8481]
---

# test:python collection of test/ by file name, not an explicit file list

Since PR #615 (commit 8234ef7a), `package.json` `test:python` is `uv run --with pytest --with pyyaml --with jsonschema --with ast-grep-cli==0.45.3 pytest test -o "python_files=test-*.py test_*.py *_test.py" -v`, so pytest collects every file under `test/` whose name matches those patterns and a new `test/test-*.py` runs as soon as it exists, with no list to append it to. That script is the only way Python tests run under `npm test`, `npm run quality`, the husky pre-commit hook (`.husky/pre-commit` runs `npm test`) and CI (`.github/workflows/quality.yaml` "Run Python tests"). The patterns live only in that command (there is no `pytest.ini` or `pyproject.toml`, and `test/conftest.py` only isolates git), and pytest's default `python_files` (`test_*.py *_test.py`) does not match the repository's hyphenated `test-*.py` names, so a bare `pytest test` collects none of them. Before PR #615 the script was a hand-maintained list of paths and a file left off it silently never ran (PRs #308/#309/#310 shipped three test files that never ran until PR #311 ("wire 4 latent test files into CI") registered them), so a note, branch or instruction that says to append a Python test file to `test:python` predates the change. CONTRIBUTING.md now states the rule: "there is no list to add it to".
