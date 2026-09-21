---
created: "2026-04-04 19:58"
session: "6fa45512-d599-4dbb-85f0-8a269d8b745e"
source: claude-mem
source_table: observations
source_ids: [4334, 4348, 4349, 4350]
---

# IDE mapping table must track platform-codes.yaml

`tools/cli/lib/installer.js` writes `config.yaml.ides` as installer IDE ids taken from `tools/cli/lib/platform-codes.yaml` (`claude-code`, `github-copilot`, `codex`, `cline`, ...), and every workflow that rebuilds CLAUDE.md / AGENTS.md / .cursorrules managed sections — export-skill steps 1 and 4, `src/skf-drop-skill/references/execute.md` §3, `src/skf-rename-skill/references/execute.md` — resolves them through the "IDE → Context File Mapping" table in `src/skf-export-skill/assets/managed-section-format.md`. That table is a hand-maintained copy of platform-codes.yaml (23 IDEs plus `other`, each with a context file and a skill root); nothing in `npm test` checks the two files agree. Originally export-skill mapped only 3 of the 8 installer IDEs and drop/rename treated raw `ides` values as platform keys, so managed sections were silently not rebuilt at all. Today an IDE missing from the table falls back to AGENTS.md + `.agents/skills/` with only a warning ("Unknown IDE '{value}' in config.yaml — defaulting to ..."), so a wrong skill root is written without any error. Adding an IDE to platform-codes.yaml therefore requires adding its row to that table in the same change.
