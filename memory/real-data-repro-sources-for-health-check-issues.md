---
created: "2026-10-07 23:39"
session: "a5de91ad-9e43-4a0e-8b07-235a1486d3dc"
---

# Real-data repro sources for health-check issues

Health-check issues filed from oh-my-skills runs can be reproduced on real data instead of fixtures. `~/Projects/OSS/oh-my-skills/forge-data/<skill>/<version>/` holds each run's `provenance-map.json`, `extraction-snapshot.json`, `test-findings-*.json`, `*-result-latest.json` and `drift-report-*.md` files (oms-cognee has 0.5.8, 1.0.0 and 1.6.2 plus `skill-brief.yaml`), and the published skill sits at `skills/<skill>/<version>/<skill>/` in that repo. The matching sources are the SKF workspace clones under `~/.skf/workspace/repos/<host>/<owner>/<repo>` (cognee 1.0.0 is `3c048aa4`, 1.6.2 is `ba3631f2`). Export a version with `git archive <sha> | tar -x -C <scratch>` rather than checking it out, so the cached clone stays untouched, and run helpers on copies of the map files. The 2026-10 fixes (#678, #680 to #687) were checked this way, and real data caught what fixtures missed: cognee's `Task` is declared in two files, and 25 of 26 names resolved where 24 were predicted.
