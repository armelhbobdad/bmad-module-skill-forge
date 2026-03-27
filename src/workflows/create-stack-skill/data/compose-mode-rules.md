# Compose Mode Rules

Rules for synthesizing a stack skill from pre-generated individual skills and an architecture document, without requiring a codebase.

## Skill Loading

1. Scan `{skills_output_folder}` for subdirectories containing both `SKILL.md` and `metadata.json`
2. **Filter:** Skip any subdirectory named `{project_name}-stack` or any skill where `metadata.json` has `"skill_type": "stack"` — stack skills must not be loaded as source dependencies to avoid self-referencing loops
3. Skip any subdirectory missing either `SKILL.md` or `metadata.json` — log a warning and skip
4. Load each `metadata.json` and extract: `name`, `language`, `confidence_tier`, `source_repo`, `exports` (count), `version`
5. Store the subdirectory name as `skill_dir` (distinct from `name` — the directory may differ from the metadata name)
6. Store loaded skills as `raw_dependencies` with `source: "existing_skill"`

## Architecture Integration Mapping

**If `{architecture_doc_path}` is null or the file does not exist:** Skip this section and proceed to [Inferred Integrations (No Architecture Document)](#inferred-integrations-no-architecture-document) below.

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
- If either skill is T2, the structural confidence still inherits the lower of T1/T1-low from the pair — the T2 temporal annotations from that skill are carried as an additive enrichment marker, not a tier upgrade
- T1 + T2 pair: inherits `T1 [composed, +T2 annotations]` — the T1 skill provides full structural confidence
- T1-low + T2 pair: inherits `T1-low [composed, +T2 annotations]` — T1-low structural confidence with T2 temporal annotations noted
- If both skills are T2 (no T1/T1-low base available): the integration confidence is `T1-low [composed, +T2 annotations from both]` — T2 temporal enrichment depends on structural extraction, so the most conservative structural tier is assumed
- Compose-mode integrations add suffix: `[composed]` — e.g., `T1 [composed]`, `T1-low [composed, +T2 annotations]`

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

If a feasibility report (`feasibility-report-{project_name}.md`) exists in `{forge_data_folder}/`:
- Load the VS overall verdict from the report's YAML frontmatter `overall_verdict` field (`FEASIBLE`, `CONDITIONALLY FEASIBLE`, or `NOT FEASIBLE`) and parse per-pair verdicts from the `## Integration Verdicts` markdown table (`Verified`, `Plausible`, `Risky`, or `Blocked`)
- Include the verdict in the integration evidence: `VS overall: {FEASIBLE|CONDITIONALLY FEASIBLE|NOT FEASIBLE}`, `VS pair: {Verified|Plausible|Risky|Blocked}`
- Flag any pairs where VS reported `Risky` or `Blocked` verdicts

## Inferred Integrations (No Architecture Document)

When no architecture document is available:
- Infer potential integrations from skills sharing the same `language` field
- Infer from skills sharing domain keywords in their `SKILL.md` descriptions
- Mark all inferred integrations: `[inferred from shared domain]`
- Inferred integrations default to lowest confidence of the pair with `[inferred from shared domain]` suffix (use this instead of `[composed]` for inferred integrations)
