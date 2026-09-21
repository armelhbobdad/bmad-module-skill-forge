---
created: "2026-03-20 00:42"
session: "2056a833-de46-4e4b-ac4e-4e77f3d7f8fd"
source: claude-mem
source_table: observations
source_ids: [1913, 1914, 1920, 1921]
---

# README audience and jargon rule

README.md is written for a first-time visitor who has never heard of BMad or agent skills: above the fold it leads with the problem and a plain-English Before/After (`## The Problem`, `## Before vs After`), and undefined jargon (AST-verified, provenance, confidence tiers, forge tiers, agentskills.io-compliant) stays out of the first screen. Term definitions belong in docs/concepts.md (linked from README as 'Seven load-bearing terms'), not in the README. The rule came from BMAD community feedback the user relayed: "tell your Claude to regenerate the readme free of jargon, and focusing above the fold on converting a 'wtf is this?' into 'ok, I understand where and why I might want this in my life'". Nothing in CONTRIBUTING.md records it, so a README rework can silently regress to the insider version.
