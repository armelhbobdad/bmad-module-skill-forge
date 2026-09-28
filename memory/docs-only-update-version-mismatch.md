---
created: "2026-04-11 15:54"
session: "d7c34731-42f9-40c1-ad3a-492ee7005589"
source: claude-mem
source_table: session_summaries
source_ids: [1640]
---

# Docs-only update version mismatch fixed by a version folder per update

Before commit 956a850e (Refs #511), only gap-driven `skf-update-skill` runs kept version and folder in step (#121, commit c3c7e53c): docs-only and plain patch-bump updates wrote a new `version` into metadata.json while their files stayed in the previous version's folders, so `references/write.md` §5b's `skf-update-active-symlink.py update --version` halted with `missing-target` / `halted-for-write-failure`. Now `references/merge.md` §6b chooses `{new_version}` once, before SKILL.md is written, in normal, degraded and docs-only modes alike (`{source_version_detected}` when `references/init.md` §6c found a higher source version, else the next patch version), stages a copy of `{skill_package}` with `skf-atomic-write.py stage-dir`, publishes it as `{skill_group}/{new_version}/` with `commit-dir`, creates `{forge_data_folder}/{skill_name}/{new_version}/` with copies of `provenance-map.json`, `evidence-report.md` and `extraction-rules.yaml`, and rebinds `{skill_package}` and `{forge_version}`; `write.md` §2 then sets `version` to exactly `{new_version}`. Gap-driven repairs still keep their version and write in place, and `--detect-only` and `--dry-run` never reach §6b. Merge never overwrites an existing version folder (`halted-for-write-failure`, `error.phase` `merge:new-version-folder`) and removes what it created when a step of the copy fails. Because only export-skill advances the export manifest, `references/init.md` §1's manifest-lag guard updates the version the `active` link names, so a second update builds on the first instead of stopping at its folder. Change version selection in merge.md §6b and write.md §2 together; `test/test-skf-update-version-folder.py` pins that prose and runs merge's commands against the real helpers.
