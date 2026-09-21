---
created: "2026-04-27 11:42"
session: "4413807b-d437-4757-bb96-ea6cb8c785dd"
source: claude-mem
source_table: observations
source_ids: [7697, 7698, 7711, 7713]
---

# Deferred python3 sites for stdlib-only helpers

Only the PyYAML-dependent helpers were cut over to `uv run` (2026-04-27); stdlib-only helpers (`# dependencies = []`) were deliberately left on `python3` as deferred cleanup, and about 60 step-file sites still read `python3 {atomicWriteHelper}` (27), `python3 {manifestOpsHelper}` (10), `python3 {rebuildManagedSectionsHelper}` (7) and similar across skf-create-skill, skf-create-stack-skill, skf-test-skill, skf-export-skill, skf-rename-skill and skf-drop-skill. The cut-over scripts' docstrings say `uv run` is canonical even when `dependencies = []`, so an existing `python3` site is not precedent for a new helper or a helper with deps. The moment a stdlib-only script gains a dependency, grep every `python3 {itsHelperVar}` site and convert it, because `npm run test:python` runs under `uv run --with pyyaml … pytest` and will keep passing while fresh installs fail with `ModuleNotFoundError`.
