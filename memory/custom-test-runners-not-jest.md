---
created: "2026-04-09 23:33"
session: "3f373a49-0cdd-4599-b4f8-6b8214af3f47"
source: claude-mem
source_table: observations
source_ids: [5155, 5157]
---

# Custom Node test runners, not Jest

Every JavaScript test under `test/` (`test-cli-integration.js`, `test-agent-schema.js`, `test-installation-components.js`, `test-knowledge-base.js`, `test-workflow-state.js`, `test-rehype-markdown-links.js`, `test-validate-docs-links.js`) is a self-contained Node script with its own `assert()` helper and colored output, wired to its own `test:*` script in `package.json` and exiting 0 or 1. Python tests run through `npm run test:python`, which is `uv run --with pytest --with pyyaml --with jsonschema pytest <every test/test-*.py listed explicitly>` and imports modules from `src/shared/scripts/` via `importlib`. `jest` (^30) sits in `devDependencies` but no test file, npm script or config uses it, so a Jest test would never run in `npm test` or CI. Add a JS test as another `test/test-*.js` script registered in the `test` and `quality` scripts, and a Python test by appending its path to the `test:python` script.
