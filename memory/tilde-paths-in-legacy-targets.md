---
created: "2026-04-08 00:37"
session: "7cba3f62-fa07-467b-9eac-6fc6674d6c0b"
source: claude-mem
source_table: both
source_ids: [4600, 4606]
---

# Tilde paths in legacy_targets never expand

`cleanLegacyTargets()` in `tools/cli/lib/ide-skills.js` (line 143) resolves every `legacy_targets` entry from `tools/cli/lib/platform-codes.yaml` with `path.join(projectDir, legacyDir)`. Node's `path.join` treats `~` as a literal directory name, so an entry such as `~/.codex/prompts` becomes `{projectDir}/~/.codex/prompts`, `fs.pathExists` returns false and the legacy cleanup silently no-ops with no error or warning. This was hit when the Codex entry carried `~/.codex/prompts`; the fix was to drop the tilde entry and keep only the project-relative `.codex/prompts`. `legacy_targets` may only list project-relative paths; a home-directory target needs the cleanup code to expand `~` (`os.homedir()`) first — nothing in the yaml header comment or the code guards against this.
