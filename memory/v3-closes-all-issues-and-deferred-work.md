---
created: "2026-09-29 21:42"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# v3.0.0 closes every open issue and every deferred-work item

The user's decision, stated 2026-09-29: "we should clean everything with the v3 release." v3.0.0 ships only after every open GitHub issue (milestone v3.0.0, plan in tracking issue #556) and every still-valid item in `_bmad-output/implementation-artifacts/deferred-work.md` is fixed. A ledger item that is already fixed, obsolete or superseded is removed from the file with its reason, so the ledger ends empty; a triage rank such as "later" defers nothing past v3. The release is a major because of three changes already on main (the setup envelope lost `write_failure`; update-skill `--detect-only` and `--dry-run` halt on a flat skill; `--allow-workspace-drift` halts on gaps that need a provenance line), so any other fix that makes a flag or input halt or record a weaker outcome has to land before v3.0.0, or it would force a v4.
