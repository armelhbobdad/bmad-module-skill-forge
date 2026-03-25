# Compose Mode Rules

Rules for synthesizing a stack skill from pre-generated individual skills and an architecture document, without requiring a codebase.

## Skill Loading

1. Scan `{skills_output_folder}` for subdirectories containing both `SKILL.md` and `metadata.json`
2. Load each `metadata.json` and extract: `name`, `language`, `confidence_tier`, `source_repo`, `exports` (count), `version`
3. Reject any skill directory missing `metadata.json` — log a warning and skip
4. Store loaded skills as `raw_dependencies` with `source: "existing_skill"`

## Architecture Integration Mapping

1. Load the architecture document from `{architecture_doc_path}`
2. Parse section headers and prose paragraphs for references to loaded skill names
3. A **co-mention** is detected when a paragraph or section references 2+ loaded skill names
4. For each co-mention pair, load both skills' export lists and API signatures from their `SKILL.md`
5. Compose an integration section describing how the two libraries connect based on:
   - Shared types or interfaces between the two skills' API surfaces
   - Architecture document prose describing their interaction
   - Complementary domain roles (e.g., one produces data the other consumes)

## Confidence Tier Inheritance

- All compose-mode evidence inherits confidence tiers from the source individual skills
- If both skills in a pair are T1, the integration is T1
- If either skill is T1-low, the integration is T1-low
- If either skill is T2, the integration inherits T2 (highest tier wins for enriched data)
- Compose-mode integrations add suffix: `[composed]` — e.g., `T1 [composed]`

## Integration Evidence Format

Each integration entry must cite both source skills by name with function signatures:

```
{Skill A name} + {Skill B name}
  Type: [pattern type from integration-patterns.md]
  Evidence:
    [from skill: {Skill A name}] {exported_function_signature}
    [from skill: {Skill B name}] {exported_function_signature}
  Architecture reference: "{quoted prose from architecture doc}"
  Confidence: {inherited_tier} [composed]
```

## Feasibility Report Integration

If a feasibility report (`verify-stack-report.md` or similar) exists in `{forge_data_folder}/`:
- Load the VS feasibility verdict for each integration pair
- Include the verdict in the integration evidence: `VS verdict: {pass|warn|fail}`
- Flag any pairs where VS reported structural incompatibility

## Inferred Integrations (No Architecture Document)

When no architecture document is available:
- Infer potential integrations from skills sharing the same `language` field
- Infer from skills sharing domain keywords in their `SKILL.md` descriptions
- Mark all inferred integrations: `[inferred from shared domain]`
- Inferred integrations default to lowest confidence of the pair with `[inferred]` suffix
