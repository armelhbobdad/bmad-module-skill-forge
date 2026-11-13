---
nextStepFile: 'report.md'
outputFile: '{report_file}'
sourceAccessProtocol: 'references/source-access-protocol.md'
scoringScript: 'scripts/compute-score.py'
# §6 writes the verdict fields and the Completeness Score section through it.
resultContextScript: 'scripts/build-result-context.py'
---

<!-- Config: communicate in {communication_language}. Test report prose in {document_output_language}. -->

# Step 5: Score

## STEP GOAL:

Calculate the overall completeness score by aggregating coverage, coherence, and external validation category scores with the appropriate weight distribution (naive or contextual), apply the pass/fail threshold, and determine the test result.

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Read the Pass Threshold

`{scoringScript}` owns the category weights, their redistribution and every verdict rule; this step sets its flags, hands it the score files and reads its output.

**The pass threshold was resolved once, at init** (init.md §1b), and init.md §6c wrote it into the report. Read `threshold` and `thresholdSource` from the `{outputFile}` frontmatter and bind `effective_threshold` ← `threshold` as a number (without its `%`) and `threshold_source` ← `thresholdSource`. Never resolve the precedence again here: the frontmatter keeps what a long run's context may lose.

Pass `effective_threshold` into the scoring-input JSON's `threshold` field in §3a. The CLI flag, pipeline default, and the scalar all feed the same downstream field; the script does not need to know which layer supplied the value.

### 2. The Category Score Files

The category scores are never read back out of the report: each is the output file of the script that computed it, in the run folder `{run_dir}` (init.md §6b), and §3b hands the files to the scoring script by path:

- `coverage.json`: Export Coverage (coverage-check §2c)
- `signatures.json`: Signature Accuracy and Type Coverage (coverage-check §2b; there is none at Quick tier, for a docs-only skill, at States 2 to 5, or for a stack or a reference app)
- `coherence.json`: the combined coherence (coherence-contextual.md §5c; contextual mode only)
- `external.json`: the external validation score (external-validators §4; its `externalScore` is null when neither validator scored)
- `surface.json`: the source surface coverage-check §2 wrote, on every run but a docs-only one; at State 2 it holds the provenance-map and metadata counts behind the State 2 undercount deduction

### 3. Apply Weight Distribution

**Read testMode from {outputFile} frontmatter.**

#### 3a. Construct Scoring Input JSON

Build the flags the script reads from what the earlier steps wrote: `mode` from the frontmatter's `testMode` (detect-mode §2), `tier` from its `forgeTier` (init.md §6c), `docsOnly` and `analysisConfidence` from its keys of those names (coverage-check wrote them), `stackSkill` and `referenceApp` from metadata.json, and `toolingStatus` from the `{outputFile}` frontmatter (init.md §6c wrote it), never from memory:

```json
{
  "mode": "{testMode: contextual or naive}",
  "tier": "{forgeTier from the {outputFile} frontmatter: Quick, Forge, Forge+, or Deep}",
  "docsOnly": "{true if the {outputFile} frontmatter's docsOnly is true, else false}",
  "state2": "{true if the {outputFile} frontmatter's analysisConfidence is provenance-map, else false}",
  "stackSkill": "{true if metadata.json.skill_type == 'stack', else false}",
  "referenceApp": "{true if metadata.json.scope_type == 'reference-app', else false}",
  "threshold": "{effective_threshold from §1}",
  "analysisConfidence": "{analysisConfidence from the {outputFile} frontmatter: full, provenance-map, metadata-only, remote-only or docs-only}",
  "toolingStatus": "{toolingStatus from the {outputFile} frontmatter: ok, or frontmatter-validator-timeout}"
}
```

**Important:** the flags are bare booleans (`true`, not `"true"`) and the threshold a number. Always pass `toolingStatus`: any value other than `ok` fires Cap 1 (§3d). `analysisConfidence` names the source access only, never tooling health. Read `metadata.json.skill_type` and `metadata.json.scope_type` from `{resolved_skill_package}/metadata.json`: a stack (`stackSkill`) and a reference app (`referenceApp`, which documents wiring patterns, not library export signatures) have no Signature Accuracy or Type Coverage, and the script redistributes their weights. With no local source (`analysisConfidence` `metadata-only` or `remote-only`, States 3 and 4) it skips both categories at any tier, as it does at Quick tier, for `docsOnly` and for `state2`.

#### 3b. Run the Scoring Script

Pass the §3a JSON and the score files that exist: `--signatures` when coverage-check scored the signatures, `--coherence` in contextual mode, and `--surface` whenever `{run_dir}/surface.json` exists (every run but a docs-only one). The script refuses a `docsOnly` that `coverage.json` contradicts and a `state2` that `surface.json` contradicts, so a flag a long run lost cannot skip Cap 2 or the State 2 deduction:

```bash
uv run {scoringScript} --json-input '<the §3a JSON>' --coverage "{run_dir}/coverage.json" [--signatures "{run_dir}/signatures.json"] [--coherence "{run_dir}/coherence.json"] --external "{run_dir}/external.json" [--surface "{run_dir}/surface.json"] > "{run_dir}/score.json"
```

Where `{scoringScript}` is the path resolved from the frontmatter variable (relative to the skill root, i.e., the skf-test-skill/ directory).

Read its output from `{run_dir}/score.json`, where the report step's result contract reads `activeCategories` and `inconclusiveReasons` too. The script returns:
- `weights`: final redistributed weights per category
- `weightedScores`: weighted contribution per category
- `totalScore`: the overall completeness score
- `threshold`: the threshold used
- `result`: `"PASS"`, `"FAIL"`, or **`"INCONCLUSIVE"`** (the minimum-evidence floor)
- `activeCategories`: list of categories that were scored
- `skippedCategories`: list of categories that were skipped
- `skipReasons`: why each category was skipped
- `weightSum`: sum of final weights (should be ~100)
- `inconclusiveReasons`: only present when `result == "INCONCLUSIVE"`; explains which floor clause tripped
- `state2Deduction` and `scoringNotes`: present when the State 2 undercount deduction was weighed (`applied` says whether it lowered Export Coverage) and when a note applies
- **Verdict-override group**: present as an atomic set of four keys only when a post-score cap or the threshold fallback engaged (the script applies §3d and §4b):
  - `effectiveResult`: the **final verdict** after caps + fallback (`"PASS"` / `"FAIL"`)
  - `capReason`: string describing the cap(s) that fired, or `null`
  - `thresholdFallback`: `true` when the FAIL→PASS-at-80-floor fallback fired
  - `originalThreshold`: the pre-fallback threshold when `thresholdFallback` is `true`, else `null`
  - When the group is **absent**, no cap or fallback engaged and `result` is the final verdict.

**The script owns the minimum-evidence floor, the State 2 deduction, both post-score caps, and the threshold fallback: everywhere below, read its emitted fields (`result`, `effectiveResult`, `capReason`, `thresholdFallback`, `scoringNotes`) and never recompute a verdict, cap, deduction or threshold decision.** The **settled verdict** is `effectiveResult` when the override group is present, otherwise `result` (INCONCLUSIVE is never overridden). §6's settle writes it into the report, with the score, the threshold and the fields that follow from it.

#### 3c. If the Script Refuses the Input or Does Not Run

A `{"error": ..., "code": "INVALID_INPUT"}` envelope in `{run_dir}/score.json` (exit 2, or exit 1 for a payload that is not JSON) means the script ran and refused what it was given: a flag is missing, mistyped or out of range, or a score file is missing its score or holds a refused result. **Correct the §3a input, or re-run the step that writes the refused file, and run it again.** Never compute a total by hand from the numbers the script refused.

A refusal that names `docsOnly` and `--coverage`, or `state2` and `--surface`, means the §3a JSON contradicts what coverage-check found: build it again from the `{outputFile}` frontmatter and run it again. When the frontmatter holds the refused value too, the file decides: write `docsOnly: true` to the frontmatter for a `coverage.json` whose `denominatorSource` is `docsOnly` (else `false`), or `analysisConfidence: 'provenance-map'` for a `surface.json` whose `state2` holds counts, then build the JSON and run the script again.

No envelope at all (the script file is missing, or it cannot start): HALT with its stderr (`halt_reason: "helper-failed"`, phase `score:compute`). A quality gate does not score by hand, so the run stops without a score rather than with an unchecked one.

### 3d. Read Post-Score Caps (applied by the script)

The script applies **Cap 1** (any `toolingStatus` other than `ok`) and **Cap 2** (docs-only with no external validation score) and returns `capReason` and `effectiveResult` (§3b). A fired cap turns a PASS into FAIL and never touches an INCONCLUSIVE verdict, and the threshold fallback (§4b) never lifts it: a capped run stays FAIL whatever the threshold. If `capReason` is non-null, §6 shows it on its **Cap:** line, and §5 and §8 recommend restoring the tooling it names.

### 4. Determine Result (PASS / FAIL / INCONCLUSIVE)

The settled verdict is §3b's, and INCONCLUSIVE (the minimum-evidence floor, which `inconclusiveReasons` explains) is never overridden.

### 4b. Threshold Fallback

When `thresholdFallback` is true, the script accepted a FAIL at the 80% floor: `effectiveResult` is `"PASS"` and `originalThreshold` holds the target threshold. Bind `threshold_fallback: true` and `original_threshold` ← `originalThreshold` for §8. §6's settle records the fallback in the Completeness Score section's `### Threshold Fallback` subsection: the target, the script's raw `totalScore`, the floor it was accepted at, the threshold source, the latest earlier test report beside this one, or none found, and a pointer to the Gap Report, which report.md §4c renders from the gap ledger. No other file records it.

### 5. Determine Next Workflow Recommendation

Recommend the next workflow by the **settled verdict** (§3b); §6's settle writes the `nextWorkflow` that matches it.

**IF PASS:**
- Recommend export-skill: the skill is ready for export.
- **Drift override:** if the `{outputFile}` frontmatter's `workspaceDrift`
  is `overridden` (init.md §5b wrote it when the user passed
  `--allow-workspace-drift` AND the workspace HEAD did not match
  `metadata.source_commit`; the flag on a clean tree leaves it `ok`), the
  PASS is a **conditional PASS**: settle writes `pass-with-drift` as its
  `testResult` and `update-skill` as its `nextWorkflow`, and its Scoring
  Notes say so. **Refuse to recommend `export-skill`**: the drift override
  weakens the workflow's strongest false-positive guard (we tested against
  HEAD, not the pinned source); a PASS under drift is not trustworthy enough
  to promote to export without a clean re-test against the pinned commit.

**IF FAIL:**
- Recommend update-skill: the skill needs remediation before export.

**IF FAIL with a cap** (`capReason` is non-null: a cap fired, and no run passes until the tooling it names is restored):
- `nextWorkflow` stays `'update-skill'`, but no skill edit lifts a cap, so the step to recommend is to restore the tooling the cap names and test again. Cap 1 (`tooling degraded`): make the tool `toolingStatus` names work again; for `frontmatter-validator-timeout`, the frontmatter validator must finish within 30 seconds. Cap 2 (`docs-only without external validators`): make skill-check run and score the skill (the Gap Report's `skill-check not run` gap says how, when it did not run), or opt in to Tessl Review. When the script's `result` is `FAIL` too, the skill also scored below its threshold: recommend the **IF FAIL:** branch's update-skill as well, after restoring the tooling.

**IF INCONCLUSIVE:**
- Recommend manual review: the evidence base is too thin to grade the skill automatically. Surface the `inconclusiveReasons` the section lists to the user, and recommend neither export nor update.

### 6. Write the Completeness Score Section

`{resultContextScript}` (it resolves relative to the skill root) writes the verdict fields the scoring output settles into the `{outputFile}` frontmatter and prints the section from `{run_dir}/score.json`, `{run_dir}/external.json` and that frontmatter. Settle rewrites the report file, so once it exits 0, read `{outputFile}` again before you edit it, here and in §7: an edit made from the copy read before settle ran would undo the fields it wrote.

```bash
uv run {resultContextScript} settle --report "{outputFile}" --score "{run_dir}/score.json" --external "{run_dir}/external.json"
```

Exit 0: write its output unchanged as the **Completeness Score** section, in place of the template's `## Completeness Score` heading and the placeholder comment under it, in `{outputFile}`. Exit 2 is a usage error: correct the command and run it again. Exit 1 printed its error on stderr and left the report as it was: HALT with it (`halt_reason: "helper-failed"`, phase `score:settle`).

If the `analysisConfidence` §3a read is not `full`, add a degradation notice at the end of the Completeness Score section. **The notice must be confidence-aware** (see the degradation notice rules in `{sourceAccessProtocol}`):

```markdown
### Access Degradation Notice

**Resolved via:** {analysisConfidence} {at provenance-map, from `{run_dir}/access.json`: "(T1 AST-verified at compilation time)" when `degradation` is `all-t1`, else each `provenanceConfidence` label after its count, as "(12 T1, 3 T1-low)"}
**Impact:** {describe limitation, e.g., "Signature checks limited to name-matching. Source file:line citations from provenance-map, not live AST.", or "Provenance data is at highest confidence; no limitation." at provenance-map when `{run_dir}/access.json` `degradation` is `all-t1`}
**Recommendation:** {at provenance-map, the one the degradation notice rules in {sourceAccessProtocol} give `{run_dir}/access.json` `degradation` (no local clone for `all-t1`); at any other access, their `low` one}
```

### 7. Update Output Frontmatter

§6's settle wrote `testResult`, `score`, `threshold` (the one the verdict was settled against) and `nextWorkflow` and, after a threshold fallback, `thresholdFallback` and `originalThreshold`. Update the rest of the `{outputFile}` frontmatter:
- `analysisConfidence: '{full|provenance-map|metadata-only|remote-only|docs-only}'`
- Append `'score'` to `stepsCompleted`

### 8. Report Score

Report the completeness score to the user: the total percentage and PASS/FAIL verdict, the per-category weighted breakdown (already appended to the report in §6), the threshold on the section's **Threshold:** line (80 after a threshold fallback), and the next workflow §5 recommends. On a capped FAIL (§5's **IF FAIL with a cap** branch), show `capReason` and recommend restoring the tooling it names and testing again, not update-skill alone: `nextWorkflow` stays `update-skill`, but no skill edit lifts a cap, and update-skill is needed as well only when the script's `result` is `FAIL` too. When `threshold_fallback` is true, include the fallback notice:

**Threshold fallback:** scored {totalScore}% against {original_threshold}% target: accepted at 80% floor (the Completeness Score section's Threshold Fallback subsection has the details)

Then proceed to the gap report.

`stepsCompleted` now ends with `'score'` (§7 appended it), so load and execute {nextStepFile}.

