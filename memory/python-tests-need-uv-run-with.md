---
created: "2026-05-15 17:07"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9670, 9676, 9677, 14680]
---

# Python tests need uv run --with for PEP 723 dependencies

Running pytest directly fails at collection with `ModuleNotFoundError` (pytest exit code 2) when a test importlib-loads a helper whose PEP 723 header declares a dependency, such as `jsonschema` for `src/shared/scripts/skf-validate-brief-schema.py` and `test/test-skf-campaign-state.py`, or `pyyaml` for many `src/shared/scripts/` helpers. `pip install jsonschema` is refused with the PEP 668 `externally-managed-environment` error, and a bare `uv run --no-cache pytest ...` fails with `Failed to spawn: pytest`, because no environment provides pytest. There is no pyproject/pytest.ini and `test/conftest.py` only isolates git; the full-suite invocation is `npm run test:python`, i.e. `uv run --with pytest --with pyyaml --with jsonschema --with ast-grep-cli==0.45.3 pytest test -o "python_files=test-*.py test_*.py *_test.py" -v`. Write spec and agent-prompt test commands with those `--with` flags from the start, replacing `test` with the files under test (bmad-build specs gave the bare form on 2026-11-04). `uv run` honours PEP 723 metadata only when it executes the script itself, not when pytest imports it, so a new dependency in a helper's `# dependencies = [...]` also needs a `--with <dep>` flag in `package.json` `test:python`. `docs/troubleshooting.md` documents the runtime side (bare `python3` → `ModuleNotFoundError: No module named 'yaml'`) but not this test side.
