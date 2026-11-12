---
created: "2026-10-07 13:18"
session: "a5de91ad-9e43-4a0e-8b07-235a1486d3dc"
---

# Untracked local tool folders in the pack-contents test

`test/test-pack-contents.js` (in `npm run test:install`, so in `npm test`, `npm run quality` and the `.husky/pre-commit` hook) packs the working tree with `npm pack --dry-run` and drops only the paths `git check-ignore` reports, so any untracked folder git does not ignore fails it. On 2026-10-07 Boost's `.boost/` failed every commit with `packed, but not a file the package may ship: .boost/hook-meta/meta.1216567788` and `husky - pre-commit script failed (code 1)`. A one-run override such as `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.excludesFile GIT_CONFIG_VALUE_0=<file>` (or `git -c`) gets a plain `npm run quality` through but not `git commit`. The hook runs `unset $(git rev-parse --local-env-vars) GIT_NAMESPACE`, which drops `GIT_CONFIG_COUNT` and `GIT_CONFIG_PARAMETERS`, so the override silently does nothing and the commit fails again after the full suite. What works is a line in `.git/info/exclude`, which linked worktrees share: `/.boost/` is there now, and a new local-only tool folder goes there too rather than into the tracked `.gitignore` or `.npmignore`.
