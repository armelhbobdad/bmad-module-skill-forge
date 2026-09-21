---
created: "2026-05-15 17:07"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9670, 9676, 9677, 14680]
---

# Python tests need uv run --with for PEP 723 dependencies

Running pytest directly on the Python suite fails at collection with `ModuleNotFoundError` (pytest exit code 2) whenever a test importlib-loads a helper whose PEP 723 header declares a dependency — `test/test-skf-campaign-state.py` and `src/shared/scripts/skf-validate-brief-schema.py` need `jsonschema`, most helpers need `pyyaml` — and `pip install jsonschema` is refused with the PEP 668 `externally-managed-environment` error. There is no pyproject/pytest.ini/conftest; the working invocation is `npm run test:python`, i.e. `uv run --with pytest --with pyyaml --with jsonschema pytest …`. `uv run` honours PEP 723 metadata only when it executes the script itself, not when pytest imports it, so every new dependency declared in a helper's `# dependencies = [...]` must also be added as a `--with <dep>` flag in `package.json` `test:python` (that is how `--with jsonschema` got there). `docs/troubleshooting.md` documents the runtime side of the same trap (bare `python3` → `ModuleNotFoundError: No module named 'yaml'`) but not the test side.
