<!-- Config: communicate in {communication_language}. -->

# Compose Mode Rules

Rules for synthesizing a stack skill from pre-generated individual skills and an architecture document, without requiring a codebase.

## Skill Loading

The version-aware skill-enumeration protocol (export-manifest primary → active-symlink fallback → stack-skill filter → load metadata fields → store as `raw_dependencies`) is specified operationally in `detect-manifests.md` §0. That step runs at step 2 and has already enumerated and loaded every constituent skill into workflow state before this file is consulted at step 5, so the loading is not re-performed here — this file covers only the compose-mode composition rules below.

## Compose-mode Co-mention Precision

Prose co-mention detection is heuristic: it can only provide `Plausible`-class evidence (compared to code-mode's co-imports, which are literal). The matcher in step 5 §2 applies two guards, and reports two evidence fields that step 5 §2 weighs instead of filtering on them:

1. **Word-boundary matching** (`\b{skill_name}\b`, case-insensitive). Substring matches are rejected (no `react` inside `reactive`). Headings are never co-mention sources.
2. **Listed pairs left out.** A pair named only in separate list items, table rows or code lines, as a Tech Stack table names every pair, is no candidate: `list_only_pair_count` counts those pairs.
3. **`excluded_section`.** True on an evidence entry whose paragraph sits under an introductory H1/H2 header (Overview, Introduction, Glossary and the like; `skf-comention-pairs.py`'s docstring lists the set): such sections often enumerate every library without describing an integration.
4. **`paragraph_count`.** The number of body paragraphs that name both libraries. One is enough to make a candidate: whether that passage describes an integration is a judgment on its excerpt.

**Known limitations:** even with the guards, a co-mention only witnesses that two libraries are discussed together; it does not prove an integration exists, so every pair the matcher reports is a candidate step 5 §2 judges.

## Architecture Integration Mapping

Step 5 §2 keeps a pair the architecture document names together only once its `unit_excerpt` shows how the two libraries work together, and writes it in the format below.

## Confidence Tier Inheritance

- All compose-mode evidence inherits confidence tiers from the source individual skills. Each constituent's tier is its `per_library_extractions[].confidence`, which step 4 §0 takes from the constituent's `evidence_tier`.
- An integration's tier is the pair tier `skf-render-stack-metadata.py` gives it (`combine_pair_tier`, the one rule both modes use, stated in its `--help`); step 5 §3 runs it for every pair.
- Compose-mode integrations add suffix: `[composed]`, e.g. `T1 [composed]` or `T2 [composed]`, except one inferred from shared domain keywords, which takes `[inferred from shared domain]` instead.

## Integration Evidence Format

Each integration entry must cite both source skills by name with function signatures:

```
#### {Skill A name} + {Skill B name}
**Type:** {pattern type from integration-patterns.md}
**Evidence:**
[from skill: {Skill A name}] {exported_function_signature}
[from skill: {Skill B name}] {exported_function_signature}
**Architecture reference:** "{unit_excerpt}" (architecture doc line {unit_line})
**Confidence:** {pair tier} ({qualifier}) [composed]
```

A pair found with no architecture document cites its own evidence in place of the architecture reference: `**Contract reference:** "{excerpt}" ({doc} line {line})` for a constituent-documented contract, or `**Shared domain:** {keywords}` for an inferred integration.

## Feasibility Report Integration

Step 5 §2 reads the [VS] report (`shared/references/feasibility-report-schema.md`) through `skf-validate-feasibility-report.py --locate`. An architecture pair it rates adds `VS overall: {overallVerdict}` and `VS pair: {verdict}` to its evidence, and a `[VS: Risky]` or `[VS: Blocked]` annotation for those verdicts. Pairs found without an architecture document carry no verdict: the report covers architecture-described interactions only.

## Inferred Integrations (No Architecture Document)

Step 5 §2 finds and judges these pairs in the constituents' own docs and domain keywords, never on a shared language alone.

- A docs mention step 5 §2 confirmed (a verifiable cross-library contract a constituent's own docs state, e.g. a grep-verified upstream seam) is recorded with `detection_method: constituent_documented_contract` (see `assets/provenance-map-schema.md`), NOT `inferred_from_shared_domain`, and labeled `[composed]`: a cited contract, not a synthesized guess.
- A shared-domain pair step 5 §2 kept is labeled `[inferred from shared domain]`.
- Detection method never sets the tier: each pair takes the tier `skf-render-stack-metadata.py` gives it.
