---
created: "2026-04-24 23:56"
session: "c987182d-1ed1-47cb-b550-cf9e6f2c658f"
source: claude-mem
source_table: session_summaries
source_ids: [2197, 2198, 2201]
---

# Line-number citations in prose docs go stale

Prose documents in this repo (`docs/_internal/RELEASING.md`, `STABILITY.md`, `CONTRIBUTING.md`) must not cite line numbers of other files such as `.github/workflows/release.yaml`; every edit to the target shifts them and nothing checks the drift. RELEASING.md once pinned `NPM_TOKEN: ""` to 'lines 191 + 688' and a later review called such topology claims stale; commit 7370b549 (PR #225) replaced the pins with a grep audit (`grep -c 'NPM_TOKEN: ""' .github/workflows/release.yaml`, expect 2). Reference a workflow by step name (`the \`Create and push tag\` step`), a doc section by anchor (`[§ Scenario D](#scenario-d--…)`), or give a grep command a reader can run, never `release.yaml:433\`.
