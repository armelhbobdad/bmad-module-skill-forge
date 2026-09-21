---
created: "2026-04-25 05:15"
session: "54440a56-2192-43ea-a4b6-c161b345b4cd"
source: claude-mem
source_table: session_summaries
source_ids: [2251, 2252, 2291, 2292, 2430]
---

# feat: commits on @internal surfaces still bump minor

docs/\_internal/STABILITY.md's "@internal — Not Covered by SemVer" section lists tools/cli/lib/*, src/skf-*/references/, src/knowledge/ and the docs tooling as `@internal` — changes there "may land in any release — patch, minor, or major" — but that clause defines what is not a breaking change, not which `version_bump` to pick. Releases 1.1.0, 1.2.0 and 1.3.0 were cut as minor, not patch, because their `feat:` commits added user-observable workflow behaviour (update-skill major-version scope reconciliation; the `SKF_SETUP_RESULT_JSON` envelope and `--require-tier`; quick-skill `--batch`/`--fail-fast` and the headless event contract), and the user confirmed "Confirm version_bump=minor (→ 1.1.0)" for the first of them. When scoping a cut of `.github/workflows/release.yaml`, the conventional-commit type plus observable behaviour decides `version_bump`; the @internal classification never downgrades a `feat:` to patch. Neither RELEASING.md nor CONTRIBUTING.md states this.
