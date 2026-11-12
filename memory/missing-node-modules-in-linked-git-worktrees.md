---
created: "2026-11-03 15:49"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Missing node_modules in linked git worktrees

A `git worktree add` checkout (sibling lanes such as `/home/armel/Projects/OSS/skf-wt-*` or the Agent tool's `.claude/worktrees/agent-*`) has no `node_modules`, so `node tools/changes.js check` (`npm run validate:changes`) and `changes.js lint` crash there with `Cannot find module 'semver'` (tools/changes.js:120-121 require `semver` and `yaml`). `tools/validate-no-em-dash.js` needs only Node builtins and still passes, which can hide that the other checks never ran. Borrowing the main checkout's modules read only works: `NODE_PATH=/home/armel/Projects/OSS/bmad-module-skill-forge/node_modules node tools/changes.js check` reported `399 change fragment(s) valid`, and markdownlint ran the same way. Prettier does not: `prettier.config.mjs` loads `prettier-plugin-packagejson`, which prettier resolves from the config file's folder and not through `NODE_PATH`, so it fails with `[error] Cannot find package 'prettier-plugin-packagejson' imported from /home/armel/Projects/OSS/skf-wt-pr7/noop.js`; run prettier from the main checkout on the file's text. For a full `npm test` run `npm ci` in the worktree first (and `npm ci --prefix website` before `docs:build`), and put the chosen route in every worktree agent's brief, since no pre-commit hook runs there to catch a skipped gate.
