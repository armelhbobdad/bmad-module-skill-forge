---
created: "2026-05-15 17:45"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9713, 9715, 9716]
---

# Native Windows junction support in the skf-update-skill active-link helper

Until issue #735, `src/shared/scripts/skf-update-active-symlink.py` (the helper `skf-update-skill/references/write.md` §8 and §8a use on `{skill_group}/active`) exited 1 on native Windows with `error: native Windows symlinks require admin/developer mode; use WSL2 to run update-skill`. Commit 2d23a66f (PR #756, merged 2026-10-13) removed that check: the helper now flips through `skf-atomic-write.py`'s `replace_link`, the `flip-link` code that falls back to an NTFS junction via `mklink /J`, and reads a junction back as the version folder it resolves to. On Windows the flip removes the old link before the rename, so it is not atomic and a reader can briefly find no `active`. `test/test-skf-update-active-symlink.py` skips only its `POSIX_ONLY` classes on Windows, and `TestNativeWindows` exercises real junctions on CI's `windows-latest` leg. Manual fixes that repoint `active` (Drop Skill `execute.md` §4, `docs/workflows.md`, the helper's `mismatch` halt message) name `uv run {atomicWriteHelper} flip-link --link ... --target ...`, not `ln -sfn`, which Git Bash without symlink rights turns into a folder copy. The junction claim in `CONTRIBUTING.md:21` and `docs/getting-started.md:218` now holds for Update Skill too, so a WSL2 requirement or an `ln -sfn` fix is stale.
