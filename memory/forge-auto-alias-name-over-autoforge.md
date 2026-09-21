---
created: "2026-06-02 21:30"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14433, 14442, 14446, 14448]
---

# forge-auto alias name over deepwiki and autoforge

The zero-ceremony pipeline alias (`AN[auto] BS[auto] CS TS[min:90] EX`) is `forge-auto`; `deepwiki` remains a deprecated alias that warns once and redirects (`src/skf-forger/SKILL.md`, `src/shared/references/pipeline-contracts.md`, `docs/forge-auto.md`) because the old name falsely promised the DeepWiki MCP, which the pipeline never calls. The first replacement, `autoforge`, was rejected: a GitHub namespace check found the 1,757-star `AutoForgeAI/autoforge` repo, and it breaks the `forge-<modifier>` family (`forge`, `forge-quick`, `forge-auto`) that pipeline alias names follow — check both before proposing a new alias. Wiring the DeepWiki MCP into the pipeline was declined at the same time because wiki staleness would make "verified" skills non-reproducible, and later closed outright as not planned in issue #425. The user confirmed the rename: "execute the full forge-auto rename now as one PR".
