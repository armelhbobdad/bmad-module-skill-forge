<!-- Config: communicate in {communication_language}. -->

# Compose Mode Rules

The labels and the evidence format of a compose-mode integration: step 5 (`references/compose-pairs.md`) builds each pair's evidence in this format, and step 6 renders it.

## Confidence Tier Inheritance

- All compose-mode evidence inherits confidence tiers from the source individual skills. Each constituent's tier is its `per_library_extractions[].confidence`, which step 4 (`references/compose-extract.md`) takes from the constituent's `evidence_tier`.
- An integration's tier is the pair tier `skf-render-stack-metadata.py` gives it (`combine_pair_tier`, the one rule both modes use, stated in its `--help`); step 5 §3 runs it for every pair.
- Compose-mode integrations add suffix: `[composed]`, e.g. `T1 [composed]` or `T2 [composed]`, except one inferred from shared domain keywords, which takes `[inferred from shared domain]` instead.

## Integration Evidence Format

Each integration entry must cite both source skills by name with function signatures:

```
#### {Skill A name} + {Skill B name}
**Type:** {the pair's type, assigned in step 5 §3 from {integrationPatternsPath}}
**Evidence:**
[from skill: {Skill A name}] {exported_function_signature}
[from skill: {Skill B name}] {exported_function_signature}
**Architecture reference:** "{unit_excerpt}" (architecture doc line {unit_line})
**Confidence:** {pair tier} ({qualifier}) [composed]
```

A pair found with no architecture document cites its own evidence in place of the architecture reference: `**Contract reference:** "{excerpt}" ({doc} line {line})` for a constituent-documented contract, or `**Shared domain:** {keywords}` for an inferred integration.

## Feasibility Report Integration

Step 5 (`references/compose-pairs.md` §2) reads the [VS] report (`shared/references/feasibility-report-schema.md`) through `skf-validate-feasibility-report.py --locate`. An architecture pair it rates (its bundle entry's `vs`) adds `VS overall: {overallVerdict}` and `VS pair: {verdict}` lines after its Architecture reference, and its Confidence line ends with a `[VS: Risky]` or `[VS: Blocked]` annotation for those verdicts. Pairs found without an architecture document carry no verdict: the report covers architecture-described interactions only.
