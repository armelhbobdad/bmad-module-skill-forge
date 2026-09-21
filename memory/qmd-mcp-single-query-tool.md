---
created: "2026-04-13 16:21"
session: "a5591f15-f074-4f5f-b70e-8260eba1d5ef"
source: claude-mem
source_table: observations
source_ids: [6103, 6127]
---

# QMD MCP exposes query/get/multi_get/status — no search or vector_search tools

The qmd MCP server (`@tobilu/qmd` 2.8.3, `dist/mcp/server.js`) registers exactly four tools: `query`, `get`, `multi_get`, `status`. `query` takes `searches=[{type:'lex'|'vec'|'hyde', query}]` plus `intent`, and its collection filter is `collections` (an array) — a singular `collection` or any other unknown parameter is silently ignored, not rejected. `search`, `vector_search` and `deep_search` do not exist and return tool-not-found; the CLI equivalents are `qmd search` (BM25), `qmd vsearch` (vector) and `qmd query` (hybrid) — there is no `qmd vector-search`/`vector_search` subcommand. `src/skf-create-skill/references/enrich.md:67-69` and `extraction-patterns.md:33` say this, but the canonical `src/knowledge/tool-resolution.md:14-15` they point to still maps `qmd_bridge` to `mcp__plugin_qmd-plugin_qmd__search`/`__vector_search`, as do `skf-update-skill/references/re-extract.md:240`, `skf-audit-skill/references/re-index.md:46`, `skf-create-stack-skill/references/parallel-extract.md:120` and `src/knowledge/qmd-registry.md:48,134` — treat those as stale and degrade non-fatally on tool-not-found instead of retrying the old names. The tool prefix also depends on how the plugin is installed: the repo writes `mcp__plugin_qmd-plugin_qmd__query`, a current Claude Code session exposes `mcp__plugin_qmd_qmd__query`.
