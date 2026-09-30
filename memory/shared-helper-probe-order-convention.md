---
created: "2026-04-09 14:35"
session: "43564723-f0c6-47d6-826c-097212da743c"
source: claude-mem
source_table: observations
source_ids: [5030, 5041, 8183, 8189, 8203, 14611]
---

# Shared helper convention: probe order, stdin JSON, in-prompt fallback

Deterministic step logic (registry walking, manifest/export parsing, metadata rendering, envelope emission) lives in `src/shared/scripts/skf-*.py` (63 PEP 723 scripts, 47 of which declare no dependencies; each has a `test/test-skf-<name>.py` that `test:python` collects by file name), not in step prose. A step reaches a helper through a frontmatter `<name>ProbeOrder` list (installed `{project-root}/_bmad/skf/shared/scripts/<helper>` first, dev `{project-root}/src/shared/scripts/<helper>` second, "first existing path wins"; 48 step files carry the phrase) and invokes it as `uv run {helper}` so PEP 723 dependencies resolve, though 24 of those 48 call at least one dependency-free helper as plain `python3 {helper}` (`src/skf-quick-skill/references/compile.md:80`). What happens when no candidate exists is not uniform: some of those steps fall back to the legacy in-prompt procedure (`src/skf-quick-skill/references/resolve-target.md:91` falls back to the LLM walk of the registry data, `compile.md:68` to in-prompt rendering), while 18 say `HALT if no candidate exists`; match the convention of the workflow you are editing. Pure parsers such as `skf-extract-public-api.py` and `skf-render-quick-metadata.py` take a JSON payload on stdin and emit JSON on stdout with no file I/O, so the caller fetches content and tests stay offline; the helper, not the step prose, is the single source of truth for the schema it renders. Nothing in CONTRIBUTING.md or docs/architecture.md describes this contract; architecture.md:63 only says steps run scripts, usually with `uv run`.
