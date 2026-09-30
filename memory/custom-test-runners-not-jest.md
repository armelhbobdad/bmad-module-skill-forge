---
created: "2026-04-09 23:33"
session: "3f373a49-0cdd-4599-b4f8-6b8214af3f47"
source: claude-mem
source_table: observations
source_ids: [5155, 5157]
---

# Custom Node test runners, not Jest

The JavaScript tests under `test/` (`test-cli-integration.js`, `test-agent-schema.js`, `test-installation-components.js`, `test-knowledge-base.js`, `test-workflow-state.js`, `test-rehype-markdown-links.js`, `test-validate-docs-links.js`, `test-validate-file-refs.js`, `test-validate-no-em-dash.js`, `test-changes.js`, `test-tool-requirements.js`) are self-contained Node scripts with their own runner (a local `assert()`, a local `test(name, fn)` over `node:assert`, or a fixture loop in `test-agent-schema.js`) and colored output, each wired to its own `test:*` script in `package.json` and exiting 0 or 1; `test/unit-test-schema.js` is wired to no script, so neither `npm test` nor CI runs it. Python tests run through `npm run test:python`, which is `uv run --with pytest --with pyyaml --with jsonschema --with ast-grep-cli==0.45.3 pytest test -o "python_files=test-*.py test_*.py *_test.py" -v` (every `test/test-*.py`, collected by file name) and imports modules from `src/shared/scripts/` via `importlib`. `jest` (^30) sits in `devDependencies` but no test file, npm script or config uses it, so a Jest test would never run in `npm test` or CI. Add a JS test as another `test/test-*.js` script registered in the `test` and `quality` scripts, and a Python test by naming it `test/test-*.py`, which `test:python` collects with no registration.
