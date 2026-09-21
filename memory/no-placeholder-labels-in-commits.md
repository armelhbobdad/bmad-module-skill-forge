---
created: "2026-05-07 12:17"
session: "19c8b8e5-5ac2-4935-94db-f827a263a164"
source: claude-mem
source_table: both
source_ids: [9204]
---

# Placeholder labels like "PR A" banned in commit and PR text

Commit messages, PR titles and PR bodies name the change by what it does — conventional-commit prefix + scope + the fix, as `CONTRIBUTING.md` § Workflow for Changes shows — never by a planning placeholder such as "PR A", "PR B", "PR D2" or "D1-1"/"D3-2" carried over from a planning conversation. The user's instruction on seeing such drafts: "I agree. Please avoid to use terms like "PR A" in commit message and PR." `CONTRIBUTING.md` covers prefixes, scopes and `Fixes #NNN` but says nothing about this, so nothing in the repo catches it; git history is clean of such labels and should stay that way.
