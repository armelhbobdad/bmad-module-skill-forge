---
nextStepFile: 'validate.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — stage/commit/flip-link/write below
# MUST go through the atomic helper, per §1 rollback contract.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Advisory: see §8.
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
# Resolve `{skillInventoryHelper}` by probing `{skillInventoryProbeOrder}` in
# order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. §1 runs its write check before any directory is
# created; without it, §1 writes only into a skill folder that does not exist yet.
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
# Advisory: see §7.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# Advisory: see §8.
namesPresentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-names-present.py'
  - '{project-root}/src/shared/scripts/skf-names-present.py'
# Advisory: see §8b.
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 7: Generate Output Files

## STEP GOAL:

Write all deliverable and workspace artifact files to their target directories.

## Rules

- Write all output files in correct directory structure. Keep the compiled content from Step 06 as approved, except for the fixes the §8 pre-commit gate makes in staging
- Create directory structure before writing files
- Report each file written with path and size

## MANDATORY SEQUENCE

### 1. Resolve Paths and Stage Target Directory

Resolve `{version}` per S11 below — the primary library version in code-mode, or the stack-local scheme in compose-mode (`1.0.0` for a new stack, or a bump of `{prior_stack_version}` on re-composition). The final artifact paths are:

```
{skill_group}                          # {skills_output_folder}/{project_name}-stack/
{skill_package}                        # {skills_output_folder}/{project_name}-stack/{version}/{project_name}-stack/
├── references/
│   └── integrations/
{forge_version}                        # {forge_data_folder}/{project_name}-stack/{version}/
```

Where the skill name is `{project_name}-stack` and `{version}` is the semver version (with build metadata stripped per `knowledge/version-paths.md`).

**Primary library definition (S11):** In code-mode, the primary library is the dependency with the highest import count from step 3; its `version` (from the manifest) becomes `{primary_library_version}`, falling back to `1.0.0` if unavailable. In compose-mode, the stack carries its own release identity: default `{version}` to `1.0.0` (a stack-local scheme) rather than borrowing the highest constituent semver. Constituent versions are preserved in `dependencies[]`, so no information is lost, and the stack's version does not track whichever constituent happens to have the highest version. The `1.0.0` default applies only to a **genuinely new** stack — see the re-composition rule below.

**Re-composition versioning (S11, compose-mode):** When the S3 pre-flight resolves a `{prior_stack_version}` (re-composing a stack that already has a release line), continue that line instead of resetting — defaulting to `1.0.0` would publish a version *below* the existing release (e.g. `1.0.0` shadowing a prior `3.0.5`, a backward jump). Bump `{prior_stack_version}`:

- **Major** if any library in `{prior_libraries}` is removed or replaced — dropping a documented library is breaking for consumers of the stack.
- **Minor** otherwise — libraries only added, and/or integration content changed (backward-compatible).

Never emit a `{version}` ≤ `{prior_stack_version}`. Narrate the resolved version and the bump rationale.

**Pre-flight: ownership, phase 1 (S3).** `{stack_name}` is `{project_name}-stack`. Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` and run, before any prior metadata is read:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {stack_name} --write-check --forge-data-folder {forge_data_folder}
```

Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder`, `{write_detail}` ← `write_check.detail` and `{prior_active_version}` ← `write_check.marked_active_version`, and apply the ownership refusals below.

When `{prior_active_version}` is not null, read `{skills_output_folder}/{stack_name}/{prior_active_version}/{stack_name}/metadata.json`. If its `skill_type` is not `"stack"`, HALT with:

"**Cannot proceed.** `{skills_output_folder}/{project_name}-stack/` exists but is not a stack skill (`skill_type={found_type}`). Rename the existing directory or choose a different `project_name` to avoid collision."

Do NOT proceed to staging or commit. Emit the result envelope on stderr per the Result Contract in SKILL.md and exit `4` (`stack_libraries` carries the confirmed library names; nothing was committed, so `skill_package` is `null`):

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":["<confirmed-lib>", "..."],"mode":"{code|compose}","exit_code":4,"halt_reason":"write-failure"}
```

Otherwise this run is a **re-composition**: capture its `version` as `{prior_stack_version}` and its `libraries` array as `{prior_libraries}` for the S11 re-composition rule above. When `{prior_active_version}` is null — the group is absent, holds only what an interrupted run leaves, or its `active` link names no version SKF generated — treat this as a new stack and leave `{prior_stack_version}` unset: prior metadata is read only from a version SKF generated.

**Pre-flight: ownership, phase 2.** Once `{version}` is resolved (S11), and before `stage-dir` and `mkdir -p {forge_version}` below, run the same command with `--write-version {version}`:

```bash
uv run {skillInventoryHelper} {skills_output_folder} --skill {stack_name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}
```

and apply the same bindings and refusals.

**Ownership refusals (both phases).** Bind `{write_verdict}` ← `write_check.verdict`, `{write_folder}` ← `write_check.folder` and `{write_detail}` ← `write_check.detail`. Continue only when the status is `ok` and `{write_verdict}` is `"ok"`: nothing is at the skill folder yet, it holds only what an interrupted run leaves, or SKF generated it and the version is new or SKF's own. Otherwise create nothing and refuse with the first case that applies:

- `{write_verdict}` is `"flat-layout"` → `halt_reason: "flat-layout"`: "**`{stack_name}` still uses the flat layout — nothing was written.** A version written beside its root `SKILL.md` would leave a skill SKF can no longer migrate or rename. Run `@Ferris TS {stack_name}` (or US, AS or EX) once to move it into the versioned layout, then re-run."
- `{write_verdict}` is `"not-skf-output"` → `halt_reason: "not-skf-output"`: "**`{stack_name}` is not SKF output — nothing was written.** `{write_folder}` {write_detail}, so SKF will not write a version there. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{stack_name}` yourself, and choose a different `project_name` to create this stack beside it. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`. A version folder with no `metadata.json` can also be one that an interrupted create-stack-skill run left behind; delete it yourself in that case."
- The status is not `ok`, or the output has no `write_check` (an older helper: it has no `--write-check` and reports a new skill as `SKILL_NOT_FOUND`) → `halt_reason: "not-skf-output"`: the same message with "SKF could not check it ({the helper's `error`, if any}; re-install SKF if the installed `skf-skill-inventory.py` is out of date)" in place of "`{write_folder}` {write_detail}".
- When no helper candidate resolves, continue only when nothing exists at `{skill_group}` (no folder, no file, not even a broken link). Otherwise refuse with `halt_reason: "not-skf-output"` and the same message, giving "SKF cannot check who generated `{skill_group}`: `skf-skill-inventory.py` is missing; re-install SKF" in place of "`{write_folder}` {write_detail}". Here `{skill_group}` is `{skills_output_folder}/{stack_name}`.

Each refusal is a HARD HALT: do NOT proceed to staging; emit the result envelope on stderr and exit `5`:

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{stack_name}","stack_libraries":["<confirmed-lib>", "..."],"mode":"{code|compose}","exit_code":5,"halt_reason":"not-skf-output"}
```

(`"halt_reason":"flat-layout"` for the flat-layout refusal.)

**Atomic write strategy (C2 / B5):** All artifact writes for `{skill_package}` MUST stage into a temp directory first, then commit atomically via `skf-atomic-write.py commit-dir`. The active symlink flip only happens AFTER the commit succeeds.

Create the staging directory:

```bash
python3 {atomicWriteHelper} stage-dir --target {skill_package}
```

After this call, writes land in `{skill_package}.skf-tmp/` (referred to below as `{skill_staging}`). Create the required subdirectories inside the staging dir:

```bash
mkdir -p {skill_staging}/references/integrations
```

Also create the forge workspace directory directly (these are workspace artifacts, not deliverables — they do not need stage-dir / commit-dir):

```bash
mkdir -p {forge_version}
```

**Rollback contract:** If ANY write in sections 2–8b below fails, immediately run:

```bash
python3 {atomicWriteHelper} commit-dir --rollback --target {skill_package}
```

Then abort (see B7): purge any `{forge_version}/*-tmp` staging artifacts, emit the result envelope on stderr per the Result Contract in SKILL.md, and halt the workflow. This is the single rollback exit shared by §7 and §8b (workspace-write failures) and §9 (commit-dir failure):

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":["<confirmed-lib>", "..."],"mode":"{code|compose}","exit_code":4,"halt_reason":"write-failure"}
```

### 2. Stage SKILL.md

Write the approved `skill_content` from step 06 to `{skill_staging}/SKILL.md` (regular write — the whole staging dir will be atomically committed later).

### 3. Stage Per-Library Reference Files

For each confirmed library, write `{skill_staging}/references/{library_name}.md`:

Load structure from `{stackSkillTemplatePath}` references section:
- Library name, version from manifest (**in compose-mode**: version from source skill `metadata.json`)
- Import count and file count (**in compose-mode**: export count from source skill metadata)
- Key exports with signatures
- Usage patterns with file:line citations (**in compose-mode**: usage patterns from source skill SKILL.md)
- Confidence tier label

**If the catalog was extracted** (large stack: step 06 §4 placed the `Library Reference Index` + `Per-Library Summaries` out of SKILL.md), also write `{skill_staging}/references/stack-catalog.md` using the structure in `{stackSkillTemplatePath}`, and confirm SKILL.md carries the inline pointer instead of the two sections. The catalog sits in `references/`, so its links to the per-library files are file-relative, `[ref]({name}.md)`: a `references/{name}.md` link there would resolve to `references/references/{name}.md`. Small stacks keep the catalog inline and write no `stack-catalog.md`.

### 4. Stage Integration Pair Reference Files

For each detected integration pair, write `{skill_staging}/references/integrations/{libraryA}-{libraryB}.md`:

Load structure from `{stackSkillTemplatePath}` integrations section:
- Library pair and integration type
- Co-import file count
- Integration pattern description with file:line citations
- Usage convention
- Confidence tier label

**If no integrations detected:** Skip this section (no files to write).

### 5. Stage context-snippet.md

Write `{skill_staging}/context-snippet.md`:

Use the Vercel-aligned indexed format targeting **~80-120 tokens** (M2). Token estimation is heuristic — use `ceil(char_count / 4)` as the working approximation (the standard rule-of-thumb for English text in BPE-style tokenizers; precise counts differ per model). Compute against the rendered snippet body (excluding trailing newline).

```
[{project_name}-stack v{version — resolved in §1}]|root: skills/{project_name}-stack/
|IMPORTANT: {project_name}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {1-2 most critical integration pitfalls}
```

**Overflow strategy (M2):** If the estimated token count exceeds **120 tokens**, trim in this fixed order until under budget:

1. **Drop the `gotchas` line first.** Pitfalls live in SKILL.md and references; the snippet's job is discovery, not full warning surface.
2. **Strip versions from the `stack` line** (`{dep-1}, {dep-2}` instead of `{dep-1}@{v1}`). Versions are recoverable from `metadata.json`.
3. **Truncate the `stack` list to the top 8 dependencies by import count** (or by export count in compose-mode), appending `, ...+{N} more`.
4. **Truncate the `integrations` list to the top 5 by file count**, appending `, ...+{N} more`.

If the snippet is still over budget after step 4, log a warning to workflow_warnings (see Workflow Rules in SKILL.md) — do not block the write. The `IMPORTANT:` line is mandatory and never trimmed.

**Underflow note:** Snippets below ~80 tokens are acceptable (small stacks naturally produce short snippets). The lower bound is informational, not enforced.

### 6. Stage metadata.json

Write `{skill_staging}/metadata.json`, populating every field from the metadata.json schema in `{stackSkillTemplatePath}` (loaded in §3) — that template is the single schema source; do not re-transcribe it here. Resolve the field values whose template placeholders don't spell out the rule:

- `version` — the `{version}` resolved in §1 (not the template's literal `1.0.0`, which is only the new-stack default).
- `forge_tier` — the run tier (Quick/Forge/Forge+/Deep) resolved in step 1.
- `confidence_distribution`: each library in `libraries[]` counted once, in the bin of its `per_library_extractions[].confidence` (step 4 sets it), so the four bins sum to `library_count`. Only the evidence report bins provenance entries (§8b).
- `confidence_tier` — the dominant T-code from `confidence_distribution`. Pick the tier with the highest count; resolve ties toward the weaker tier (T1-low > T1, T2 > T1-low, T3 > T2) so the reported value never overstates confidence. When `confidence_distribution` is empty (no libraries extracted), emit `"T1-low"` as the conservative default.
- `source_authority` — the lowest authority among constituent skills (official > community > internal).

### 7. Write Forge Data Artifacts (Workspace)

Write workspace artifacts directly to `{forge_version}` (they are workspace-only, not part of the skill package, so they need no staging). Each individual file MUST be written via `skf-atomic-write.py write` to avoid partial-write corruption. This section writes `provenance-map.json` and, in code mode, checks its source lines; §8b writes `evidence-report.md` after the §8 gate, so the report lists the warnings both record:

```bash
<json-content> | python3 {atomicWriteHelper} write --target {forge_version}/provenance-map.json
```

If any workspace write fails, invoke the rollback contract from §1.

**provenance-map.json:**

Use the schema from `{provenanceMapSchemaPath}` — see that asset for the canonical templates and field definitions of both variants:

- **In code-mode:** use the code-mode variant (`source_repo` / `source_commit` populated; `detection_method = "co-import grep"`), with one entry per export record step 4 checked, its fields as recorded and `source_library` set to its library.
- **In compose-mode:** use the compose-mode variant (source-anchor fields `null`; `extraction_method = "compose-from-skill"`; `detection_method ∈ "architecture_co_mention|constituent_documented_contract|inferred_from_shared_domain"`; includes the additional `constituents[]` array for drift detection). Each entry's `confidence` and `signature_source` are its constituent's tier (`per_library_extractions[].confidence`), and its `export_name` is the literal identifier of the cited contract as the staged `SKILL.md` or a `.md` file directly in `references/` writes it, never a descriptive label or a name written only in `references/integrations/` (§8 checks it).

Populate compose-mode `constituents[].metadata_hash` from the value stored in workflow state at step 2 (S13), not a fresh re-hash at step-7 time — `{provenanceMapSchemaPath}` carries the rationale for why the manifest-detection-time hash is the correct provenance anchor.

**Source lines (code mode only).** The provenance verifier checks that each entry's `source_line` is the line that defines its export (a `def` recorded on its decorator line is not). Resolve `{verifyProvenanceCompletenessHelper}` from `{verifyProvenanceCompletenessProbeOrder}` and run `verify`, then `fix`, which moves each `source_line` to its export's definition line when the file has exactly one, then `verify` once more. `{scan_root}` is the project root, `project_root` from step 1, which each `source_file` is relative to:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata {skill_staging}/metadata.json \
    --provenance {forge_version}/provenance-map.json \
    --source-root {scan_root} \
    -o {forge_version}/provenance-verify.skf-tmp
uv run {verifyProvenanceCompletenessHelper} fix \
    --verify {forge_version}/provenance-verify.skf-tmp \
    --provenance {forge_version}/provenance-map.json \
    --skill-dir {skill_staging}
```

Rely on each call's JSON, not its exit code (`1` means findings, or items `fix` left), and ignore `missing` and `orphaned`: a stack's `exports` is `[]` by design. Append one `workflow_warnings[]` entry (`step: "step-07"`, `severity: "info"`, `code: "provenance-lines-fixed"`) naming each line `fix` moved (its `applied[]`), and one (`severity: "warn"`, `code: "provenance-line-unverified"`, `message`: its `export_name`, `source_file`, `source_line`, `reason` and `definition_lines`) for each `stale[]` item the last `verify` reports, for a person to decide. When neither probe path exists, a call exits `2` (no JSON) or `summary.stale_check` is `skipped-no-source-root`, append one entry (`step: "step-07"`, `severity: "warn"`, `code: "provenance-lines-unchecked"`, `message`: the reason) instead and end the check. Delete `{forge_version}/provenance-verify.skf-tmp` when the check ends.

### 8. Pre-Commit Gate

Step 8 validates only after commit-dir and flip-link have published the package, so catch here, while it is staged, the `skill-check` rejects `--fix` cannot correct: a `description` over 1024 characters and a body over `body.max_lines` (500). Resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}` and run it on the **staged** `SKILL.md`, with the real skill name so the `.skf-tmp` suffix does not fail the directory-match check:

```bash
uv run {frontmatterValidator} {skill_staging}/SKILL.md --skill-dir-name {project_name}-stack --max-body-lines 500 --max-body-tokens 5000
```

Act on the `issues[]` severities in its JSON, not on the exit code (an over-long `description` is `medium` and exits `0`):

- **`status` is `fail`, or an issue is `high` or `medium`:** HALT-to-fix **in staging** and re-run the validator until it clears; do NOT proceed to §8b or the §9 commit-dir before then. Remediate by `field`:
  - `description` / `name` / `compatibility`: correct `{skill_staging}/SKILL.md` (shorten `description` to ≤ 1024 chars).
  - `body` (`body lines N exceeds max 500`): prefer a **selective split** of the largest Tier-2 section(s) into `{skill_staging}/references/`, keeping Tier-1 content inline (as `validate.md` §3 does), or trim redundant content.
    When the split moves the catalog into `{skill_staging}/references/stack-catalog.md`, rewrite each `[ref](references/{name}.md)` in it to `[ref]({name}.md)`, as §3 above does for a catalog step 06 extracted.
- **Only `low` issues** (an unexpected field, or `body token estimate N exceeds max 5000`, a char/4 estimate that `skill-check` only warns on): append each to `workflow_warnings[]` (`step: "step-07"`, `severity: "warn"`, `code: "pre-commit-gate-issue"`, `message`: the issue's `field` and `message`) and proceed.

**If `{frontmatterValidator}` does not resolve or cannot run**, append a `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `code: "pre-commit-gate-skipped"`, `message: "pre-commit frontmatter + body-size gate skipped: validator unavailable"`) and proceed: step 8 remains the post-commit backstop.

**Compose-mode export names (compose mode only).** `skf-test-skill` credits a compose-mode entry toward Export Coverage only when the package writes its `export_name`. Resolve `{namesPresentHelper}` from `{namesPresentProbeOrder}` and run:

```bash
uv run {namesPresentHelper} --provenance {forge_version}/provenance-map.json --skill-dir {skill_staging}
```

Its `absent[]` lists each entry (`entry_index`, `export_name`, `source_library`) whose name `skf-test-skill` would not find in the staged package; when it is empty, go on to §8b. Otherwise, when `{headless_mode}` is false, set the `export_name` of each absent entry whose contract a staged file names by a literal identifier (a descriptive label was recorded in its place) to that identifier, and rewrite the map with the atomic writer as §7 does. Then, in both modes, run the call again with `--drop-absent`, which drops every entry still absent and rewrites the map. Append a `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `message`: its `source_library` and `export_name`, the old and the new one for a rename) per renamed entry (`code: "compose-export-name-renamed"`) and per `dropped[]` entry (`code: "compose-export-name-dropped"`). If neither probe path exists or a run exits `2` (no JSON), append one `compose-export-names-unchecked` entry with the reason.

### 8b. Write the Evidence Report (Workspace)

Now that the §8 gate has recorded its warnings, bin the final map's entries by `signature_source` for the report, in both modes. Resolve `{renderMetadataStatsHelper}` from `{renderMetadataStatsProbeOrder}` and run:

```bash
echo '{}' | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json --shape stack
```

Then write `evidence-report.md` to `{forge_version}` the same way as §7, through the atomic writer and with no staging:

```bash
<md-content> | python3 {atomicWriteHelper} write --target {forge_version}/evidence-report.md
```

If the write fails, invoke the rollback contract from §1.

**evidence-report.md:**
- Extraction summary per library, with its tier
- Integration detection results per pair
- Warnings and failures encountered, including every `workflow_warnings[]` entry recorded so far (the §7 line check's and the §8 gate's among them)
- Confidence tier distribution: the helper's `confidence_distribution`, one count per provenance entry (`metadata.json` counts libraries, §6), or "not computed" when the helper is missing or exits `2`

### 9. Commit Staging Directory

After all staged writes in sections 2–6 completed successfully, atomically swap the staging dir into place:

```bash
python3 {atomicWriteHelper} commit-dir --target {skill_package}
```

The helper moves any existing `{skill_package}` aside to a `.skf-rollback-<pid>` dir before the swap. On failure the helper restores the prior target and exits non-zero — in that case invoke the rollback contract from §1 and HALT.

### 10. Flip Active Symlink

ONLY AFTER `commit-dir` succeeds, flip the `{skill_group}/active` symlink to point at `{version}`:

```bash
python3 {atomicWriteHelper} flip-link --link {skill_group}/active --target {version}
```

The helper holds an flock on `{skill_group}/active.skf-lock` and refuses to replace a non-symlink at `{skill_group}/active` — this guards against accidentally overwriting a real directory (ECH BLOCKER 6/B6). After the flip, `{skill_group}/active/{project_name}-stack/` resolves to the just-committed skill package.

If `flip-link` fails, append a `workflow_warnings[]` entry (`step: "step-07"`, `severity: "warn"`, `code: "flip-link-failed"`, `message`: the helper's error) and continue. The committed package is still valid, and step 9 lists the warning, since §8b has already written the evidence report.

### 11. Display Write Summary

Report the files written: the `{skill_package}` deliverables (SKILL.md with `{line_count}` lines, context-snippet.md with `{token_estimate}` tokens, metadata.json, `references/` `{lib_count}` library files, `references/integrations/` `{pair_count}` integration files), the `{forge_version}` workspace (provenance-map.json, evidence-report.md), the `{skill_group}/active -> {version}` symlink, and the `{total_count}` total.

### 12. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

