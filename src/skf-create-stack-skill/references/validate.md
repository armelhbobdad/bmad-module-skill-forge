---
nextStepFile: 'report.md'
outputValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
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

Run the shared deterministic output validator once against the committed package — it checks the three core deliverable files' existence, SKILL.md frontmatter, and context-snippet format/token in a single call, so this step consumes its JSON rather than re-deriving those by hand. Resolve `{outputValidator}` from `{outputValidatorProbeOrder}` (first existing path wins). If neither candidate exists, log a WARNING (`"output validator unavailable — skf-validate-output.py missing"`) and fall back to the manual file/frontmatter/snippet checks below.

```bash
python3 {outputValidator} {skill_package} --generated-by create-stack-skill --skill-type stack --forge-tier {forge_tier}
```

Consume from its JSON:

- `files_found` — existence of `SKILL.md` / `context-snippet.md` / `metadata.json` (the three core deliverable rows below).
- `validation.skill_md.frontmatter` — feeds the frontmatter check in §3 (manual-fallback path).
- `validation.context_snippet.issues` — feeds §8.
- `validation.stack_counts` — the stack count-equalities, derived deterministically from disk + metadata by the `--skill-type stack` pass: `issues[]` (each `{severity, field, message}`, one per mismatch of `library_count` / `integration_count` / `confidence_distribution`; empty when all agree) and `observed` (`library_count_meta`, `ref_file_count`, `integration_count_meta`, `pair_file_count`, `confidence_sum`). Feeds the count rows in §5 and the confidence-sum row in §7 — do not re-count files or re-sum the distribution by hand.
- `validation.stack_structure`: the stack structure pass. The `check` of each `issues[]` entry (`{severity, check, field, message}`) names the section below that records it: `skill_md` (§4), `metadata` (§5), `references` (§6) or `tier_labels` (§7). Do not re-read the output files to check what it checks.

Under `--skill-type stack` the validator skips the individual-skill body and metadata passes (their `{"skipped": ...}` markers are no finding) and runs these two instead. When §3 changes the package it runs this command again, and §4 to §8 read the latest run. When the validator is unavailable, §4 to §7 each record one **WARNING** finding that their checks did not run.

Then confirm the remaining files the validator does not cover:

**Deliverables** (`{skill_package}`):
- [ ] SKILL.md · context-snippet.md · metadata.json — from `files_found` above
- [ ] references/ directory with per-library files
- [ ] references/integrations/ directory with pair files (if integrations detected)

**Workspace** (`{forge_version}`):
- [ ] provenance-map.json
- [ ] evidence-report.md

**Symlink:**
- [ ] `{skill_group}/active` exists and resolves to `{version}`

Record any missing files (from `files_found` or the manual rows) as **ERROR** findings.

### 2. Check Tool Availability

Probe skill-check with `--no-install` to avoid cold-install hangs, wrap in a short timeout, and treat any hang or non-zero exit as unavailable (S14):

```bash
timeout 10s npx --no-install skill-check -h
```

- If exits 0: Use skill-check for automated validation in sections 3, 9.
- If exits non-zero, times out, or returns "command not found": Use manual fallback paths, append a `workflow_warnings[]` entry (`step: "step-08"`, `severity: "warn"`, `code: "skill-check-unavailable"`, `message: "skill-check unavailable: manual fallback checks used, security scan skipped"`) so step 9 does not report the run as skill-check validated, and list every skipped check in the §10 validation results.

**Important:** Do not assume availability — empirical check required.

### 3. Validate SKILL.md via skill-check (if available)

**If available**, run: `npx skill-check check <skill-dir> --fix --format json --no-security-scan`

This validates frontmatter, description, body limits, links, formatting — and auto-fixes deterministic issues. Parse JSON for `scores[].score` (match the entry by `relativePath`/`skillId`; falls back to a top-level `qualityScore` on older skill-check builds), `diagnostics[]`, `fixed[]`.

**Post-fix provenance drift guard (S15):** If `fixed[]` is non-empty, `skill-check --fix` has modified `SKILL.md` after step 7 wrote it — so the `metadata.json` hashes/provenance recorded against the pre-fix body may now be stale. Emit a **WARNING** finding listing each auto-fix (`"skill-check --fix modified SKILL.md: {fix_description} — metadata.json hashes/provenance may be out of date"`) rather than silently accepting the fixes, so the drift is surfaced. If the caller wants authoritative metadata, they should re-run the workflow.

**If `body.max_lines` reported**, prefer selective split: extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 content inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). For a stack capstone the canonical split is the catalog (`Library Reference Index` + `Per-Library Summaries`) → `references/stack-catalog.md`, leaving an inline pointer (see `{stackSkillTemplatePath}` "Sizing Guidance"). The moved catalog's links resolve from `references/`, so rewrite each `[ref](references/{name}.md)` in it to `[ref]({name}.md)`. This is the **intended** large-stack layout, not a violation: §4 below accepts the pointer form, so clearing the skill-check body ERROR this way does not also trip the structure check. Fall back to `npx skill-check split-body <skill-dir> --write` if not feasible. After the split, verify that any in-SKILL.md anchor links (e.g. to the catalog/pointer or other moved sections) still resolve, and that every link inside a moved section resolves from its new file.

**Re-validate a changed package.** When `fixed[]` is non-empty or a split ran, run the §1 `{outputValidator}` command again (after a split, skill-check too), so §4 to §8 record the package as it now stands.

**If unavailable**, do not hand-walk the frontmatter — use `validation.skill_md.frontmatter` from the §1 output-validator run, which checks delimiters, `name` format + directory match (`{project_name}-stack`), `description` presence/length, and unknown fields against the agentskills.io allow-set. Record each reported issue at its severity as a **WARNING** finding. (If the output validator was *also* unavailable in §1, fall back to the manual checklist: `---` delimiters; `name` lowercase-alphanumeric-plus-hyphens 1-64 chars matching `{project_name}-stack`; `description` present and 1-1024 chars; only `name`/`description`/`license`/`compatibility`/`metadata`/`allowed-tools` permitted.) Invalid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 4. Validate SKILL.md Body Structure

Record each `validation.stack_structure.issues[]` entry whose `check` is `skill_md` as a **WARNING** finding. The catalog's pointer form (a `## Library Catalog` section linking `references/stack-catalog.md`) is the intended large-stack layout (§3), not a violation.

### 5. Validate metadata.json Fields

Record each `validation.stack_structure.issues[]` entry whose `check` is `metadata` as a **WARNING** finding.

**Count equalities (library / integration):** do NOT re-count files here; take them from `validation.stack_counts` in the latest output-validator run (§1, or §3's re-run), which derived them deterministically from disk. The `library_count` vs per-library reference files and `integration_count` vs integration pair files checks surface as `field: "library_count"` / `field: "integration_count"` entries in `validation.stack_counts.issues[]` (absent when they agree); echo the exact numbers from `validation.stack_counts.observed` (`library_count_meta` / `ref_file_count`, `integration_count_meta` / `pair_file_count`). The `confidence_distribution`-sum equality is covered in §7.

Record each `validation.stack_counts.issues[]` count entry (`library_count` / `integration_count`) as a **WARNING** finding.

### 6. Validate Reference File Completeness

Record each `validation.stack_structure.issues[]` entry whose `check` is `references` as a **WARNING** finding.

### 7. Validate Confidence Tier Labels

Record each `validation.stack_structure.issues[]` entry whose `check` is `tier_labels` as a **WARNING** finding.

- [ ] metadata.json: `confidence_distribution` sums to `library_count`: take this from the latest output-validator run (`--skill-type stack`): the `field: "confidence_distribution"` entry in `validation.stack_counts.issues[]` is present only on mismatch, with `validation.stack_counts.observed.confidence_sum` vs `library_count_meta` for the exact numbers. Do not re-sum the distribution by hand.

Record the `validation.stack_counts` `confidence_distribution` issue, if any, as a **WARNING** finding.

### 8. Validate context-snippet.md

Take the first-line format, `|IMPORTANT:` second-line, and token-estimate checks from `validation.context_snippet.issues` returned by the §1 output-validator run — it performs the line-1 `[name vVersion]|root:` pattern match, the line-2 check, and the `len(content)//4` token estimate deterministically, so this step does not recompute them. Record each reported issue as a **WARNING** finding.

Then verify the two stack-specific rows the generic validator does not cover:
- [ ] Stack and integrations lines present
- [ ] Token estimate lands near the ~80-120 design target from step 7 §5 (the validator flags only its wider <40 / >200 bounds; an ~80-150 snippet with an overflow-strategy `workflow_warning` is expected, not a defect)

Record format violations as **WARNING** findings.

### 9. Security Scan (if skill-check available)

Run: `npx skill-check check <skill-dir> --format json` (security scan enabled by default).

Record security findings as advisory **WARNING** findings — they do not block the report.

**If unavailable:** Skip with note in validation results.

### 10. Display Validation Results

Report the validation outcome. If all checks passed, state so and name what was verified: file presence (`{count}/{count}`), SKILL.md structure, metadata.json fields, the `{lib_count}` library + `{pair_count}` integration reference files, and complete confidence-tier coverage. If there were findings, report the `{warning_count}` finding(s) — each with severity, description, and file path — plus files present/expected and warning/error counts; when errors include missing files, note this may indicate a write failure in step 07.

### 11. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

