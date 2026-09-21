---
created: "2026-04-21 04:58"
session: "06631415-2932-4e5d-bdb1-79ab4e9bb958"
source: claude-mem
source_table: observations
source_ids: [6678, 6684, 13054, 13058]
---

# deferred-work.md technical-debt ledger in gitignored _bmad-output

Code-review findings triaged as 'defer' are appended, per story under date-stamped `## Deferred from: code review of <story> (<date>)` headings, to `_bmad-output/implementation-artifacts/deferred-work.md` (entries from 2026-04-21 through 2026-05-26 as of v2.1.0; each item gives file path, line, description and deferral rationale). `_bmad-output/` is gitignored (`.gitignore:44`), so the ledger and the story artifacts exist only on the maintainer's machine and never on a fresh clone — yet `docs/_internal/RELEASING.md` (the tag-before-publish ordering paragraph) and `release-audits/v1.0.0-launch-audit.md` (nine table rows) link to it as though it were tracked, so those links dangle for everyone else. Where the ledger is available, read it before a new review re-discovers a known deferred issue (e.g. the 'Create and push tag pushes the git tag BEFORE Publish to npm' hardening item); in PRs, do not cite its section names as public references (`CONTRIBUTING.md` already bans `_bmad-output/` IDs in PR bodies).
