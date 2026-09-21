---
created: "2026-05-16 14:41"
session: "1e2334fb-85a5-467d-a2f4-9f77df25bf8f"
source: claude-mem
source_table: session_summaries
source_ids: [2862, 2863, 2864, 2865, 2866]
---

# Layer 2 candidate refresh of 2026-05 never reached ROADMAP.md

`ROADMAP.md` "Layer 2 Tenant Candidates" is dated "as of 2026-04-19" (commit bca07a2f, still the file's last commit at v2.1.0) and never received the 2026-05-16 candidate refresh, which was written only under the gitignored `_bmad-output/planning-artifacts/research/` tree together with an unapplied ROADMAP edit block, so it is absent from the repo. That refresh found graphify had repositioned from an embeddable tree-sitter graph library into a peer AI-coding-assistant skill (`graphify install --platform <assistant>`, its own `/graphify` command), so "SKF wraps graphify" now has UX overlap to design around, while consuming `graphify-out/graph.json` as a tenant artifact still works; Leiden became an optional extra gated to Python < 3.13. No candidate cleared the Tool Maturity Gate, so Layer 0 (`~/.skf/workspace/`, `src/skf-create-skill/references/source-resolution-protocols.md`) remains the only shippable layer. Re-evaluation is due when a candidate ships a stable ≥1.0 release, publishes a versioned-schema commitment, or in Q4 2026 — whichever comes first — or earlier on Layer 1 usage signals (5+ cached repos, disk complaints). Anyone touching the roadmap or Layer 2 should start from these findings rather than re-research from the April table.
