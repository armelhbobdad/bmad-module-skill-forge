# Migration & Deprecation Section Rules (§2b / §5b)

> **Single source of truth.** Both `coherence-check.md` §2b (naive path)
> and §5b (contextual path) apply the rules in this file verbatim. Update this
> file — not the step file sections — when the rule set changes.

## Gate Check

Execute this check ONLY IF both conditions are met:

1. Forge tier is **Deep** (tool-gated)
2. `{forge_data_folder}/{skill_name}/evidence-report.md` exists (data-gated)

If either condition fails, skip silently and proceed to the next section.

The check runs regardless of naive/contextual mode. T2-future annotations are a
property of the source code and enrichment data, not the skill type.

## Scope of Section 4b (Authoring Rule This Gate Enforces)

Section 4b (SKILL.md "Migration & Deprecation Warnings") is scoped to
*forward-looking* breaking changes only — what T2-future annotations capture.
Current-state signature gotchas (e.g. "this function is sync not async") belong
alongside the function in Full API Reference, **not here**.

This scoping is authoritative per `skf-create-skill/assets/skill-sections.md`
("Section 4b (Migration & Deprecation Warnings) is conditional: only emitted
for Deep tier when T2-future annotations exist").

Two legitimate exceptions for the `T2-future = 0 AND Section 4b present` case
are formalized in the rules below:

- **(a) historical migration** content — past, shipped package renames or
  consolidated import paths that remain load-bearing for correcting model
  training-data drift → Info severity, no justification required.
- **(b) other non-migration content** — reviewer may downgrade to Low with
  inline justification.

Do not relax the gate otherwise — that would desync the test workflow from the
authoring rule.

## Case Rules

Check whether SKILL.md contains a "Migration & Deprecation Warnings" section
(Section 4b). Then parse `evidence-report.md`'s **YAML frontmatter** for the
pinned `t2_future_count` field — this is the authoritative count, not the
narrative body.

**Detection contract (MANDATORY).** Read the frontmatter deterministically:

```bash
# Extract t2_future_count from frontmatter. Requires a `---` delimiter pair.
awk '/^---$/{c++;next} c==1 && /^t2_future_count:/{print $2; exit}' \
    {forge_data_folder}/{skill_name}/evidence-report.md
```

- **Frontmatter missing OR `t2_future_count` absent** → treat as Case 4 (see
  below) and skip silently. Do NOT fall back to grepping prose (`grep "T2-future"`) —
  prose drift (heading renames, alt phrasings like "forward-looking
  annotations", capitalization variance) silently breaks detection and can
  invert Case-1 vs Case-2/3 severity.
- **`t2_future_count` parsed** → use its integer value for the Case Rules
  below.

The pinned field is emitted by `skf-create-skill/references/compile.md`
§7 (frontmatter-pinned fields), which ALWAYS writes `t2_future_count: N`
(including 0). Legacy skills whose `evidence-report.md` predates the pinned
field land in Case 4.

### Case 1 — T2-future > 0 AND Section 4b absent

Flag as **Medium** severity gap:

> "Migration section missing — T2-future annotations exist but Section 4b is
> not present in SKILL.md Tier 1."

### Case 2 — T2-future = 0 AND Section 4b present AND content is historical migration

Flag as **Info** severity (not Medium). Historical migration content covers
completed package renames (e.g. `@oldscope/*` → `@newscope/*`), consolidated
import paths, and shipped API cutovers that still surface in training-data
drift — load-bearing for correcting model knowledge even though no
forward-looking change is pending.

Recognizable patterns: old-name → new-name rewrites, citations to
already-shipped PRs/issues, "migrated in version N" or "consolidated from X to
Y" language.

Recommend in the gap report that a future skill revision rename Section 4b to
"Import Corrections" or "Ecosystem Notes" to free the Migration & Deprecation
heading for its forward-looking contract. No inline justification required —
the historical-migration classification is itself the rationale.

### Case 3 — T2-future = 0 AND Section 4b present AND content is non-migration

Flag as **Medium** severity gap:

> "Migration section unexpected — Section 4b contains non-migration content and
> no T2-future annotations were produced."

Reviewer may downgrade to Low with inline justification on a case-by-case
basis.

### Case 4 — evidence-report.md unavailable

Skip silently. Record the note:

> "Section 4b verification skipped — evidence-report.md not found."

## Output

Append any resulting finding(s) to the coherence analysis results. Both the
naive path (§2b) and the contextual path (§5b) funnel findings into the same
Coherence Analysis section of `{outputFile}`.
