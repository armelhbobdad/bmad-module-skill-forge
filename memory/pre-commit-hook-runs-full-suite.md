---
created: "2026-05-18 17:52"
session: "900827df-c0f7-4954-b899-977f414b6435"
source: claude-mem
source_table: observations
source_ids: [10105, 10291, 14577]
---

# Pre-commit hook runs the full npm test suite

`.husky/pre-commit` runs `npx --no-install lint-staged`, unsets git's repository variables, then `npm test`: `npm run quality` minus `docs:validate-drift`, in another order, with about 18,000 pytest tests via `uv`. Alone it takes 13 to 19 minutes (`17804 passed, 10 skipped, 78 warnings in 791.34s (0:13:11)`) and 20 to 40 beside another full suite, so a silent `git commit` is working, not hung, and the maintainer's "Run npm run quality before each commit" doubles that. It passes the Bash tool's cap (`Command did not complete within its 600s timeout and was moved to the background`), so commit with run_in_background and an exit marker (`git commit -F msg > log 2>&1; echo "commit exit=$?" >> log`). Wait for the notification, not truncated hook output, and read the pytest summary before pushing; `npm test` chains its steps with `&&` and runs `lint` after `test:python`, so a lint error surfaces only after a full pytest pass. CONTRIBUTING.md item 4 says the hook runs "The full `npm test` suite" and line 158 says "Do not `git commit --no-verify`"; the one disclosed bypass (c8ace137, #427) was never requested, so never use `--no-verify` silently or without an equivalent green run.
