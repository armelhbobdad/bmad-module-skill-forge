---
created: "2026-04-09 17:25"
session: "b21d51c9-99b8-45d1-8bed-e9c02c44bcd0"
source: claude-mem
source_table: both
source_ids: [5053, 5077, 6180, 6184]
---

# Cross-platform requirement for every script and embedded snippet under src/

Owner rule: "keep in mind that, SKF should perfectly work on linux/macos/windows." Every Python helper in `src/shared/scripts/` and every shell/Python snippet embedded in a workflow markdown must behave identically on all three: no `subprocess` `shell=True` with POSIX tools, no hardcoded `/tmp`, `/usr/` or literal `~` paths, no Unix-socket assumptions, symlinks only through `skf-atomic-write.py` (`_create_symlink_or_junction`, which falls back to `mklink /J` when Windows symlink privilege is missing), atomic writes via `os.replace()`, and `encoding="utf-8"` on every `read_text`/`write_text`/`open` — Windows defaults to cp1252, and four unencoded calls in `skf-rebuild-managed-sections.py` once broke on non-ASCII CLAUDE.md/AGENTS.md content. create-skill's `src/skf-create-skill/references/source-resolution-protocols.md` skips `git checkout FETCH_HEAD` when `HEAD == FETCH_HEAD` to avoid Windows file-handle locks; update-skill's copy of those clone steps (`references/remote-source-resolution.md`) was deleted in commit 72398eb3 (#511). Its replacement, `src/shared/scripts/skf-source-tree.py`, shows the current Windows shape for git work: a private tree per run instead of a checkout of the shared clone, child output in temporary files rather than pipes, `taskkill /T /F` on a time limit (on POSIX, `_stop` sends SIGTERM to the process group first so git removes its lock files), and tree removal through extended-length paths (`_long_path`, `_rmtree`) past MAX_PATH. CI runs `ubuntu-latest` + `windows-latest` only (quality.yaml), macOS is not gated, and CONTRIBUTING.md states platform support without any of these coding rules, so a review of new scripts has to apply them by hand.
