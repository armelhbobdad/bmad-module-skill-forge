---
created: "2026-03-14 18:22"
session: "399dba32-15e7-4ca7-b421-c491359347a7"
source: claude-mem
source_table: session_summaries
source_ids: [427, 428, 429, 430]
---

# npx tessl's -y flag retired with skf-tessl-review.py

No step file runs tessl itself any more: commit 4fa24400 (#513) removed `timeout 120s npx --no-install -y tessl skill review {skillDir}` from `src/skf-test-skill/references/external-validators.md` and `timeout 120s npx -y tessl skill review <staging-skill-dir>` from `src/skf-create-skill/references/validate.md`, because Tessl had replaced `tessl skill review` with Tessl Review and the old call made create-skill report an installed tool as unavailable and test-skill record a parse failure. Every tessl call now lives in `src/shared/scripts/skf-tessl-review.py` (`submit`, `collect`, `parse`), which both steps resolve through `tesslReviewProbeOrder`. Its `resolve_tessl()` takes `tessl` from PATH, else `npx --no-install tessl` from the npx cache, both through the CWD-shim guard `_resolve_outside_cwd`, so it never passes `-y` and never installs tessl (an uncached tessl ends as `not-installed`); `submit_review` and `collect_review` run every tessl call in a `tempfile.TemporaryDirectory(prefix="skf-tessl-")` working folder, and `_kill_tree` kills the tessl process tree when `PROBE_TIMEOUT_SEC`, `SUBMIT_TIMEOUT_SEC` or `VIEW_TIMEOUT_SEC` runs out. The trap `-y` was added for (commit 9bda9034: "Both workflows use npx -y to auto-accept install prompts") still applies to any other npx call in a step: without `-y`, npx stops on its package-install confirmation prompt when the package is not cached, and the step hangs with no error text. So probe first with `timeout 15s npx --no-install <package> -h`, as external-validators.md §2 does for skill-check, or pass `-y`; never put a tessl command back into step prose, extend the helper instead.
