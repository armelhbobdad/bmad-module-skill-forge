---
created: "2026-04-21 13:29"
session: "9713e66f-7f75-4067-b7c5-b6281fa6587a"
source: claude-mem
source_table: observations
source_ids: [6813, 6815, 6816, 6819, 36987]
---

# Entire CLI required by the commit-msg hook

`.husky/commit-msg` runs `entire hooks git commit-msg "$1" || exit 1`, and `entire` (the Entire CLI, wired in b4613239 with `.entire/settings.json`) is a local dev tool that README.md and CONTRIBUTING.md never list as a prerequisite. Anywhere it is not on PATH — CI, a fresh clone, a sandboxed or `env -i` shell — every `git commit` fails with `.husky/commit-msg: 3: entire: not found` (exit 1); reproduce with `env -i PATH=/usr/bin:/bin sh .husky/commit-msg /tmp/msg`. Only commit-msg blocks: post-commit, prepare-commit-msg and pre-push end in `|| true`. `.github/workflows/release.yaml` sets job-level `HUSKY: "0"` (the opt-out `.husky/_/h` checks) rather than editing hooks, because `npm ci` re-runs `prepare: husky || exit 0` and reinstalls them; any new workflow that commits from CI needs the same env line, and locally `HUSKY=0 git commit` or installing Entire are the only ways past it. The maintainer considers this an open contributor bottleneck: "one of the botlleneck is that every contributors need to install entire on their machine too. Am I right?"
