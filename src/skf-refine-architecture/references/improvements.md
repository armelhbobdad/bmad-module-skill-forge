---
nextStepFile: 'compile.md'
refinementRulesData: '{refinementRulesPath}'
findingStorageData: 'references/finding-storage.md'
---

<!-- Config: communicate in {communication_language}. Append improvement findings to the RA state file in {document_output_language}. -->

# Step 4: Improvement Detection

## STEP GOAL:

Identify capability expansions: library features documented in the generated skills that the architecture does not leverage, of the types and value tiers the refinement rules define. For each improvement, document the capability and suggest how to incorporate it.

## Rules

- Focus only on capability expansions not leveraged in the architecture — do not repeat gaps (Step 02) or issues (Step 03)
- Improvements are additive suggestions — they enhance, not contradict, the architecture
- Every improvement must include evidence citations from actual skill content

## MANDATORY SEQUENCE

### 3. Compare Skill API Surfaces Against Architecture Usage

**Scope routing (from Step 02 §2b):** Apply `{in_scope_skills}` and `{out_of_scope_skills}`, and the pair lists `{in_scope_pairs}` and `{out_of_scope_pairs}` that Step 02 §3 split by them; if they are no longer in context, read them from the `[RA-SCOPE]` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`). Step 02 §4 read no surface of a skill in `{out_of_scope_skills}`, so no improvement or synergy involves one: a capability that pays off only together with an out-of-scope skill is not looked for.

For each skill in `{in_scope_skills}`:

Compare its `{skill_api_surfaces}` entry (`{exports, protocols, data_formats, capabilities}`, or the `<!-- [RA-SURFACES] ... -->` block of the same state file after a context loss) with what `{analysis_doc}`, the copy Step 01 §1b wrote with any earlier Refine Architecture pass set aside, says the library does. An export or capability the architecture never uses counts when it would strengthen the architecture, and so does a pattern the skill documents that beats the approach the architecture describes; an internal utility, helper or debug function does not. Never re-read a SKILL.md, in the parent or through new subagents.

### 4. Detect Cross-Library Synergies

Examine the pairs in `{in_scope_pairs}` (Step 02 §3: the pairs whose two skills are both in `{in_scope_skills}`) for one library's events or output the other can consume, or overlapping capabilities that could be unified, that the architecture does not exploit. A pair in `{out_of_scope_pairs}` is out of scope: skip it. Flag a synergy only where both sides have documented APIs.

### 5. Document Each Improvement

For each detected improvement, cite it in this format:

```
**[IMPROVEMENT]**: {description}

Evidence:
- {skill_name} exports: `{function}({params}) -> {return_type}`
- Architecture uses: {what the architecture currently describes}
- Untapped: {what the skill offers that the architecture does not mention}

Suggestion: {how to incorporate this capability into the architecture}
```

**Type and value:** type each improvement by the Improvement Classification of `{refinementRulesData}` and give it one tier of its Improvement Value table.

### 6. Report Improvements & Store Findings

Report the in-scope improvement count with its count per value tier, then list each improvement as a row of **# / Library / Improvement Type / Value / Summary** followed by its full §5 citation.

Store the **in-scope** improvement findings under a `<!-- [RA-IMPROVEMENTS] ... -->` block (their citations carry the evidence, value tier and suggestion), as `{findingStorageData}` says (an improvement that matches one a review dropped goes under `[RA-DISMISSED]` instead).

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

