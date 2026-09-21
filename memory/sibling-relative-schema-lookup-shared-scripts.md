---
created: "2026-06-04 15:47"
session: "e58f8523-4c6a-4a67-9908-4211ba413cd7"
source: claude-mem
source_table: observations
source_ids: [15145, 15146, 15153, 15170]
---

# Sibling-relative schema lookup in shared scripts

`tools/cli/lib/installer.js` copies `src/shared/` wholesale to `_bmad/skf/shared/`, so an installed script runs from `_bmad/skf/shared/scripts/` with `schemas/` and `../data/` beside it and no `src/` tree anywhere above it. A shared script must therefore resolve its schema or data file relative to `__file__` (`Path(__file__).resolve().parent / "schemas" / ...` as `skf-validate-brief-schema.py:64` and `skf-emit-result-envelope.py:96` do; `skf-language-corpora.py:39` uses `parent.parent / "data"`), never by walking `parent` up to a repo root and appending `src/shared/...`. `skf-validate-brief-schema.py` did the latter and raised `FileNotFoundError` on every installed-layout run while `npm test` stayed green, because the dev suite executes the script in place under `src/`. The regression test `test_installed_layout_resolves_sibling_schema` in `test/test-skf-validate-brief-schema.py:407` copies the script into a fake `_bmad/skf/shared/scripts/` tree and runs it there — copy that pattern for any new script that loads a sibling file.
