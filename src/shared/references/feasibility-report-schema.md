# Feasibility Report Schema

**Purpose:** Canonical contract shared between `skf-verify-stack` (producer) and the skills that read its report, `skf-refine-architecture` and `skf-create-stack-skill` (consumers). Any change here must be applied to the producer and every consumer in lockstep.

## Filename

```
{forge_data_folder}/feasibility-report-{project_slug}-{YYYYMMDD-HHmmss}.md
```

`{project_slug}` is `project_name` slugified by one rule: NFKD-decompose it and drop the combining marks (so `Café` gives `cafe`), drop any letter or digit that has no ASCII form, lowercase the rest, turn every run of other characters (spaces, punctuation, symbols) into one hyphen, and trim hyphens from both ends. A name that leaves nothing, an empty one included, gets the slug `project`. A stable `feasibility-report-{project_slug}-latest.md` copy (not symlink) is written next to the timestamped file for pipeline consumers.

`skf-validate-feasibility-report.py` (in `_bmad/skf/shared/scripts/`, or `src/shared/scripts/` in a dev checkout) holds the slug rule, so no skill derives the file name by hand. `--locate {forge_data_folder} --project-name "{project_name}"` applies the rule, reads only the `-latest` copy (a timestamped file can be a halted run's partial report), and returns `projectSlug`, `path`, `schemaVersion`, `overallVerdict`, `pairVerdicts` (from the canonical table under `## Integration Verdicts`) and `unknownTokens`. It exits 0 with `status: "ok"`, or with `status: "not-found"` when the project has no `-latest` report. It exits 1 when the report's `schemaVersion` is not `"1.0"`, its canonical table is missing or there twice (`duplicateVerdictTableLine` gives the second one's line), or a verdict token is unknown. It exits 2 when the report cannot be read, and on a usage error such as a missing `--project-name` or an empty folder, which prints no JSON.

## Frontmatter (required)

```yaml
---
schemaVersion: "1.0"
reportType: feasibility
projectName: "{project_name}"
projectSlug: "{project_slug}"
generatedAt: "{ISO-8601 UTC}"
generatedBy: skf-verify-stack
overallVerdict: "FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE"
coveragePercentage: <0..100 integer>
pairsVerified: <non-negative integer>
pairsPlausible: <non-negative integer>
pairsRisky: <non-negative integer>
pairsBlocked: <non-negative integer>
recommendationCount: <non-negative integer>
prdAvailable: <true|false>
---
```

**Unknown `schemaVersion` MUST fail loudly in consumers — never silently proceed.** Consumers check `schemaVersion == "1.0"` and emit an explicit error if mismatched.

## Per-pair verdict tokens (case-sensitive)

Exactly one of:

| Token | Meaning | Required evidence |
|---|---|---|
| `Verified` | Every compatibility check passes, and at least one of the two skills cites the other literally | Documentation cross-reference (Check 4) MUST pass with a literal substring/name citation in at least one direction; language + protocol + type checks all pass |
| `Plausible` | Every check passes except the documentation cross-reference: neither skill cites the other literally | Language + protocol + type checks pass; Check 4 weak or missing (no literal citation) |
| `Risky` | At least one check produced incompatibility that a workaround may resolve | The language, protocol or type check fails (a missing Check 4 citation caps at `Plausible` instead); workaround cited in recommendation |
| `Blocked` | Fundamental incompatibility that cannot be worked around | Language mismatch, protocol mismatch with no bridge, or type mismatch with no adapter |

## Overall verdict tokens (case-sensitive)

Exactly one of `FEASIBLE`, `CONDITIONALLY_FEASIBLE`, `NOT_FEASIBLE`.

- `FEASIBLE`: every live technology is Covered (100% coverage; a technology marked Replaced is not live), every integration pair is `Verified`, at least one integration pair exists when there are two or more live technologies, and, when the requirements pass ran, every requirement is Fulfilled.
- `NOT_FEASIBLE`: any `Blocked` pair, or zero coverage.
- `CONDITIONALLY_FEASIBLE`: everything else. This includes a run that found no integration pair across two or more live technologies: those integrations were never checked, so they are not known to be compatible.

## Body section headings (required, in order)

```markdown
## Executive Summary
## Coverage Analysis
## Integration Verdicts
## Recommendations
## Evidence Sources
```

Consumers read the pair table under `## Integration Verdicts` through `--locate` (see Filename). The table header is fixed:

```markdown
| lib_a | lib_b | verdict | rationale |
```

Only this table carries the per-pair verdicts, and the report holds it exactly once. `--locate` fails on a report with a second one (a filled table appended below the report template's empty one, say), skips any table in fenced code or an HTML comment, and does not read the display table with more columns that may follow for human readers.

## Producer obligations (skf-verify-stack)

- Set `schemaVersion: "1.0"` in frontmatter.
- Never emit a verdict token outside the defined set.
- Write the canonical table exactly once under `## Integration Verdicts`, with no data rows when the run found no integration pair: fill the empty table in `assets/feasibility-report-template.md` instead of appending a second one.
- When Check 4 (documentation cross-reference) finds no literal citation, cap the per-pair verdict at `Plausible`. Protocol and data-format tokens inferred from prose (Check 2) can flag a risk, but they neither promote a pair to `Verified` nor cap it at `Plausible`.
- When `coveragePercentage == 0`, force `overallVerdict: NOT_FEASIBLE` regardless of pair results.

## Consumer obligations (skf-refine-architecture, skf-create-stack-skill)

- Locate and read the report with `skf-validate-feasibility-report.py --locate` (see Filename); never build the file name in prose.
- Verify `schemaVersion == "1.0"`; halt with explicit error on mismatch.
- Treat any unknown verdict token (`--locate` lists them in `unknownTokens`) as a hard error (do not silently drop or map).

## Versioning policy

Any change to the verdict token set, frontmatter keys, or section headers is a schema-breaking change and MUST bump `schemaVersion`. Additive changes (new optional frontmatter keys) bump the minor version; breaking changes bump the major version.
