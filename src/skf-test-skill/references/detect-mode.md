---
nextStepFile: 'coverage-check.md'
outputFile: '{report_file}'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Detect Mode

## STEP GOAL:

Examine the skill metadata to determine whether this is an individual skill (naive mode — API surface coverage only) or a stack skill (contextual mode — full coherence validation including cross-references and integration patterns).

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Determine Test Mode

Read the skill metadata (loaded in step 01) and branch on its `skill_type` field — a single deterministic lookup:

- `skill_type: 'single'` → **Naive Mode** (API-surface coverage; coherence is structural only, no coherence category in scoring)
- `skill_type: 'stack'` → **Contextual Mode** (full coherence validation — cross-references resolve, types match, integration patterns complete; coherence category scored)
- unset or unclear → default to **Naive Mode** (conservative: fewer checks, less chance of false negatives from missing context), note the default in the report, and record it as a warning: write `test-mode-defaulted-naive: metadata.json skill_type is {its value, or unset}` to `{run_dir}/warning.txt` with a file write, then, from `{project-root}`, run:

  ```bash
  uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"
  ```

What each mode actually checks is owned by `coherence-check.md`, and how category weights are distributed by step 5's scoring script (`scripts/compute-score.py`): do not restate either here.

**Quick-tier adjustment (applies to both modes):** set nothing here. Step 5 passes the tier to the scoring script, which skips Signature Accuracy and Type Coverage at Quick tier (no AST available) and redistributes their weights.

### 2. Update Output Document

Update `{outputFile}` frontmatter:
- Set `testMode: '{naive|contextual}'`

Write the **Test Summary** section in place of the template's `## Test Summary` heading and the placeholder comment under it, in `{outputFile}`:

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

Append `'detect-mode'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.

