---
nextStepFile: 'report.md'
outputValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
securityScanProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-security-scan.py'
  - '{project-root}/src/shared/scripts/skf-security-scan.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runFile: '{run_dir}/run.json'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 8: Validate Output

## STEP GOAL:

Validate all written output files against their expected structure and verify confidence tier label completeness.

## Rules

- Validate structure and completeness, not content quality
- Only §3 writes to the committed package: `skill-check --fix` may rewrite `SKILL.md`, and a `body.max_lines` finding moves sections into `references/` (or runs `split-body --write`). Every other section leaves the package as step 7 committed it
- Advisory mode: always proceed to report regardless of findings

## MANDATORY SEQUENCE

### 1. Verify File Existence

Run the shared deterministic output validator once against the committed package and the run's workspace: it checks the three core deliverable files' existence, SKILL.md frontmatter, context-snippet format/token, the workspace files and the `active` link in a single call, so this step consumes its JSON rather than re-deriving those by hand. Resolve `{outputValidator}` from `{outputValidatorProbeOrder}` (first existing path wins). If neither candidate exists, log a WARNING (`"output validator unavailable: skf-validate-output.py missing"`) and fall back to the manual file/frontmatter/snippet checks below.

```bash
python3 {outputValidator} "{skill_package}" --generated-by create-stack-skill --skill-type stack --forge-tier {forge_tier} --forge-version "{forge_version}" --active-link "{skill_group}" --expected-version "{version}"
```

`{forge_tier}` is the `forge_tier` of `{runFile}`, the run tier step 1 saved.

Consume from its JSON:

- `files_found`: existence of `SKILL.md` / `context-snippet.md` / `metadata.json`.
- `validation.skill_md.frontmatter`: feeds the frontmatter check in §3 (manual-fallback path).
- `validation.context_snippet.issues`: feeds §8, the stack's `|stack:` and `|integrations:` line checks included.
- `validation.stack_counts`: the stack count-equalities, derived deterministically from disk + metadata by the `--skill-type stack` pass: `issues[]` (each `{severity, field, message}`, one per mismatch of `library_count` / `integration_count` / `confidence_distribution`; empty when all agree) and `observed` (`library_count_meta`, `ref_file_count`, `integration_count_meta`, `pair_file_count`, `confidence_sum`). §5 records its `library_count` and `integration_count` entries and §7 its `confidence_distribution` entry: do not re-count files or re-sum the distribution by hand.
- `validation.stack_structure`: the stack structure pass. The `check` of each `issues[]` entry (`{severity, check, field, message}`) names the section below that records it: `skill_md` (§4), `metadata` (§5), `references` (§6) or `tier_labels` (§7). Do not re-read the output files to check what it checks.
- `validation.stack_workspace`: the workspace and link pass: `issues[]` (each `{severity, field, message}`, one per file `{forge_version}` lacks, `provenance-map.json` or `evidence-report.md`, and one with `field: "active"` when `{skill_group}/active` is missing, broken or resolves to anything but `{version}`) and `observed`.

Under `--skill-type stack` the validator skips the individual-skill body and metadata passes (their `{"skipped": ...}` markers are no finding) and runs the `stack_counts` and `stack_structure` passes instead. When §3 changes the package it runs this command again, and §4 to §8 read the latest run. When the validator is unavailable, §4 to §7 each record one **WARNING** finding that their checks did not run.

Record each `files_found` file that is `false` and each `validation.stack_workspace.issues[]` entry as an **ERROR** finding.

When the validator is missing, confirm these rows by hand instead, and when its JSON has no `validation.stack_workspace` (an older installed validator), the Workspace and Symlink rows; record each miss as an **ERROR** finding:

**Deliverables** (`{skill_package}`):
- [ ] SKILL.md · context-snippet.md · metadata.json

**Workspace** (`{forge_version}`):
- [ ] provenance-map.json
- [ ] evidence-report.md

**Symlink:**
- [ ] `{skill_group}/active` exists and resolves to `{version}`

### 2. Check Tool Availability

Probe skill-check with `--no-install` to avoid cold-install hangs, wrap in a short timeout, and treat any hang or non-zero exit as unavailable:

```bash
timeout 10s npx --no-install skill-check -h
```

- If exits 0: Use skill-check for automated validation in section 3.
- If exits non-zero, times out, or returns "command not found": Use manual fallback paths, append a `workflow_warnings[]` entry (`step: "step-08"`, `severity: "warn"`, `code: "skill-check-unavailable"`, `message: "skill-check unavailable: manual fallback checks used"`) so step 9 does not report the run as skill-check validated, recording it at once (write its `[step-08/warn] skill-check-unavailable: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound), and list every skipped check in the §10 validation results.

### 3. Validate SKILL.md via skill-check (if available)

**If available**, resolve `{hashContentHelper}` ← first existing path in `{hashContentProbeOrder}`, then run in order: `uv run {hashContentHelper} hash <skill-dir>/SKILL.md`, `npx skill-check check <skill-dir> --fix --format json --no-security-scan`, then `uv run {hashContentHelper} hash <skill-dir>/SKILL.md` again, keeping the `content_hash` each `hash` call prints.

This validates frontmatter, description, body limits, links and formatting, and auto-fixes deterministic issues. Parse JSON for `scores[].score` (match the entry by `relativePath`/`skillId`; falls back to a top-level `qualityScore` on older skill-check builds) and `diagnostics[]`. skill-check's JSON lists no fix: SKILL.md changed across the `--fix` call when the two `content_hash` values differ, and is taken as changed, not hashed, when no `{hashContentProbeOrder}` path exists (run the skill-check call alone) or a `hash` call prints no `content_hash`.

Bind `{quality_score}` ← that score, from the latest skill-check run (§3 runs it again after a split); `{quality_score}` is null when skill-check is unavailable. It is the skill-check score, not a test-skill score, and step 9 puts it in the result envelope and the result contract.

**Post-fix provenance drift guard:** When SKILL.md changed across the `--fix` call, `skill-check --fix` modified it after step 7 wrote it, so the `metadata.json` hashes and provenance recorded against the earlier body may now be stale. Emit one **WARNING** finding, `"skill-check --fix modified SKILL.md after step 7 wrote it: metadata.json hashes and provenance may be out of date"` (`"SKILL.md may have been rewritten (not hashed) by skill-check --fix after step 7 wrote it: metadata.json hashes and provenance may be out of date"` when SKILL.md was not hashed), rather than silently accepting the fix, so the drift is surfaced. If the caller wants authoritative metadata, they should re-run the workflow.

**If `body.max_lines` reported**, prefer selective split: extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 content inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). For a stack capstone the canonical split is the catalog (`Library Reference Index` + `Per-Library Summaries`) → `references/stack-catalog.md`, leaving an inline pointer (see `{stackSkillTemplatePath}` "Sizing Guidance"). The moved catalog's links resolve from `references/`, so rewrite each `[ref](references/{name}.md)` in it to `[ref]({name}.md)`. This is the **intended** large-stack layout: §4 below accepts the pointer form, so clearing the skill-check body ERROR this way does not also trip the structure check. Fall back to `npx skill-check split-body <skill-dir> --write` if not feasible. After the split, verify that any in-SKILL.md anchor links (e.g. to the catalog/pointer or other moved sections) still resolve, and that every link inside a moved section resolves from its new file.

**Re-validate a changed package.** When SKILL.md changed across the `--fix` call (not hashed included) or a split ran, run the §1 `{outputValidator}` command again (after a split, skill-check too), so §4 to §8 record the package as it now stands.

**If unavailable**, do not hand-walk the frontmatter: use `validation.skill_md.frontmatter` from the §1 output-validator run, which checks delimiters, `name` format + directory match (`{stack_name}`), `description` presence/length, and unknown fields against the agentskills.io allow-set. Record each reported issue at its severity as a **WARNING** finding. (If the output validator was *also* unavailable in §1, fall back to the manual checklist: `---` delimiters; `name` lowercase-alphanumeric-plus-hyphens 1-64 chars matching `{stack_name}`; `description` present and 1-1024 chars; only `name`/`description`/`license`/`compatibility`/`metadata`/`allowed-tools` permitted.) Invalid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 4. Validate SKILL.md Body Structure

Record each `validation.stack_structure.issues[]` entry whose `check` is `skill_md` as a **WARNING** finding. The catalog's pointer form (a `## Library Catalog` section linking `references/stack-catalog.md`) is the intended large-stack layout (§3), not a violation.

### 5. Validate metadata.json Fields

Record each `validation.stack_structure.issues[]` entry whose `check` is `metadata`, and each `library_count` or `integration_count` entry of `validation.stack_counts.issues[]`, from the latest output-validator run as a **WARNING** finding.

### 6. Validate Reference File Completeness

Record each `validation.stack_structure.issues[]` entry whose `check` is `references` as a **WARNING** finding.

### 7. Validate Confidence Tier Labels

Record each `validation.stack_structure.issues[]` entry whose `check` is `tier_labels`, and the `confidence_distribution` entry of `validation.stack_counts.issues[]`, from the latest output-validator run as a **WARNING** finding.

### 8. Validate context-snippet.md

Record each `validation.context_snippet.issues` entry as a **WARNING** finding. Its `length` entries use the validator's <40 / >300 bounds: the 120-token budget is step 7 §5's, which records `snippet-over-budget` for a snippet it could not trim under it.

When the validator is missing, check these rows by hand instead, and when its JSON has no `validation.stack_workspace` (an older installed validator, which checks no stack line), the second row; record each miss as a **WARNING** finding:
- [ ] Line 1 is `[{stack_name} v{version}]|root: skills/{stack_name}/` and line 2 starts with `|IMPORTANT:`
- [ ] A `|stack:` line and an `|integrations:` line are present

### 9. Security Scan

Run the scan whether or not skill-check is available. Resolve `{securityScanHelper}` ← first existing path in `{securityScanProbeOrder}` and run it on the committed package, with the longest timeout your shell tool takes (it ends within two minutes):

```bash
uv run {securityScanHelper} run --package "<skill-dir>"
```

It runs Snyk Agent Scan, at the version it pins, only when `SNYK_TOKEN` is set, and reads the scanner's own JSON report, so rely on the JSON it prints, never on an exit code. Record each `findings[]` entry's `text` as an advisory **WARNING** finding: security findings do not block the report. Record its `note` in the §10 validation results, as "security scan: {note}" for `pass` and `warn` and as "security scan skipped: {note}" for `skipped`. When no `{securityScanProbeOrder}` path exists, record no finding, only the §10 note "security scan skipped: skf-security-scan.py missing"; when the call prints no JSON object, the note "security scan skipped: skf-security-scan.py printed no result".

Bind `{security_result}` ← the helper's `security_result` (`pass`, `warn` or `skipped`), or `skipped` when the helper is missing or printed no JSON object. Step 9 puts it in the result envelope and the result contract.

### 10. Display Validation Results

Report the validation outcome. If all checks passed, state so and name what was verified: file presence (`{count}/{count}`), SKILL.md structure, metadata.json fields, the `{lib_count}` library + `{pair_count}` integration reference files, and complete confidence-tier coverage. If there were findings, report the `{warning_count}` finding(s), each with severity, description, and file path, plus files present/expected and warning/error counts; when errors include missing files, note this may indicate a write failure in step 07. In both cases, list each §9 security scan note.

### 11. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

