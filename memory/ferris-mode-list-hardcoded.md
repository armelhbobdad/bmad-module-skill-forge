---
created: "2026-04-08 00:25"
session: "8bcb9111-b354-4301-ab90-f1e2a73bbfdf"
source: claude-mem
source_table: observations
source_ids: [4591, 4594, 4599]
---

# Ferris mode list hardcoded in five files

Ferris has five workflow-bound modes — Architect, Surgeon, Audit, Delivery and Management (RS rename-skill, DS drop-skill and the campaign) — and the count and list are repeated by hand, with no generator or validator, in `src/skf-forger/SKILL.md:14`, `src/skf-forger/bmad-skill-manifest.yaml:8` (`identity:`), `src/README.md:35`, `docs/agents.md:31-37` (Workflow-Driven Modes table) and `docs/architecture.md:66-74` (Ferris Operating Modes table); `docs/workflows.md` additionally names the mode per workflow (`**Agent:** Ferris (Management mode)` at lines 231, 249, 265) and in its categories table at line 331. When Management was added, most copies still said "four modes" until a docs audit in April 2026 caught it, and Ferris reads its own SKILL.md at activation, so a stale copy there misdescribes the agent to itself. Adding, removing or renaming a mode means editing every one of these places; `grep -rn 'five modes\|Management mode' src docs` finds them all.
