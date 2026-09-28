---
created: "2026-06-02 21:29"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: both
source_ids: [14435, 14459, 14641]
---

# DeepWiki MCP integration rejected for the forge pipeline (issue #425)

Issue #425 ('Experiment: DeepWiki MCP as an opt-in, firewalled research accelerator for CS') was closed as not planned on 2026-06-03 by the maintainer: "I would like to close it as not planned. I personnaly don't want to interact with deepwiki mcp because the index from the deepwiki are often stale. Deepwiki required a user to refresh the indexing of the target repo and in some scenarios, many repo are not present in deepwiki yet." Do not propose wiring the DeepWiki MCP into the forge pipeline (AN/BS/CS/TS) as an evidence or citation source: a stale lead can pass re-grounding as a same-name match and yield a false citation with valid-looking provenance, and output would depend on a third-party crawl schedule. Even the firewalled fallback design that #425 carried (an opt-in `--research-leads=deepwiki` flag yielding leads only, every claim re-grounded to file:line at the pinned SHA, exact no-op when the MCP is absent) was declined. The `forge-auto` pipeline never calls the MCP; `deepwiki` survives only as its deprecated alias (`src/shared/references/pipeline-contracts.md`, `DEPRECATED_ALIASES` in `src/skf-forger/scripts/parse-pipeline.py`). Commit 72398eb3 (#511) removed update-skill's gh API, zread, deepwiki fallback chain, and `src/skf-update-skill/references/re-extract.md` §1b now forbids fetching changed files through them because the gh contents API serves the default branch and the zread and deepwiki indexes may sit at another commit, the same staleness that got #425 declined; that leaves the Source Access Resolution section of `src/skf-test-skill/references/source-access-protocol.md` as the one place where remote reading tools such as deepwiki stay an optional fallback, when the provenance map or the metadata.json exports fall short.
