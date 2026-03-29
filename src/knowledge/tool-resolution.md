# Tool Resolution

Bridge names (`ast_bridge`, `ccc_bridge`, `qmd_bridge`, `gh_bridge`) and subprocess patterns (Pattern 1–4) used throughout SKF workflows are **conceptual interfaces**, not callable functions. This document provides the canonical mapping from abstract names to concrete tools per IDE environment.

## Bridge Resolution Table

| Bridge       | Operation                        | Claude Code                                                      | Cursor         | CLI                                                | Fallback                         |
|--------------|----------------------------------|------------------------------------------------------------------|----------------|----------------------------------------------------|----------------------------------|
| `ast_bridge` | `scan_definitions()`             | `mcp__ast-grep__find_code` or `mcp__ast-grep__find_code_by_rule` | ast-grep MCP   | `sg run` / `ast-grep -p`                           | Source reading (T1-low)          |
| `ast_bridge` | `detect_co_imports()`            | `mcp__ast-grep__find_code_by_rule` with co-import YAML rule      | ast-grep MCP   | `ast-grep run -p 'import $$$' --json=stream`       | grep-based co-import count       |
| `ccc_bridge` | `search(query, root, top_k)`     | `/ccc` skill search                                              | ccc MCP server | `cd {root} && ccc search --limit {top_k} "{query}"` | Skip silently                    |
| `ccc_bridge` | `ensure_index(root)`             | `/ccc` skill indexing                                            | ccc MCP server | `cd {root} && ccc init` + `ccc index`               | Skip silently                    |
| `ccc_bridge` | `status()`                       | `/ccc` skill status                                              | ccc MCP server | `ccc --help` + `ccc doctor`                        | Unavailable = `tools.ccc: false` |
| `qmd_bridge` | `search(query)`                  | `mcp__plugin_qmd-plugin_qmd__search`                             | qmd MCP server | `qmd search "{query}"`                             | Skip enrichment                  |
| `qmd_bridge` | `vector_search(query)`           | `mcp__plugin_qmd-plugin_qmd__vector_search`                      | qmd MCP server | `qmd vector_search "{query}"`                      | Use BM25 search only             |
| `qmd_bridge` | `version()`                      | `qmd --version` → parse `"qmd X.Y.Z"` → `"X.Y.Z"`              | qmd MCP server | `qmd --version`                                    | `"unknown"`                      |
| `gh_bridge`  | `list_tree(owner, repo, branch)` | `gh api repos/{owner}/{repo}/git/trees/{branch}?recursive=1`     | gh CLI         | `gh api ...`                                       | Direct file listing if local     |
| `gh_bridge`  | `read_file(owner, repo, path)`   | `gh api repos/{owner}/{repo}/contents/{path}`                    | gh CLI         | `gh api ...`                                       | Direct file read if local        |

## Subprocess Pattern Definitions

Workflow steps reference "subprocess" execution with numbered patterns. These map to concrete mechanisms per IDE:

| Pattern                                | Purpose                                               | Claude Code                                                          | Cursor                            | CLI                                |
|----------------------------------------|-------------------------------------------------------|----------------------------------------------------------------------|-----------------------------------|------------------------------------|
| **Pattern 1** (grep/search)            | Search across files for imports, co-imports           | Grep tool or Bash with `rg`                                          | Built-in search                   | `grep` / `rg`                      |
| **Pattern 2** (per-file deep analysis) | Deep analysis of individual files or units            | Agent tool (sequential per unit)                                     | Sequential analysis               | Per-unit script                    |
| **Pattern 3** (data operations)        | QMD queries, severity classification, data transforms | Main thread (Read + process)                                         | Main thread                       | Script                             |
| **Pattern 4** (parallel execution)     | Parallel per-library extraction, parallel diffing     | Agent tool with multiple parallel calls or `run_in_background: true` | Parallel requests (IDE-dependent) | `xargs -P` or background processes |

### max_parallel_generation

Referenced by Pattern 4 steps. Defines the maximum concurrent subprocess spawns:

| Environment | Recommended Value                | Notes                                                                 |
|-------------|----------------------------------|-----------------------------------------------------------------------|
| Claude Code | 3–5                              | Concurrent Agent tool calls; higher values may cause context pressure |
| Cursor      | IDE-dependent                    | Follow Cursor's agent concurrency limits                              |
| CLI         | CPU core count or user-specified | Use `xargs -P {n}` or equivalent                                      |

## Resolution Protocol

When a workflow step references a bridge name or subprocess pattern:

1. **Identify** the bridge name (`ast_bridge`, `ccc_bridge`, etc.) or pattern number (Pattern 1–4)
2. **Check tool availability** in `{sidecar_path}/forge-tier.yaml` → `tools.*` section
3. **Resolve** using the tables above — use the first available option in priority order: MCP tool → CLI command → Fallback
4. **Apply fallback** if no resolution is available — fallbacks are always defined and never block the workflow
5. **Log degradation** when falling back — note the reason in context for the evidence report

## Related Fragments

- [ccc-bridge.md](ccc-bridge.md) — CCC semantic discovery interface and lifecycle
- [progressive-capability.md](progressive-capability.md) — Quick/Forge/Forge+/Deep tier philosophy
- [confidence-tiers.md](confidence-tiers.md) — T1/T1-low/T2/T3 trust model and citation formats
- [qmd-registry.md](qmd-registry.md) — QMD collection producer/consumer/janitor architecture
