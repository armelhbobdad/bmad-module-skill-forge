---
created: "2026-06-02 21:42"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14439, 14440, 14441]
---

# Collision check before naming a pipeline alias or command

Before shipping a new pipeline alias or command name, run an exact-name collision search on GitHub, npm, PyPI and the web, and keep the `forge-<modifier>` family shape (`forge`, `forge-quick`, `forge-auto`; aliases are recognized in src/skf-forger/SKILL.md and expanded from src/shared/references/pipeline-contracts.md). The zero-ceremony pipeline first shipped as `deepwiki`, collided with the DeepWiki MCP, and had to be renamed behind a one-time deprecation notice (docs/forge-auto.md § Migration, commit f0e99e46). The first replacement candidate, `autoforge`, was caught by this check — `AutoForgeAI/autoforge` (1,757 stars) is an exact match, and the prefix shape breaks the family — while `forge-auto`, `forge-go` and `forge-all` had only fuzzy hits, so `forge-auto` shipped. Nothing in CONTRIBUTING.md or docs/_internal/STABILITY.md records this step.
