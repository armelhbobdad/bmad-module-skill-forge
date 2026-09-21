---
created: "2026-03-08 20:18"
session: "883a7c2c-6ff9-4c83-aa11-e66236b0ad67"
source: claude-mem
source_table: observations
source_ids: [638, 639, 640, 643]
---

# @clack/prompts is the CLI prompt library

The installer CLI (`tools/cli/lib/ui.js`, `tools/cli/lib/installer.js`, `tools/cli/commands/uninstall.js`) uses `@clack/prompts` (package.json:86) for prompts, spinners and intro/note/outro; inquirer and ora were removed in commit 1dd321eb and appear nowhere in the tree. The choice mirrors BMAD-METHOD, whose own 24-file migration to @clack/prompts was driven by inquirer's arrow-key navigation breaking on Windows — a platform SKF supports and CI-gates on every PR (CONTRIBUTING.md:21). Do not reintroduce inquirer or ora for a new prompt or spinner; the commit message records the migration but not this reason, and no doc in the repo does either.
