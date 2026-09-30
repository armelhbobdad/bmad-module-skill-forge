---
nextStepFile: 'compile.md'
refinementRulesData: '{refinementRulesPath}'
---

<!-- Config: communicate in {communication_language}. Append improvement findings to the RA state file in {document_output_language}. -->

# Step 4: Improvement Detection

## STEP GOAL:

Identify capability expansions — library features documented in the generated skills that the architecture does not leverage. Detect unused capabilities, cross-library synergies visible from skill API surfaces, and alternative patterns that could strengthen the architecture. For each improvement, document the capability and suggest how to incorporate it.

## Rules

- Focus only on capability expansions not leveraged in the architecture — do not repeat gaps (Step 02) or issues (Step 03)
- Improvements are additive suggestions — they enhance, not contradict, the architecture
- Every improvement must include evidence citations from actual skill content

## MANDATORY SEQUENCE

### 1. Reference Refinement Rules

Use the refinement rules loaded in Step 01 from `{refinementRulesData}`. If not available in context, reload from `{refinementRulesData}`.

Extract: improvement classification (Unused Capability, Cross-Library Synergy, Alternative Pattern) and detection method.

### 2. Build Architecture Usage Map

For each library referenced in the architecture document, extract how it is used:

- What capabilities are described (e.g., "Loro for real-time data sync")
- What APIs or features are referenced
- What role it plays in the architecture

This creates a map of `{library} -> {described_usage[]}` for comparison against full skill API surfaces.

### 3. Compare Skill API Surfaces Against Architecture Usage

**Scope routing (from Step 02 §2b):** Apply `{in_scope_skills}` and `{out_of_scope_skills}` here as gap analysis and issue detection do; if they are no longer in context, read them from the `[RA-SCOPE]` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`). This step suggests improvements for the document's scope only: §3 compares in-scope skills and §4 examines pairs of in-scope skills. An improvement or synergy that involves an out-of-scope skill, such as an in-scope capability that pays off only together with an out-of-scope skill, is not an improvement for this document even when it looks worthwhile: set it aside for the informational **Out-of-Scope** bucket (§6).

For each skill in `{in_scope_skills}`:

**Start from the surfaces already collected.** Reuse `{skill_api_surfaces}` (the compact `{exports, protocols, data_formats}` summaries from Step 02 §4) for exports, types, and protocol support — do not re-read SKILL.md in the parent.

**For the fuller capability read** — documented capabilities and features that go beyond §4's exports/protocols/data_formats extraction — delegate to parallel subagents mirroring Step 02 §4 (the canonical delegate-the-read pattern): each subagent reads one SKILL.md and returns compact JSON listing that skill's documented capabilities/features; the parent collects the summaries without loading full SKILL.md content. Reload a file directly only if its summary is unavailable or context has compacted.

**Compare against the architecture usage map:**
- Which exports does the architecture reference or imply usage of?
- Which exports are not referenced in the architecture at all?

**For each unreferenced capability:**
- Evaluate relevance: would this capability strengthen the architecture?
- Skip trivial or internal-only exports (utilities, helpers, debug functions)
- Flag capabilities that could address architectural concerns or expand functionality

### 4. Detect Cross-Library Synergies

Examine pairs of in-scope skills (both skills in `{in_scope_skills}`) for complementary capabilities not exploited in the architecture. A pair with an out-of-scope skill is out of scope, as in Step 02 §2b: skip it, and route a synergy with an out-of-scope skill that the comparison brings up anyway to the Out-of-Scope bucket (§3 scope routing). For each in-scope pair, ask:

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

**Categorize improvements:**
- **High:** Capabilities that address known architectural concerns or significantly expand functionality
- **Medium:** Capabilities that add convenience or efficiency improvements
- **Low:** Capabilities that are nice-to-have but not impactful

### 6. Report Improvements & Store Findings

Report the in-scope improvement count with its high/medium/low value breakdown, then list each improvement as a row of **# / Library / Improvement Type / Value / Summary** followed by its full §5 citation. One signal is not inferable from the counts and must survive regardless of format:

- **Out-of-scope improvements or synergies were set aside (from §3 and §4):** list them separately for awareness only (they were not counted as improvements) and note that re-running with `--scope-skills` pulls any that belong into scope.

Store the **in-scope** improvement findings per the Finding Storage rule (refinement rules), under a `<!-- [RA-IMPROVEMENTS] ... -->` block (its citations carry the evidence, value rating, and suggestion). Record any out-of-scope improvement or synergy under the shared `<!-- [RA-OUT-OF-SCOPE] ... -->` marker so Step 05 leaves it out of the refined document: it is informational only.

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

