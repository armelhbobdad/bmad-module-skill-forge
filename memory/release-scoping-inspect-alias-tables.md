---
created: "2026-06-04 19:51"
session: "ec053a51-2187-4d28-8522-c8a36d1207aa"
source: claude-mem
source_table: observations
source_ids: [15472, 15478, 15481, 15483, 15484]
---

# Release scoping must inspect alias and contract removals

`git log <last-tag>..HEAD` subjects are not enough to choose `version_bump` for `.github/workflows/release.yaml`: the v1.9.0 → v2.0.0 break was the `onboard` pipeline alias going from deprecated-but-still-expanding to a HALT ("🚫 onboard has been removed. Use forge-auto instead", src/skf-forger/SKILL.md:107-109) and its row vanishing from the alias table in src/shared/references/pipeline-contracts.md — visible only by diffing those files against the previous tag, never in commit subjects (no `feat!`/`fix!` or `BREAKING CHANGE` footer), and the generated CHANGELOG 2.0.0 block still shows no breaking marker. A `minor` dispatch (v1.10.0) chosen on that basis was cancelled by the user: "I want to ship the next major release release @docs/_internal/RELEASING.md". Before choosing `version_bump`, diff the forger alias table, pipeline-contracts.md, the JSON-schema enums under src/shared/scripts/schemas/ and STABILITY.md's covered surfaces against the last tag: a deprecated alias that still works is minor; an alias or enum value that now halts or is gone is major. RELEASING.md does not say this.
