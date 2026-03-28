# Scoring Rules

## Default Threshold

**Pass threshold:** 80%

## Category Weights

| Category | Weight | Description |
|----------|--------|-------------|
| Export Coverage | 36% | Percentage of source exports documented in SKILL.md |
| Signature Accuracy | 22% | Documented signatures match actual source signatures |
| Type Coverage | 14% | Types and interfaces referenced are complete |
| Coherence (contextual) | 18% | Cross-references valid, integration patterns complete |
| Coherence (naive) | 0% | Not applicable — weight redistributed to other categories |
| External Validation | 10% | Average of skill-check quality score + tessl average score (redistributed if unavailable) |

## Naive Mode Weight Redistribution

The following weights replace the default table for naive mode. The 18% coherence weight from the default table has been proportionally redistributed into these values. Do not apply a second redistribution.

When running in naive mode (no coherence category):
- Export Coverage: 45%
- Signature Accuracy: 25%
- Type Coverage: 20%
- External Validation: 10%

## External Validation Unavailable

When neither skill-check nor tessl is available, redistribute the 10% external validation weight proportionally to the other active categories. When only one tool is available, use that tool's score as the external validation score.

## tessl and Split-Body Interaction

tessl evaluates SKILL.md body content only — it does not read `references/*.md` files. After split-body extraction, the tessl content score will drop significantly (e.g., 65% to 38%) because Tier 2 content is no longer inline. This is expected behavior and does not reflect actual content quality. When reporting scores for a split-body skill, note: "tessl content score reflects post-split inline content only. Use the pre-split tessl score as the content quality baseline."

## Tier-Dependent Scoring

### Quick Tier (no tools)
- Export Coverage: file/structure existence check only
- Signature Accuracy: skipped (no AST)
- Type Coverage: skipped (no AST)
- Score based on: structural completeness only
- Weight redistribution: skipped categories' weights (Signature Accuracy 22% + Type Coverage 14%) redistributed proportionally to remaining active categories

### Docs-Only Mode (Quick tier, all [EXT:...] citations)

When `docs_only_mode: true` is set by step-03 (indicating a Quick tier skill where all SKILL.md citations are `[EXT:...]` format with no local source code):

- **Signature Accuracy:** Not scored (no source to compare against)
- **Type Coverage:** Not scored (no source to compare against)
- **Weight redistribution:** Same as Quick tier — Signature Accuracy (22%) and Type Coverage (14%) weights redistributed proportionally to remaining active categories
- **Export Coverage basis:** Documentation completeness rather than source coverage. Score = (documented_items_with_complete_descriptions / total_documented_items) * 100. A "complete" item has: description, parameters (if function/method), and return type (if function/method).
- **Coherence:** Standard rules for the detected mode (naive or contextual) apply unchanged

This is functionally identical to Quick tier weight redistribution but with a different coverage denominator (self-consistency instead of source comparison).

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
- **Migration & Deprecation Warnings section:** If T2-future annotations exist in the enrichment data, verify that Section 4b is present in SKILL.md Tier 1 and that each warning traces to a T2 provenance citation. If no T2-future annotations exist, Section 4b should be absent (not empty). Presence/absence mismatch is a Medium severity gap.

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

## Result Determination

- score >= threshold → PASS
- score < threshold → FAIL

## Gap Severity

| Severity | Criteria |
|----------|----------|
| Critical | Missing exported function/class documentation |
| High | Signature mismatch between source and SKILL.md |
| Medium | Missing type or interface documentation |
| Medium | Migration section present/absent mismatch with T2-future annotation data (Deep tier) |
| Medium | Script/asset directory exists but no Scripts & Assets section in SKILL.md |
| Medium | Scripts & Assets section references file not found in scripts/ or assets/ directory |
| Low | Script/asset file present without provenance entry in provenance-map.json file_entries |
| Low | Missing optional metadata or examples |
| Low | Description trigger optimization recommended (third-person voice, negative triggers, or keyword coverage gaps) |
| Info | Style suggestions, non-blocking observations |
| Info | Discovery testing not performed — realistic prompt testing recommended before export |
