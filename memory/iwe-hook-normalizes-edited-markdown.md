---
created: "2026-09-28 11:40"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# IWE PostToolUse hook rewrites any project markdown edited with Edit or Write

Every `.md` file in this repository is a document of the IWE workspace, so editing one with the Edit or Write tool fires IWE's PostToolUse hook, which reports "`CONTRIBUTING` was written outside the CLI, so it landed unnormalized. It has been rewritten into this store's canonical form" and rewrites the whole file, not just the edited line. On `CONTRIBUTING.md` it broke two links (`.github/` became `.github.md`, `src/knowledge/` became `src/knowledge.md`), dropped the code spans inside link text, turned `_why_` into `*why*`, put blank lines between list items and changed "`bash" to "` bash" — a one-line edit became a 29-line diff. The hook's advice to use `iwe update -k <key>` is for memory notes only; for project markdown (`src/`, `docs/`, root files) restore the file with `git checkout -- <file>` and make the change with a shell edit (a Python or sed replacement run through Bash), which does not fire the hook. YAML and JSON files are left alone. Always check `git diff --stat` after touching markdown. The same normalization run repo-wide is why `iwe normalize` must never be run here: its dry run would rewrite 248 of the 252 project markdown files.
