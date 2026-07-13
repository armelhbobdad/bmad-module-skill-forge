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

- Validate structure and completeness, not content quality — validation is read-only
- Advisory mode: always proceed to report regardless of findings

## MANDATORY SEQUENCE

### 1. Verify File Existence

Run the shared deterministic output validator once against the committed package — it checks the three core deliverable files' existence, SKILL.md frontmatter, and context-snippet format/token in a single call, so this step consumes its JSON rather than re-deriving those by hand. Resolve `{outputValidator}` from `{outputValidatorProbeOrder}` (first existing path wins). If neither candidate exists, log a WARNING (`"output validator unavailable — skf-validate-output.py missing"`) and fall back to the manual file/frontmatter/snippet checks below.

```bash
python3 {outputValidator} {skill_package} --generated-by create-stack-skill --skill-type stack
```

Consume from its JSON:

- `files_found` — existence of `SKILL.md` / `context-snippet.md` / `metadata.json` (the three core deliverable rows below).
- `validation.skill_md.frontmatter` — feeds the frontmatter check in §3 (manual-fallback path).
- `validation.context_snippet.issues` — feeds §8.
- `validation.stack_counts` — the stack count-equalities, derived deterministically from disk + metadata by the `--skill-type stack` pass: `issues[]` (each `{severity, field, message}`, one per mismatch of `library_count` / `integration_count` / `confidence_distribution`; empty when all agree) and `observed` (`library_count_meta`, `ref_file_count`, `integration_count_meta`, `pair_file_count`, `confidence_sum`). Feeds the count rows in §5 and the confidence-sum row in §7 — do not re-count files or re-sum the distribution by hand.

**Under `--skill-type stack`, `validation.skill_md.body` and `validation.metadata` are emitted as `{"skipped": ...}` markers** — the *individual-skill* schema (which looks for `## Overview` / `Description` / `Key Exports` / `Usage` sections and a `source_repo` field) does not apply to a stack package, so the validator skips those passes and runs `validation.stack_counts` instead. Stack-shaped body structure and the remaining (non-count) metadata fields are checked in §4 / §5.

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
- If exits non-zero, times out, or returns "command not found": Use manual fallback paths. Mark `metadata.validation_status: "manual-only"` (do this in step 7 when appropriate) and record every skipped check in the evidence report.

**Important:** Do not assume availability — empirical check required.

### 3. Validate SKILL.md via skill-check (if available)

**If available**, run: `npx skill-check check <skill-dir> --fix --format json --no-security-scan`

This validates frontmatter, description, body limits, links, formatting — and auto-fixes deterministic issues. Parse JSON for `scores[].score` (match the entry by `relativePath`/`skillId`; falls back to a top-level `qualityScore` on older skill-check builds), `diagnostics[]`, `fixed[]`.

**Post-fix provenance drift guard (S15):** If `fixed[]` is non-empty, `skill-check --fix` has modified `SKILL.md` after step 7 wrote it — so the `metadata.json` hashes/provenance recorded against the pre-fix body may now be stale. Emit a **WARNING** finding listing each auto-fix (`"skill-check --fix modified SKILL.md: {fix_description} — metadata.json hashes/provenance may be out of date"`) rather than silently accepting the fixes, so the drift is surfaced. If the caller wants authoritative metadata, they should re-run the workflow.

**If `body.max_lines` reported**, prefer selective split: extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 content inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). For a stack capstone the canonical split is the catalog (`Library Reference Index` + `Per-Library Summaries`) → `references/stack-catalog.md`, leaving an inline pointer (see `{stackSkillTemplatePath}` "Sizing Guidance"). This is the **intended** large-stack layout, not a violation: §4 below accepts the pointer form, so clearing the skill-check body ERROR this way does not also trip the structure check. Fall back to `npx skill-check split-body <skill-dir> --write` if not feasible. Verify any in-SKILL.md anchor links (e.g. to the catalog/pointer or other moved sections) still resolve after the split. Then re-validate.

**If unavailable**, do not hand-walk the frontmatter — use `validation.skill_md.frontmatter` from the §1 output-validator run, which checks delimiters, `name` format + directory match (`{project_name}-stack`), `description` presence/length, and unknown fields against the agentskills.io allow-set. Record each reported issue at its severity as a **WARNING** finding. (If the output validator was *also* unavailable in §1, fall back to the manual checklist: `---` delimiters; `name` lowercase-alphanumeric-plus-hyphens 1-64 chars matching `{project_name}-stack`; `description` present and 1-1024 chars; only `name`/`description`/`license`/`compatibility`/`metadata`/`allowed-tools` permitted.) Invalid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 4. Validate SKILL.md Body Structure

Load `{stackSkillTemplatePath}` and verify SKILL.md contains expected sections:

- [ ] Header with project name, library count, integration count, forge tier
- [ ] Integration Patterns section (before per-library summaries)
- [ ] Conventions section
- [ ] **Catalog** — `Library Reference Index` table + `Per-Library Summaries`, in **either** form:
  - *Inline* (small stacks): both sections present in SKILL.md, **or**
  - *Pointer* (large stacks): a `Library Catalog` pointer to `references/stack-catalog.md`, **and** that file exists and contains both sections.

  Accept either form — do not WARN when the catalog has been extracted to clear the `body.max_lines` budget (§3). Only record a **WARNING** when *neither* the inline sections *nor* a pointer-plus-`stack-catalog.md` is present, or when the pointer's target file is missing.

Record other missing sections (Header, Integration Patterns, Conventions) as **WARNING** findings.

### 5. Validate metadata.json Fields

Parse metadata.json and verify required fields:

- [ ] `skill_type` equals "stack"
- [ ] `name` matches `{project_name}-stack`
- [ ] `version` and `generation_date` present
- [ ] `forge_tier` is present and matches the forge tier from step 01 (`Quick|Forge|Forge+|Deep`)
- [ ] `confidence_tier` is present and is exactly one of `T1|T1-low|T2|T3` — the dominant T-code computed from `confidence_distribution` (pick the tier with the highest count; ties resolve to the weaker tier: T1-low > T1, T2 > T1-low, T3 > T2 for tie-break so the reported tier never overstates confidence)
- [ ] `libraries` array present and non-empty
- [ ] `confidence_distribution` object present with `t1`, `t1_low`, `t2`, `t3` keys (lowercase, matching template definition)

**Count equalities (library / integration)** — do NOT re-count files here; take them from `validation.stack_counts` in the §1 output-validator run (invoked with `--skill-type stack`), which derived them deterministically from disk. The `library_count` vs per-library reference files and `integration_count` vs integration pair files checks surface as `field: "library_count"` / `field: "integration_count"` entries in `validation.stack_counts.issues[]` (absent when they agree); echo the exact numbers from `validation.stack_counts.observed` (`library_count_meta` / `ref_file_count`, `integration_count_meta` / `pair_file_count`). The `confidence_distribution`-sum equality is covered in §7.

Record each `validation.stack_counts.issues[]` count entry (`library_count` / `integration_count`) and any other mismatch above as **WARNING** findings.

### 6. Validate Reference File Completeness

For each confirmed library, verify `references/{library}.md` contains: library name header, version from manifest (**in compose-mode**: version from source skill metadata), Key Exports section, Usage Patterns section.

For each integration pair, verify `references/integrations/{libraryA}-{libraryB}.md` contains: integration pair header, type classification, Integration Pattern section, Key Files section.

Record missing or incomplete files as **WARNING** findings.

### 7. Validate Confidence Tier Labels

Scan all output files for confidence tier coverage:

- [ ] SKILL.md: each per-library summary and integration pair entry has a confidence label
- [ ] Reference files: each has a confidence label in its header
- [ ] metadata.json: `confidence_distribution` sums to `library_count` — take this from the §1 output-validator run (`--skill-type stack`): the `field: "confidence_distribution"` entry in `validation.stack_counts.issues[]` is present only on mismatch, with `validation.stack_counts.observed.confidence_sum` vs `library_count_meta` for the exact numbers. Do not re-sum the distribution by hand.

Record missing tier labels and any `validation.stack_counts` `confidence_distribution` issue as **WARNING** findings.

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

