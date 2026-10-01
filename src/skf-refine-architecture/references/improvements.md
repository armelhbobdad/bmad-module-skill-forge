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

### 2. Build Architecture Usage Map

For each library referenced in the architecture document, extract how it is used. Read it as `{analysis_doc}`, the copy Step 01 §1b wrote with any earlier Refine Architecture pass set aside, so an old RA suggestion never reads as a capability the architecture already uses:

- What capabilities are described (e.g., "Loro for real-time data sync")
- What APIs or features are referenced
- What role it plays in the architecture

This creates a map of `{library} -> {described_usage[]}` for comparison against full skill API surfaces.

### 3. Compare Skill API Surfaces Against Architecture Usage

**Scope routing (from Step 02 §2b):** Apply `{in_scope_skills}` and `{out_of_scope_skills}`, and the pair lists `{in_scope_pairs}` and `{out_of_scope_pairs}` that Step 02 §3 split by them; if they are no longer in context, read them from the `[RA-SCOPE]` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`). An improvement or synergy that involves an out-of-scope skill, such as an in-scope capability that pays off only together with an out-of-scope skill, is not an improvement for this document even when it looks worthwhile: set it aside for the informational **Out-of-Scope** bucket (§6).

For each skill in `{in_scope_skills}`:

**Read its surface from `{skill_api_surfaces}`**, the compact `{exports, protocols, data_formats, capabilities}` summaries Step 02 §4 collected: its exports, types and protocol support, and the capabilities and features its SKILL.md documents beyond them. If they are no longer in context, read them from the `<!-- [RA-SURFACES] ... -->` block of the same state file. Never re-read a SKILL.md, in the parent or through new subagents.

**Compare against the architecture usage map:**
- Which exports and capabilities does the architecture reference or imply usage of?
- Which are not referenced in the architecture at all?

**For each unreferenced capability:**
- Evaluate relevance: would this capability strengthen the architecture?
- Skip trivial or internal-only exports (utilities, helpers, debug functions)
- Flag capabilities that could address architectural concerns or expand functionality

### 4. Detect Cross-Library Synergies

Examine the pairs in `{in_scope_pairs}` (Step 02 §3: the pairs whose two skills are both in `{in_scope_skills}`) for complementary capabilities not exploited in the architecture. A pair in `{out_of_scope_pairs}` is out of scope: skip it. For each in-scope pair, ask:

- Does Library A export an event system that Library B could consume?
- Does Library A produce a data format that Library B has an optimized processor for?
- Do two libraries offer overlapping capabilities that could be unified?

**Only flag synergies where both sides have documented APIs** — do not speculate about undocumented features.

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

Report the in-scope improvement count with its count per value tier, then list each improvement as a row of **# / Library / Improvement Type / Value / Summary** followed by its full §5 citation. One signal is not inferable from the counts and must survive regardless of format:

- **Out-of-scope improvements or synergies were set aside (from §3 and §4):** list them separately for awareness only (they were not counted as improvements) and note that re-running with `--scope-skills` pulls any that belong into scope.

Store the **in-scope** improvement findings under a `<!-- [RA-IMPROVEMENTS] ... -->` block (their citations carry the evidence, value tier and suggestion) and any out-of-scope improvement or synergy under the shared `<!-- [RA-OUT-OF-SCOPE] ... -->` marker, as `{findingStorageData}` says (an improvement that matches one a review dropped goes under `[RA-DISMISSED]` instead).

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

