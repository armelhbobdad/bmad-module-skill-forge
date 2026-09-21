---
created: "2026-03-26 00:55"
session: "39ca4974-63db-4263-bd83-7692ad34d5a9"
source: claude-mem
source_table: observations
source_ids: [2440]
---

# Verify Stack name chosen to avoid BMM's architecture command

The stack-verification skill is `skf-verify-stack`, menu code `VS`, display name "Verify Stack" (src/module-help.csv:12, docs/workflows.md "Verify Stack (VS)") and deliberately not "Verify Architecture". The user chose it: "I prefer [VS] Verify Stack. It will verify stack against input files (PRD.md, Architecture.md). Verify Architecture can conflict with BMM existing command." BMM owns the architecture verb (its `bmad-architecture` skill creates, updates and validates the architecture document), so do not rename VS, add a "verify architecture" alias, or describe it that way in docs/ or Ferris's menu; what VS verifies is the stack of generated skills against the architecture and PRD inputs, and the architecture document itself is the job of `skf-refine-architecture` (RA).
