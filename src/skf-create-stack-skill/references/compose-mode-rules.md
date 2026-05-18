<!-- Config: communicate in {communication_language}. -->

# Compose Mode Rules

Rules for synthesizing a stack skill from pre-generated individual skills and an architecture document, without requiring a codebase.

## Skill Loading

Skills use version-nested directories — see `knowledge/version-paths.md` for the full path templates and resolution rules.

**Version-aware skill enumeration:**

1. **Primary: Export manifest** — Read `{skills_output_folder}/.export-manifest.json`. For each entry in `exports`, resolve the active version path: `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/` — this directory must contain both `SKILL.md` and `metadata.json`.
2. **Fallback: `active` symlinks** — If the manifest does not exist, is empty, or a manifest entry lacks an `active_version`, scan for `{skills_output_folder}/*/active/*/SKILL.md`. Each match resolves to a skill package at `{skills_output_folder}/{skill-name}/active/{skill-name}/` (the `{active_skill}` template).
3. **Filter:** Skip any skill named `{project_name}-stack` or any skill where `metadata.json` has `"skill_type": "stack"` — stack skills must not be loaded as source dependencies to avoid self-referencing loops
4. Skip any resolved skill package missing either `SKILL.md` or `metadata.json` — log a warning and skip
5. Load each `metadata.json` from the resolved version-aware path and extract: `name`, `language`, `confidence_tier`, `source_repo`, `exports` (count), `version`
6. Store the skill group directory name as `skill_dir` (the top-level name under `{skills_output_folder}`, distinct from `name` — the directory may differ from the metadata name)
7. Store the resolved package path as `skill_package_path` for use in later steps (extraction, integration detection)
8. Store loaded skills as `raw_dependencies` with `source: "existing_skill"`

## Compose-mode Co-mention Precision

Prose co-mention detection is heuristic — it can only provide `Plausible`-class evidence (compared to code-mode's co-imports, which are literal). To reduce false positives the matcher in step 5 §2 applies three guards:

1. **Word-boundary matching** (`\b{skill_name}\b`, case-insensitive). Substring matches are rejected (no `react` inside `reactive`).
2. **Section filtering.** Paragraphs under H1/H2 headers that normalise to `introduction`, `overview`, `glossary`, `table of contents`, `references`, `appendix`, or `index` are excluded — they typically enumerate all libraries without describing integration. Headings themselves are also excluded as co-mention sources.
3. **Two-paragraph minimum.** A pair `(A, B)` requires at least two distinct body paragraphs co-mentioning both names. A single paragraph can be coincidental.

**Known limitations:** even with these guards, a co-mention only witnesses that two libraries are discussed together; it does not prove an integration exists. Downstream consumers should prefer stack manifests (`skf-create-stack-skill` output) to prose-derived evidence when both are available.

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

The feasibility report contract is defined by the shared schema at `src/shared/references/feasibility-report-schema.md` (single source of truth — `skf-verify-stack` is the producer, this skill is the consumer). Consumers MUST follow the schema verbatim:

- **Filename pattern:** `{forge_data_folder}/feasibility-report-{project_slug}-{YYYYMMDD-HHmmss}.md`, with a stable `feasibility-report-{project_slug}-latest.md` copy at the same location. Use `{project_slug}` (slugified `project_name`), not raw `{project_name}`.
- **Schema version guard:** Parse frontmatter and confirm `schemaVersion == "1.0"`. On mismatch, HALT with an explicit error; never silently proceed with an unknown version.
- **Overall verdict tokens** (frontmatter `overallVerdict`, case-sensitive): exactly one of `FEASIBLE | CONDITIONALLY_FEASIBLE | NOT_FEASIBLE`.
- **Per-pair verdict tokens** (in the `## Integration Verdicts` table, case-sensitive): exactly one of `Verified | Plausible | Risky | Blocked`. Any unknown token is a hard error.
- Include the verdict in the integration evidence: `VS overall: {overallVerdict}`, `VS pair: {verdict}`.
- Flag pairs where VS reported `Risky` or `Blocked`.

## Inferred Integrations (No Architecture Document)

When no architecture document is available:
- Infer potential integrations from skills sharing the same `language` field
- Infer from skills sharing domain keywords in their `SKILL.md` descriptions
- Mark all inferred integrations: `[inferred from shared domain]`
- Inferred integrations default to lowest confidence of the pair with `[inferred from shared domain]` suffix (use this instead of `[composed]` for inferred integrations)
