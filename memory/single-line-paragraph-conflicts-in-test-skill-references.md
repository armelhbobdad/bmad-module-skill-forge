---
created: "2026-11-09 11:56"
session: "77252030-8c80-4285-b88e-c15f43930eb7"
---

# Single-line paragraph conflicts in Test Skill references

Test Skill's reference files keep each paragraph on one line: `src/skf-test-skill/references/inventory-contract.md` line 33 is 19,215 characters, and `scoring-rules.md`, `coverage-check-branches.md`, `source-access-protocol.md` and `signature-comparison-rules.md` each hold a line of 3,000 to 5,200 characters. Two branches that edit different sentences of one paragraph therefore always stop with `CONFLICT (content)` on rebase. On 2026-11-09, stacking parallel fix lanes hit this in `source-access-protocol.md` and in `signature-comparison-rules.md` (the split-body paragraph under "Reading a form", and "Overload sets"). A sentence-level 3-way merge resolved most of it; where both sides inserted after the same sentence, the order came from the `.index(...) < .index(...)` asserts in `test/test-skf-test-skill-signature-rules.py`. Plan parallel lanes so each long paragraph has one editor, or expect to merge by sentence and rerun the tests that pin sentence order.
