<!-- Config: communicate in {communication_language}. -->

# Scoring Rules

## Default Threshold

**Pass threshold:** 80%

## Category Weights

| Category               | Weight | Description                                                                               |
|------------------------|--------|-------------------------------------------------------------------------------------------|
| Export Coverage        | 36%    | Percentage of source exports documented in SKILL.md                                       |
| Signature Accuracy     | 22%    | Documented signatures match actual source signatures                                      |
| Type Coverage          | 14%    | Types and interfaces referenced are complete                                              |
| Coherence (contextual) | 18%    | Cross-references valid, integration patterns complete                                     |
| Coherence (naive)      | 0%     | Not applicable — weight redistributed to other categories                                 |
| External Validation    | 10%    | skill-check score, averaged with the opt-in Tessl Review score (redistributed if absent)   |

## Naive Mode Weight Redistribution

The following weights replace the default table for naive mode. The 18% coherence weight from the default table has been proportionally redistributed into these values. Do not re-redistribute for coherence (already handled in this table). Quick-tier redistribution (zeroing Signature Accuracy and Type Coverage) still applies as an additional step.

When running in naive mode (no coherence category):
- Export Coverage: 45%
- Signature Accuracy: 25%
- Type Coverage: 20%
- External Validation: 10%

## External Validation Unavailable

When neither skill-check nor Tessl Review produced a score (Tessl Review runs only when the user set `tessl_review_workspace` in preferences.yaml), redistribute the 10% external validation weight proportionally to the other active categories. When only one produced a score, use that score as the external validation score.

## Tier-Dependent Scoring

### Quick Tier (no tools)
- Export Coverage: file/structure existence check only
- Signature Accuracy: skipped (no AST)
- Type Coverage: skipped (no AST)
- Score based on: structural completeness only
- Weight redistribution: skipped categories' weights (Signature Accuracy 22% + Type Coverage 14%) redistributed proportionally to remaining active categories

### Docs-Only Mode (all [EXT:...] citations, any tier)

When `docs_only_mode: true` is set by step 3 (indicating a skill where all SKILL.md citations are `[EXT:...]` format with no local source code):

- **Signature Accuracy:** Not scored (no source to compare against)
- **Type Coverage:** Not scored (no source to compare against)
- **Weight redistribution:** Same as Quick tier — Signature Accuracy (22%) and Type Coverage (14%) weights redistributed proportionally to remaining active categories
- **Export Coverage basis:** Documentation completeness rather than source coverage. Score = (documented_items_with_complete_descriptions / total_documented_items) * 100. A "complete" item has: description, parameters (if function/method), and return type (if function/method).
- **Coherence:** Standard rules for the detected mode (naive or contextual) apply unchanged

This is functionally identical to Quick tier weight redistribution but with a different coverage denominator (self-consistency instead of source comparison).

**External-validator requirement for docs-only:** docs-only mode removes two categories (Signature Accuracy, Type Coverage) from scoring. If External Validation is also unavailable, the evidence base collapses to Coverage alone (naive) or Coverage + Coherence (contextual) — which in the naive/Quick case trips the minimum-evidence floor (INCONCLUSIVE). To keep docs-only skills gradable when external validators are present but still deterministic when they are missing: **when `docsOnly: true` AND `externalValidation is null`, step 5 must cap `totalScore` at `threshold - 1` (forcing FAIL) before the INCONCLUSIVE floor is evaluated.** This prevents a docs-only skill from PASSing with only one or two redistributed categories carrying all the weight. Implement in step 5 §4 as a pre-compare cap, recorded in the report as `scoring_notes: docs-only without external validators — capped below threshold`.

### Stack Skills (Any Tier)

When `metadata.json.skill_type == "stack"` (set `stackSkill: true` in the scoring input):

- **Signature Accuracy:** N/A — a stack skill's "signature surface" is the external library API it composes (pydantic, SQLAlchemy, FastAPI, etc.), not a proprietary surface the skill authors. Grading signatures against a surface the skill does not own produces meaningless numbers.
- **Type Coverage:** N/A — same rationale; the type surface belongs to the external libraries.
- **Weight redistribution:** Same as Quick tier / docs-only / State 2 — Signature Accuracy (22%) and Type Coverage (14%) weights redistributed proportionally to remaining active categories (Export Coverage, Coherence, External Validation).
- **Applies regardless of detected tier** (Quick, Forge, Forge+, Deep) and is independent of `docsOnly` and `state2`. A stack skill can also be docs-only or State 2; the skip reasons combine additively (e.g. `"stack skill (external type surface) + State 2 (provenance-map)"`).
- **Detection:** step 5 reads `metadata.json.skill_type` from the skill package. If the value is `"stack"`, set `stackSkill: true` in the scoring input JSON.

### Reference-App Skills (Any Tier)

When `metadata.json.scope_type == "reference-app"` (set `referenceApp: true` in the scoring input):

- **Signature Accuracy:** N/A — a reference app documents wiring patterns (how surfaces are composed), not a library export surface the skill authors. There are no public-export signatures to grade against; the Pattern Surface replaces the Key API Summary (see `skf-create-skill` Reference-App Assembly Overrides).
- **Type Coverage:** N/A — same rationale; a reference app has no library type surface to cover. Coverage is measured as pattern-surface coverage (`stats.pattern_surfaces_documented`), not export/type coverage.
- **Weight redistribution:** Same as Quick tier / docs-only / State 2 / stack — Signature Accuracy (22%) and Type Coverage (14%) weights redistributed proportionally to remaining active categories (Export Coverage, Coherence, External Validation).
- **Applies regardless of detected tier** (Quick, Forge, Forge+, Deep) and is independent of `docsOnly` and `state2`; skip reasons combine additively. `referenceApp` and `stackSkill` are distinct scope/type signals and should not both be set for the same skill.
- **Detection:** step 5 reads `metadata.json.scope_type` from the skill package. If the value is `"reference-app"`, set `referenceApp: true` in the scoring input JSON. The skip reason recorded is `"reference-app (no library export signatures)"`.

### State 2 Source Access (Any Tier, Provenance-Map Only)

When source is not locally available and analysis resolves to State 2 (provenance-map baseline per source-access-protocol.md):

- **Signature Accuracy:** N/A — provenance-map stores parameters as flat string arrays; verification is string comparison only, not semantic AST verification. Type aliases (`str` vs `String`, `list` vs `List[Any]`) cannot be resolved without live source.
- **Type Coverage:** N/A — cannot verify type completeness without local source access for AST re-parsing.
- **Weight redistribution:** Same as Quick tier — Signature Accuracy (22%) and Type Coverage (14%) weights redistributed proportionally to remaining active categories (Export Coverage, Coherence, External Validation).
- **Applies regardless of detected tier** (including Forge, Forge+, Deep) whenever `analysis_confidence` is `provenance-map` and local source is unavailable.
- **Export Coverage denominator:** Uses the union of provenance-map entry names and metadata.json `exports[]` names (per source-access-protocol.md State 2 rules).

Note: When provenance-map entries are predominantly T1 (AST-verified at compilation time), the coverage and name-matching data is already at highest confidence. The N/A categories reflect the inability to re-verify at test time, not low-quality extraction data.

**State 2 undercount risk acknowledgement:** provenance-map is a cached extraction snapshot — if the source has evolved since extraction, public API adds/removes will not surface in Export Coverage (denominator is frozen to the provenance-map union). When `state2: true` AND step 3 records any provenance vs metadata divergence (e.g. union > either source by >5%), apply a flat **10% deduction** to `exportCoverage` before calling the scoring script, AND set `analysis_confidence: provenance-map` (already set) with a report note: `scoring_notes: State 2 undercount risk acknowledged — 10% deduction applied to Export Coverage`. Rationale: the skill cannot be reliably scored on a frozen denominator when the cache is known to disagree with its own metadata; prefer understating over overstating.

### Forge Tier (ast-grep)
- Export Coverage: AST-backed export comparison
- Signature Accuracy: AST-verified signature matching
- Type Coverage: AST-verified type completeness
- Full scoring formula applied

### Forge+ Tier (ast-grep + ccc)
- Same scoring as Forge tier — ccc provides pre-ranking but does not change scoring weights
- Improved extraction coverage (from ccc pre-discovery) may increase T1 count, but scoring formula is identical to Forge
- Full scoring formula applied

### Deep Tier (ast-grep + gh + QMD)
- All Forge tier checks plus:
- Cross-repository reference verification
- QMD knowledge enrichment for coherence
- Full scoring formula with maximum depth
- **Migration & Deprecation Warnings section:** If T2-future annotations exist in the enrichment data, verify that Section 4b is present in SKILL.md Tier 1 and that each warning traces to a T2 provenance citation. If no T2-future annotations exist, Section 4b should normally be absent (not empty). Presence/absence mismatch is a Medium severity gap — with one Info-severity exception for historical-migration content (completed package renames, consolidated import paths, shipped API cutovers that remain load-bearing for training-data drift remediation). See `references/coherence-check.md` §2b/§5b for the three-case rule.

## Score Calculation

```
score = sum(category_weight * category_score) for each category
category_score = (items_passing / items_total) * 100
```

## Coherence Score Aggregation (Contextual Mode)

```
reference_validity = (valid_references / total_references) * 100
integration_completeness = (complete_patterns / total_patterns) * 100
combined_coherence = (reference_validity * 0.6) + (integration_completeness * 0.4)
```

If no integration patterns exist, combined coherence equals reference validity.

This is the documented contract. The tally + weighted mean is computed by `scripts/aggregate-coherence.py` (invoked from coherence-check.md §5c), not by hand; the per-reference validity judgment (§4) and pattern-completeness judgment (§5) stay in the prompt, only the arithmetic is scripted.

A pattern is one entry under Cross-Cutting Patterns or Library Pair Integrations in the stack's Integration Patterns section; the Hub Library Connections summaries are not patterns. A pattern is complete when it meets the integration-completeness criteria in `references/coherence-check.md` §5. The first of them asks for the wiring evidence the stack's mode records, not a code example. In a code-mode stack, the evidence is `file:line` citations and key files. In a compose-mode stack, it is one `[from skill: {skill name}]` line for each constituent skill the entry joins, citing something that skill exports. For a skill that exports functions, that is an exported function signature, the `[from skill: {skill name}] {exported_function_signature}` line of the Integration Evidence Format in `skf-create-stack-skill/references/compose-mode-rules.md`. For any other constituent (a skill whose `scope_type` is `reference-app` or `docs-only`, or whose exports are not functions), it is the export, pattern surface or documented contract the line quotes. A `[from skill: …]` line that cites nothing the skill exports does not count. A fenced code block is not required.

## Result Determination

Three-state gate — **PASS / FAIL / INCONCLUSIVE**. `INCONCLUSIVE` is not PASS and not FAIL; it signals insufficient evidence to grade the skill. Downstream workflows must treat `INCONCLUSIVE` as a hard gate — do not export, do not auto-retry, surface to the human.

- **Minimum-Evidence Floor (applies before PASS/FAIL comparison):**
  - `active_categories` = count of categories with a non-zero final weight *after* all redistribution (Quick tier, docs-only, State 2, external-validator-unavailable). Categories with a redistributed weight of 0 do not count as active, even if they received a score.
  - **If `active_categories < 2`** → force `result: INCONCLUSIVE` with rationale `"insufficient evidence: only {N} active category"`. A single active category cannot cross-validate itself and a PASS would be a false signal.
  - **If `tier == "Quick"` AND the sole active contributor is Export Coverage** → force `result: INCONCLUSIVE` with rationale `"Quick tier: Export Coverage alone is insufficient evidence — add a second active category by upgrading tier or enabling external validators"`. This catches the degenerate case where every signature/type/coherence/external category gets redistributed to 0 and Export Coverage is doing all the work.
  - The floor is enforced by `scripts/compute-score.py`. The step 5 scoring step reads `result` from the script output and writes it into the test report frontmatter unchanged.

- Otherwise:
  - score >= threshold → PASS
  - score < threshold → FAIL

The floor is intentionally conservative: skf-test-skill grades other skills, so a false PASS has catastrophic downstream effects (polluted exports, misleading feasibility data). Falling back to INCONCLUSIVE is always preferred over a low-evidence PASS.

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
| Medium   | `stale-documentation`       | A documented export the enumerated source surface lacks that is not a fabricated signature: its cited file defines it, or no cited line could be checked (coverage-check §2c) |
| Medium   | `migration-section`         | Migration section present/absent mismatch with T2-future annotation data (Deep tier; Case 1 and Case 3 of `migration-section-rules.md`) |
| Medium   | `metadata-drift`            | Metadata drift: intra-cluster export counts diverge by more than 10% (barrel: `stats.exports_public_api` vs `exports[].length`; documented surface: `stats.exports_documented` vs the provenance-map named-export count), or denominator deflation: the re-derived source barrel exceeds `effective_denominator` by more than 25% and the brief has no `scope.tier_a_include` (coverage-check §4 and §4b) |
| Medium   | `denominator-inflation`     | Denominator inflation: the stratified-scope `scope.include` union exceeds the provenance-map entry count by more than 25% (brief missing `scope.tier_a_include`) |
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
| Info     | `observation`               | Style suggestions, non-blocking observations |
| Info     | `provenance-unverified`     | Provenance line not verified: the line-check rules found no definition line (coverage-check §4c) |
| Info     | `migration-section`         | Historical migration content in Section 4b with no T2-future annotation (Case 2 of `migration-section-rules.md`) |
| Info     | `multi-denominator`         | Multi-denominator reporting: barrel and documented-surface clusters diverge by design (>10% cross-cluster) |
| Info     | `discovery`                 | Discovery testing not performed (`--no-discovery`, a catalog of fewer than 2 skills, or no subagents to route the prompts): realistic prompt testing recommended before export (report §4b) |
| Info     | `external-validator`        | A Tessl Review content suggestion (advisory; one marked `(not applicable: …)` is not recorded) |
