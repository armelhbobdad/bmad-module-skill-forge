---
created: "2026-06-04 19:51"
session: "ec053a51-2187-4d28-8522-c8a36d1207aa"
source: claude-mem
source_table: observations
source_ids: [15472, 15478, 15481, 15483, 15484]
---

# Release scoping must inspect alias and contract removals

Commit subjects are not enough to choose `version_bump` for `.github/workflows/release.yaml`. The v1.9.0 to v2.0.0 break was the `onboard` pipeline alias going from deprecated-but-still-expanding to a HALT ("🚫 onboard has been removed. Use forge-auto instead") with its row gone from src/shared/references/pipeline-contracts.md, visible only by diffing those files against the previous tag; a `minor` dispatch chosen from the subjects was cancelled by the user: "I want to ship the next major release release @docs/_internal/RELEASING.md". Since #578 that diff is automated: `tools/covered-surfaces.js` compares schema enum values and properties under src/shared/scripts/schemas/, Ferris menu codes, pipeline aliases and workflow flags against the last stable tag, and `npm run changes:preview -- --bump <type>` and the release gate refuse a bump below what it and the change fragments require. Replayed over 33 stable releases, its hard group fires only for `onboard` and `write_failure`. It cannot see a break that exists only in step-file prose, such as update-skill flags that now halt: the fragment's author must type those `breaking`, and the preview's review list (halt reasons, error phases, changed flag text, flags that left every flag row) is where they show up.
