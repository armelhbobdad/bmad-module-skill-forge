---
created: "2026-05-15 17:45"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9713, 9715, 9716]
---

# skf-update-skill active symlink helper is POSIX-only

`src/shared/scripts/skf-update-active-symlink.py`, the helper `skf-update-skill/references/write.md` §5b/§6 uses to flip and verify `{skill_group}/active`, refuses to run on Windows: `main()` exits 1 with `error: native Windows symlinks require admin/developer mode; use WSL2 to run update-skill` (line ~303), and `test/test-skf-update-active-symlink.py` is skipped wholesale on `win`. The older `skf-atomic-write.py flip-link` (used by quick-skill, create-skill, create-stack-skill and rename-skill) instead falls back to an NTFS junction via `mklink /J`. So the public claim in `CONTRIBUTING.md:21` and `docs/getting-started.md:171` that SKF 'transparently falls back to NTFS junctions' holds for forging but not for `skf-update-skill`, which halts at the active-symlink step for a native-Windows user. Windows-support work must either port the junction fallback into the update helper or document the WSL2 requirement publicly.
