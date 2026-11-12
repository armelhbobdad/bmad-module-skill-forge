---
created: "2026-11-09 14:10"
session: "77252030-8c80-4285-b88e-c15f43930eb7"
---

# Cross-lane test breaks after stacking parallel lanes

Fix lanes cut from one base, each green on its own targeted tests, broke each other once stacked on 2026-11-09, with no textual conflict to warn of it. #1022's new test read `json.loads(proc.stdout)["files"]` from `score-signatures.py plan --output` after #1018 made that stdout a summary, and tests from #1029 and #997 failed with `KeyError: 'inventory'` once #1040 moved `validate-inventory.py --output`'s inventory into the file. #1033's new refusal also rejected `inventory-contract.md`'s own JSON example after #1035 added a split-body mismatch to it. Only the full `npm test` on the stacked head caught them (`3 failed, 18000 passed`, `npm-test-exit=1`). The commands that, given `--output`, print only a summary are listed in `SUMMARIZED_COMMANDS` and `SUMMARIZED_SCRIPTS` in `test/test-skf-test-skill-provenance-paths.py`, so a test reading JSON from such a command's stdout breaks once a sibling lane turns it into a summary. Stack each lane on the previous one, run the full suite on that head before pushing, and fold each fix into the commit that caused the break.
