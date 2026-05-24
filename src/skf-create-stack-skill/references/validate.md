---
nextStepFile: 'report.md'
stackSkillTemplate: 'assets/stack-skill-template.md'
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

Check that all expected files exist from written_files[]:

**Deliverables** (`{skill_package}`):
- [ ] SKILL.md
- [ ] context-snippet.md
- [ ] metadata.json
- [ ] references/ directory with per-library files
- [ ] references/integrations/ directory with pair files (if integrations detected)

**Workspace** (`{forge_version}`):
- [ ] provenance-map.json
- [ ] evidence-report.md

**Symlink:**
- [ ] `{skill_group}/active` exists and resolves to `{version}`

Record any missing files as **ERROR** findings.

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

**Post-fix provenance drift guard (S15):** If `fixed[]` is non-empty, `skill-check --fix` has modified `SKILL.md` after step 7 wrote it. The safe default for v1.0 is to emit a **WARNING** finding listing each auto-fix (`"skill-check --fix modified SKILL.md: {fix_description} — metadata.json hashes/provenance may be out of date"`). Do NOT silently accept the fixes without surfacing the drift. If the caller wants authoritative metadata, they should re-run the workflow.

**If `body.max_lines` reported**, prefer selective split: extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 content inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). Fall back to `npx skill-check split-body <skill-dir> --write` if not feasible. Verify `#quick-start` and `#key-types` anchors still resolve after split. Then re-validate.

**If unavailable**, perform manual frontmatter check:
- [ ] Frontmatter present with `---` delimiters
- [ ] `name` — present, non-empty, lowercase alphanumeric + hyphens, 1-64 chars, matches `{project_name}-stack`
- [ ] `description` — present, non-empty, 1-1024 characters
- [ ] No unknown fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` permitted

Record frontmatter violations as **WARNING** findings. Invalid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 4. Validate SKILL.md Body Structure

Load `{stackSkillTemplate}` and verify SKILL.md contains expected sections:

- [ ] Header with project name, library count, integration count, forge tier
- [ ] Integration Patterns section (before per-library summaries)
- [ ] Library Reference Index table
- [ ] Per-Library Summaries section
- [ ] Conventions section

Record missing sections as **WARNING** findings.

### 5. Validate metadata.json Fields

Parse metadata.json and verify required fields:

- [ ] `skill_type` equals "stack"
- [ ] `name` matches `{project_name}-stack`
- [ ] `version` and `generation_date` present
- [ ] `forge_tier` is present and matches the forge tier from step 01 (`Quick|Forge|Forge+|Deep`)
- [ ] `confidence_tier` is present and is exactly one of `T1|T1-low|T2|T3` — the dominant T-code computed from `confidence_distribution` (pick the tier with the highest count; ties resolve to the weaker tier: T1-low > T1, T2 > T1-low, T3 > T2 for tie-break so the reported tier never overstates confidence)
- [ ] `library_count` matches actual reference files; `integration_count` matches pair files
- [ ] `libraries` array present and non-empty
- [ ] `confidence_distribution` object present with `t1`, `t1_low`, `t2`, `t3` keys (lowercase, matching template definition)

Record mismatches as **WARNING** findings.

### 6. Validate Reference File Completeness

For each confirmed library, verify `references/{library}.md` contains: library name header, version from manifest (**in compose-mode**: version from source skill metadata), Key Exports section, Usage Patterns section.

For each integration pair, verify `references/integrations/{libraryA}-{libraryB}.md` contains: integration pair header, type classification, Integration Pattern section, Key Files section.

Record missing or incomplete files as **WARNING** findings.

### 7. Validate Confidence Tier Labels

Scan all output files for confidence tier coverage:

- [ ] SKILL.md: each per-library summary and integration pair entry has a confidence label
- [ ] Reference files: each has a confidence label in its header
- [ ] metadata.json: confidence_distribution sums match library_count

Record missing tier labels as **WARNING** findings.

### 8. Validate context-snippet.md

Verify context-snippet.md follows Vercel-aligned indexed format:
- [ ] First line matches: `[{project}-stack v{version}]|root: {prefix}{project}-stack/` where prefix is `skills/` (draft form) or any IDE skill root (`.{dir}/skills/`)
- [ ] Second line starts with `|IMPORTANT:`
- [ ] Stack and integrations lines present
- [ ] Approximate token count is ~80-120 tokens (use the `ceil(char_count / 4)` heuristic from step 7 §5; tolerate up to ~150 if the overflow strategy was applied and a workflow_warning was emitted)

Record format violations as **WARNING** findings.

### 9. Security Scan (if skill-check available)

Run: `npx skill-check check <skill-dir> --format json` (security scan enabled by default).

Record security findings as advisory **WARNING** findings — they do not block the report.

**If unavailable:** Skip with note in validation results.

### 10. Display Validation Results

**If all checks pass:**

"**Validation complete — all checks passed.** Files: {count}/{count} present. SKILL.md structure valid. metadata.json fields verified. {lib_count} library + {pair_count} integration files verified. Confidence tiers: complete coverage. **Proceeding to summary report...**"

**If warnings found:**

"**Validation complete with {warning_count} finding(s).** Findings: {list each: severity, description, file_path}. Files: {present}/{expected} present. Warnings: {count}. Errors: {count}. {If errors: Note missing files may indicate a write failure in step 07.} **Proceeding to summary report...**"

### 11. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

