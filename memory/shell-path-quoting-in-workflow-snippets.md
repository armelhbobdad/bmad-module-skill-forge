---
created: "2026-04-13 17:32"
session: "a5591f15-f074-4f5f-b70e-8260eba1d5ef"
source: claude-mem
source_table: observations
source_ids: [6143, 6149, 6150, 6153]
---

# Shell path quoting in workflow shell snippets

Every shell command in an skf-* step or reference that interpolates a `{...}` path placeholder (`git -C "{workspace_repo_path}"`, `rm -rf "{temp_path}"`, `cd "{project-root}"`, `mkdir -p "{staging}"`) must double-quote the placeholder, because macOS home directories such as `/Users/First Last/` contain spaces and break unquoted shell (WSL2 sees the same). The canonical statement is the "Shell Path Quoting" paragraph at the top of `src/skf-create-skill/references/source-resolution-protocols.md`, but it is worded as applying to that document only and nothing in `CONTRIBUTING.md` states it repo-wide. The convention is applied unevenly: `grep -rnE '(git -C|rm -rf|cd|mkdir -p) \{[a-z_-]+\}' src/ --include='*.md'` still finds ~49 unquoted uses (for example `src/skf-audit-skill/references/init.md:205-212` and `src/skf-create-skill/references/sub/fetch-temporal.md:75`). When writing or editing any workflow shell snippet, quote every path placeholder and do not copy the unquoted forms as a template.
