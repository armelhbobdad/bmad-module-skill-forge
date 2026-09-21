---
created: "2026-04-08 00:09"
session: "8bcb9111-b354-4301-ab90-f1e2a73bbfdf"
source: claude-mem
source_table: both
source_ids: [4585, 4603, 4606, 4607, 4618]
---

# platform-codes.yaml is a locally patched upstream copy

`tools/cli/lib/platform-codes.yaml` began as a copy of BMAD-METHOD's `tools/installer/ide/platform-codes.yaml` and was then patched (see also validators-adapted-from-bmad-method, tilde-paths-in-legacy-targets and detection-marker-generic-skill-dirs). The critical patch: upstream gives both `codex` and `junie` `target_dir: .agents/skills`, which made the SKF installer write the same skills twice, double the manifest `ide_skills` entries, loop on clean/reinstall and break auto-detection for both, so SKF moved junie to `.junie/skills`; codex also lost the `~/.codex/prompts` legacy target, gained `detection_marker: .codex`, and every entry gained `skill_invocation_prefix`. The upstream file (checkout at `../BMAD-METHOD`) still has the collision and none of those keys, so re-copying it verbatim reintroduces all of these bugs. Every platform entry must keep a unique `installer.target_dir`; nothing under `test/` enforces it, so check with `grep -n 'target_dir:' tools/cli/lib/platform-codes.yaml | awk '{print $NF}' | sort | uniq -d` (must print nothing). None of this is written in the file's header or the changelog — the fix was squashed into the migration commit 6320b577.
