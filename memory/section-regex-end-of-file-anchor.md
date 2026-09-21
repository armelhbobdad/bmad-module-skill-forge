---
created: "2026-05-26 21:39"
session: "7eb2c7e5-13e7-4b06-a9aa-f1bb59adf77f"
source: claude-mem
source_table: observations
source_ids: [13643]
---

# SKILL.md section-slicing regex needs a \\Z end-of-file anchor

Structural tests that slice one section out of a SKILL.md with `re.search(r"## Heading\b(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)` return no match when that section is the last one in the file, because there is no following `## ` heading for the lookahead to find. `test/test-skf-per-pipeline-thresholds.py` failed this way on the `assert m, "Forger SKILL.md must have a Pipeline Mode section"` fixture while extracting `## Pipeline Mode` from `src/skf-forger/SKILL.md`. The fix is the alternation `(?=^## |\Z)`, now used by all four section fixtures in that file and in `test/test-skf-evidence-report-fallback.py`; copy that form for any new section-extraction regex.
