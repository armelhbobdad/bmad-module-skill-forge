---
created: "2026-06-02 21:29"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: both
source_ids: [14435, 14459, 14641]
---

# DeepWiki MCP integration rejected for the forge pipeline (issue #425)

Issue #425 ('Experiment: DeepWiki MCP as an opt-in, firewalled research accelerator for CS') was closed as not planned on 2026-06-03 by the maintainer: "I would like to close it as not planned. I personnaly don't want to interact with deepwiki mcp because the index from the deepwiki are often stale. Deepwiki required a user to refresh the indexing of the target repo and in some scenarios, many repo are not present in deepwiki yet." Do not propose wiring the DeepWiki MCP into the forge pipeline (AN/BS/CS/TS) as an evidence or citation source: a stale lead can pass re-grounding as a same-name match and yield a false citation with valid-looking provenance, and output would depend on a third-party crawl schedule. Even the firewalled fallback design that #425 carried (an opt-in `--research-leads=deepwiki` flag yielding leads only, every claim re-grounded to file:line at the pinned SHA, exact no-op when the MCP is absent) was declined. The `forge-auto` pipeline (formerly aliased `deepwiki`, see `src/shared/references/pipeline-contracts.md`) never calls the MCP; the only DeepWiki MCP mentions that remain are the pre-existing optional last-resort remote-reading fallbacks in `src/skf-update-skill/references/re-extract.md` and `src/skf-test-skill/references/source-access-protocol.md`.
