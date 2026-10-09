<!-- Config: communicate in {communication_language}. -->

# Scoring Rules

## Where the Scoring Rules Live

Scripts compute every score, so this file keeps no copy of their rules:

- `scripts/compute-score.py` owns the category weights (contextual and naive), the redistribution of each skipped category's weight (Quick tier, docs-only, State 2, no local source at States 3 and 4, a stack, a reference app, no external validation score), the State 2 undercount deduction, the minimum-evidence floor (INCONCLUSIVE), the two caps and the threshold fallback, in the order its docstring states. score.md sets the flags it reads and reads its verdict.
- `scripts/aggregate-coherence.py` owns the contextual coherence split between reference validity and integration completeness; coherence-check.md §5 decides which integration patterns are complete.
- `scripts/reconcile-coverage.py` computes Export Coverage on every branch; a docs-only skill takes its `docsOnly` branch, the documentation completeness ratio coverage-check.md §2c names. `scripts/score-signatures.py` computes Signature Accuracy and Type Coverage.

The pass threshold is `{defaultThreshold}`, unless `--threshold` or the pipeline's default overrides it (score.md §1).

## Gap Severity

This table is the single source of truth for classifying a gap. Every stage records each gap it finds in the gap ledger (`scripts/gap-ledger.py`, `{forge_version}/test-findings-{run_id}.json`) with the severity and the category of the row it matches. The hard gate (step 4c) blocks a run on any Critical or High gap, before scoring. A Medium, Low or Info gap never blocks. Scores come from the category metrics (a missing export lowers Export Coverage), and the pass threshold decides the verdict. Discovery testing runs after the gate, so a discovery gap of any severity is counted in the Gap Report and blocks nothing.

| Severity | Category                    | Criteria |
|----------|-----------------------------|----------|
| Critical | `signature-mismatch`        | Wrong signature: a documented signature that differs from the source in its parameters (name, type, order, optionality) or its return type (coverage-check §2) |
| Critical | `fabricated-signature`      | Fabricated signature: a documented export absent at the source line the skill cites for it. Decided only where ast-grep enumerated the exports at the pinned commit: the name is outside that surface, and the cited file is missing or defines no such name (coverage-check §2c) |
| Critical | `broken-reference`          | Broken reference (contextual mode): a reference whose target does not exist, such as a file not at the stated path, a skill not in the skills output folder, a type no module declares, or a `scripts/` or `assets/` file the skill names (coherence-check §4) |
| High     | `inaccurate-reference`      | Inaccurate reference (contextual mode): the target exists but does not match, such as a type the cited module does not export, a signature that differs, or an integration pattern that does not match the implementation (coherence-check §4) |
| High     | `reference-escape`          | A reference whose real path leaves the skill, its source and, for a stack, the skills output folder (coherence-check §4) |
| High     | `split-body-mismatch`       | The SKILL.md body and a `references/` file document one export differently (coverage-check §1b) |
| High     | `numerator-inflation`       | `stats.exports_documented` equals the denominator while declared exports are absent from SKILL.md and `references/` (coverage-check §4b) |
| High     | `structural`                | Naive mode: a missing required section, an unbalanced code fence, or a documented async or sync behaviour its example contradicts (coherence-check §2.1, §2.2, §2.5) |
| High     | `discovery`                 | Discovery test: at most 1 of 3 realistic prompts routed to the skill (report §4b.3) |
| Medium   | `missing-export`            | Missing export: an exported function or class the skill does not document. It lowers Export Coverage, and the threshold decides the verdict |
| Medium   | `missing-type`              | Missing type or interface documentation |
| Medium   | `stale-documentation`       | A documented export the enumerated source surface lacks that is not a fabricated signature and not a documented extra: classify-stale found no single file that declares it (an import, a re-export or an indented local does not count) and the skill's citations on the lines that name it cite no single one of the files that do, it is a dotted name, the brief scoped its file out (`excluded.outsideScope`), or the run could not look: the source is not Python or TS/JS, classify-stale did not run (it needs the Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `workspaceDrift` not `overridden` and a bound provenance map), or `surface.json` has no complete `extraction` (coverage-check §2c) |
| Medium   | `migration-section`         | Migration section present/absent mismatch with T2-future annotation data (Deep tier; Case 1 and Case 3 of `migration-section-rules.md`) |
| Medium   | `metadata-drift`            | Metadata drift: intra-cluster export counts diverge by more than 10% (barrel: `stats.exports_public_api` vs `exports[].length`; documented surface: `stats.exports_documented` vs the provenance-map named-export count), or denominator deflation: the re-derived source barrel exceeds `effective_denominator` by more than 25% and the brief has no `scope.tier_a_include` glob that matches a file (coverage-check §4 and §4b) |
| Medium   | `denominator-inflation`     | Denominator inflation: the stratified-scope `scope.include` union exceeds the provenance-map entry count by more than 25% (the brief has no `scope.tier_a_include` glob that matches a file) |
| Medium   | `brief-scope-stale`         | Stale brief scope: a `scope.include` glob matches no file in the source tested, so the surface restores the root exports defined in a file no glob covers that the brief does not exclude, or a `scope.tier_a_include` glob matches no file in the source tested, so it counts no name (coverage-check §4) |
| Medium   | `scripts-assets`            | A `scripts/` or `assets/` directory exists but SKILL.md has no Scripts & Assets section (coherence-check §2.7 and §4) |
| Medium   | `integration-pattern`       | Incomplete integration pattern (contextual mode): one entry of coherence-check §5's `incomplete_patterns` |
| Medium   | `structural`                | Naive mode: an opening code fence without a language tag, an exported function or method no usage-family section or reference file names, or a table row whose column count differs from its header (coherence-check §2.3, §2.4, §2.6) |
| Medium   | `discovery`                 | Discovery test: 2 of 3 realistic prompts routed to the skill (report §4b.3) |
| Low      | `scripts-assets-provenance` | Script/asset file present without provenance entry in provenance-map.json file_entries |
| Low      | `provenance-line`           | Provenance line is not the definition of an export (`line-not-definition`, coverage-check §4c) |
| Low      | `migration-section`         | Case 3 of `migration-section-rules.md` that the reviewer downgraded with an inline justification |
| Low      | `metadata`                  | Missing optional metadata or examples |
| Low      | `description`               | Description trigger optimization recommended (third-person voice, negative triggers, or keyword coverage gaps), a Tessl Review description suggestion included |
| Low      | `external-validator`        | A skill-check diagnostic or a Tessl Review validation finding the run left unresolved (external-validators §5b) |
| Info     | `observation`               | Style suggestions, non-blocking observations, and a documented extra: a documented name outside the enumerated surface that is not a fabricated signature and that the source still declares at column 0 (a module so named counts; among several declaring files, the one the skill cites on a line naming it), found only in a Python or TS/JS source where classify-stale ran (the Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `workspaceDrift` not `overridden` and a bound provenance map) and `surface.json` has a complete `extraction`: `Documented extra: {name}`, at that line, which update-skill never routes (coverage-check §2c) |
| Info     | `provenance-unverified`     | Provenance line not verified: the line-check rules found no definition line (coverage-check §4c) |
| Info     | `migration-section`         | Historical migration content in Section 4b with no T2-future annotation (Case 2 of `migration-section-rules.md`) |
| Info     | `multi-denominator`         | Multi-denominator reporting: barrel and documented-surface clusters diverge by design (>10% cross-cluster) |
| Info     | `discovery`                 | Discovery testing not performed (`--no-discovery`, a catalog of fewer than 2 skills, or no subagents to route the prompts): realistic prompt testing recommended before export (report §4b) |
| Info     | `external-validator`        | A Tessl Review content suggestion (advisory; one marked `(not applicable: …)` is not recorded) |
