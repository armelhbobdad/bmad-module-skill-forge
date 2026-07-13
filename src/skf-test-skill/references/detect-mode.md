---
nextStepFile: 'coverage-check.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Detect Mode

## STEP GOAL:

Examine the skill metadata to determine whether this is an individual skill (naive mode — API surface coverage only) or a stack skill (contextual mode — full coherence validation including cross-references and integration patterns).

### 1. Determine Test Mode

Read the skill metadata (loaded in step 01) and branch on its `skill_type` field — a single deterministic lookup:

- `skill_type: 'single'` → **Naive Mode** (API-surface coverage; coherence is structural only, no coherence category in scoring)
- `skill_type: 'stack'` → **Contextual Mode** (full coherence validation — cross-references resolve, types match, integration patterns complete; coherence category scored)
- unset or unclear → default to **Naive Mode** (conservative — fewer checks, less chance of false negatives from missing context) and note the default in the report

What each mode actually checks and how category weights are distributed is owned by `scoring-rules.md` (Tier-Dependent Scoring) and `coherence-check.md` — do not restate it here.

**Quick-tier adjustment (applies to both modes):** If `forge_tier` is `Quick`, Signature Accuracy and Type Coverage are skipped during scoring (no AST available); their weights are redistributed proportionally to the remaining active categories per `scoring-rules.md` Tier-Dependent Scoring.

### 2. Update Output Document

Update `{outputFile}` frontmatter:
- Set `testMode: '{naive|contextual}'`

Append the **Test Summary** section to `{outputFile}`:

```markdown
## Test Summary

**Skill:** {skill_name}
**Test Mode:** {naive|contextual}
**Forge Tier:** {detected_tier}

**Mode Rationale:** {brief explanation of why this mode was selected}

**Analysis Plan:**
- Coverage Check: {what will be checked based on mode + tier}
- Coherence Check: {what will be checked based on mode + tier}
```

### 3. Report Mode Detection

Report the detected mode ({naive|contextual}) and why it was selected (individual skill → naive, stack → contextual), then proceed to the coverage check.

Update stepsCompleted, then load and execute {nextStepFile}.

