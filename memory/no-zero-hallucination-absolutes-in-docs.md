---
created: "2026-04-13 16:41"
session: "a5591f15-f074-4f5f-b70e-8260eba1d5ef"
source: claude-mem
source_table: observations
source_ids: [6113, 6115, 6117, 6134]
---

# No zero-hallucination absolutes in user-facing docs

User-facing docs (README.md, docs/, CHANGELOG.md, the website) must not promise "zero hallucination" or say SKF makes agents "stop hallucinating"; the claim is stated as citation-based instead — README.md's tagline is "Every instruction links back to its upstream — a specific `file:line` at a pinned commit", its CTA is "fixes your agent's API guesses", and docs/concepts.md's Provenance section says "If SKF can't point to a source, it doesn't include the instruction." The v1.0 editorial pass replaced every absolute in those files and renamed the concepts section (then "Every Claim Cites a Source", now "Provenance") because an absolute conflicts with docs/verifying-a-skill.md's framing "Perfection is suspicious. Visible fallibility is trustworthy." The engineering principle keeps its internal name — src/knowledge/zero-hallucination.md, the `src/module.yaml` subheader "Zero hallucination tolerance" and the Ferris persona in src/skf-forger/SKILL.md — so do not copy that wording from src/ into public docs. Nothing in CONTRIBUTING.md or docs/_internal/ records this rule.
