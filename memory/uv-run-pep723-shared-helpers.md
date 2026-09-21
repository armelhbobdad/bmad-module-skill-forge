---
created: "2026-04-27 11:38"
session: "4413807b-d437-4757-bb96-ea6cb8c785dd"
source: claude-mem
source_table: both
source_ids: [7690, 7691, 7699, 7702, 7711]
---

# uv run for PEP 723 shared helpers

Shared helpers in `src/shared/scripts/` that declare a non-empty PEP 723 `# dependencies = ["pyyaml"]` (skf-validate-frontmatter, skf-detect-tools, skf-forge-tier-rw, skf-preflight, skf-write-skill-brief, skf-validate-brief-schema, skf-description-guard and others — 14 at v2.1.0) must be invoked from step files and reference docs as `uv run {script}`; both bare `python3 {script}` and `uv run python {script}` skip the inline metadata and fail on a fresh interpreter with `ModuleNotFoundError: No module named 'yaml'`. This first surfaced on a fresh Windows `/skf-setup` and again through `uv run python` forms in step files, which is why `uv` is a documented prerequisite (docs/getting-started.md) and `/skf-setup` probes `uv --version` at activation (docs/troubleshooting.md). Nothing lints the convention — only `test/test-skf-step-doc-sources.py` asserts `uv run` for one step — and `npm run test:python` runs under `uv run --with pyyaml`, so a wrong invocation in a step file passes CI and only fails in a user's project.
