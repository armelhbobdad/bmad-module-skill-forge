---
created: "2026-05-16 00:41"
session: "368f6026-a320-4e3c-ab70-9bedb28ba90c"
source: claude-mem
source_table: observations
source_ids: [9932, 9933]
---

# Minimal commits and PRs for multi-item work

When asked to address a tracking issue that bundles several workstreams — issue #325 covered six new `src/shared/scripts/skf-*.py` helpers, the `compute-score.py` argparse migration and subagent prompt tightening — the user wants the work landed as the fewest commits and PRs that stay coherent, grouped by root cause, not one commit or PR per workstream. User: "Can we address the issue #325? We should end up with a minimal commits and PRs. What do you think?" The same instruction ("we should end up with the minimal commits and PRs") is repeated for every improvement-queue batch, so it is the default for multi-item work in this repo; `CONTRIBUTING.md` only asks for "small focused PRs" and does not record this.
