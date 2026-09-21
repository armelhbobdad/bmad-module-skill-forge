---
created: "2026-05-15 15:27"
session: "77c2e3d9-3742-4582-9b5e-94101963b3ee"
source: claude-mem
source_table: observations
source_ids: [9606, 9616, 9873, 9950]
---

# Edit local .claude/skills only when necessary, then /reload-plugins

The BMad builder skills under `.claude/skills/` (bmad-workflow-builder, bmad-agent-builder and the rest) are local and gitignored (`.gitignore:54` ignores `.claude`), so no commit, review or doc in this repo tracks edits to them. The user's standing rule: "Feel free to Self improve your internal workflows (in .claude/skills folder) ONLY IF IT IS NECESSARY (RUN /reload-plugins TO LOAD NEW UPDATED SKILLS)." Claude Code only picks up an edited skill after `/reload-plugins`; an edit without it silently keeps running the old version. The quality-analysis runs these skills drive (the ones used to elevate skf-* skills from Good to Excellent) write timestamped `.analysis/` folders into skill directories, which `.gitignore:67` (`**/.analysis`) keeps out of commits.
