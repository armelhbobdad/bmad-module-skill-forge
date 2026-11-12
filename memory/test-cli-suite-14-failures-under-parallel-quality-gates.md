---
created: "2026-10-03 04:16"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# test:cli Suite 14 failures under parallel quality gates

Running `npm run quality` on several worktree branches at once can make `npm run test:cli` exit 1 in `test/test-cli-integration.js` "Test Suite 14: The CLI Prints the Tool Report, Then the Update Notice", before pytest runs and with no failing assertion in the log. On 2026-10-03, with five branches in parallel, two stopped there while three passed the same suite; re-run one at a time, both passed (14,106 and 14,059 tests). Suite 14 spawns `tools/cli/skf-cli.js update` and `status` with a 120-second `spawnSync` timeout, and the tool report's probes stop after `TIMEOUT_MS` (3000 ms, `tools/cli/lib/version-check.js`), so heavy parallel load is the likely cause, though not proven. Run full gates one or two at a time, and re-run a branch alone before treating a Suite 14 stop as a code failure.
