---
created: "2026-04-11 15:54"
session: "d7c34731-42f9-40c1-ad3a-492ee7005589"
source: claude-mem
source_table: session_summaries
source_ids: [1640]
---

# Docs-only update mode bumps version without a version directory

In `skf-update-skill` the version-directory logic is keyed on 'a source version detected during step 3': `merge.md` §6b creates `{skill_group}/{new_version}/` only when that detected version differs from metadata, while `write.md` §2 otherwise 'increment[s] patch version' unless `update_mode == "gap-driven"`. Gap-driven mode was fixed for this mismatch (#121, commit c3c7e53c), but the docs-only path (`re-extract.md` §1: re-fetch `doc_urls`, skip source extraction, no source version set) still has the same shape: metadata gets a patch bump, the files stay in the old version directory, and `write.md` §5b's `skf-update-active-symlink.py update --version {version}` then halts with `missing-target` / `halted-for-write-failure`. It was left out of scope when #121 was fixed. If touching docs-only updates, gate the bump on mode the way gap-driven does or create the new directory in §6b.
