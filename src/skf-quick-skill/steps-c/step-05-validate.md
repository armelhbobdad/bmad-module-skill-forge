---
nextStepFile: './step-06-write.md'
# Resolve `{frontmatterValidator}` by probing `{frontmatterValidatorProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback);
# first existing path wins. Used in §4 fallback when `npx skill-check` is
# unavailable so manual frontmatter validation matches the agentskills.io
# spec deterministically instead of via an LLM-walked checklist.
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
---

# Step 5: Write & Validate

Communicate with the user in `{communication_language}`. Validation reports are user-facing — render their narrative content in `{document_output_language}`.

## STEP GOAL:

To write the compiled SKILL.md, context-snippet.md, and metadata.json to the versioned skill package, then validate them on disk against the agentskills.io specification at community tier. Writing happens here (before step-06 finalization) because `skill-check` is a file-based CLI — it reads artifacts from disk — so the files must exist before validation runs. Report any gaps or issues. Validation is advisory — issues are reported but do not block the workflow.

## Rules

- Write exactly what was compiled — do not modify content during writing
- Validation is advisory — report issues but never block output
- Do not modify compiled content post-validation — report only
- Community-tier validation (lighter than official requirements)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Create Output Directory

Resolve `{version}` from the extraction inventory's detected version, defaulting to `1.0.0` if not detected. Create the skill output directories:

```
{skill_group}                          # {skills_output_folder}/{repo_name}/
{skill_package}                        # {skills_output_folder}/{repo_name}/{version}/{repo_name}/
```

If `{skill_package}` already exists, confirm with user before overwriting:

"**Directory `{skill_package}` already exists.** Overwrite will replace the prior compiled output; validation results, result contracts, and any manual tweaks from the previous run will not be preserved. Overwrite existing files? [Y/N]"

- **If user selects Y:** Proceed to section 2.
- **If user selects N:** Halt with: "Overwrite cancelled. Existing skill preserved. Run [QS] with a different skill name or remove the existing directory manually."

**GATE [default: Y]** — If `{headless_mode}` is true, auto-proceed with Y and log: "headless: overwriting existing `{skill_package}`".

### 2. Write Deliverables

Write the three compiled artifacts to the skill package so that validation in sections 3–9 has files on disk to read:

**File 1:** `{skill_package}/SKILL.md` — the compiled skill document
**File 2:** `{skill_package}/context-snippet.md` — the compressed context snippet
**File 3:** `{skill_package}/metadata.json` — the machine-readable metadata

Confirm after each write: "Written: SKILL.md" / "Written: context-snippet.md" / "Written: metadata.json".

**If any write fails — HARD HALT:**

"**Write failed:** Could not write to `{file_path}`.

Error: {error details}

Check:
- Does the output directory exist and is it writable?
- Is there sufficient disk space?
- Are there permission issues?"

### 3. Check Tool Availability

Run: `npx skill-check -h`

- If succeeds (returns usage information): Continue to automated validation (section 4)
- If fails (command not found or error): Skip to manual fallback in section 4

**Important:** Use the verification command. Do not assume availability — empirical check required.

### 4. Validate SKILL.md via skill-check (if available)

**If `npx skill-check` is available**, run automated validation + security scan in one invocation against the skill package written in section 2 (security scan is enabled by default when `--no-security-scan` is omitted, so the same call covers §8 and avoids paying the npx startup cost twice):

```bash
npx skill-check check {skill_package} --fix --format json
```

This validates frontmatter, description, body limits, links, and formatting; runs the security scan; and auto-fixes deterministic issues (field ordering, slug format, required fields, trailing newlines).

**Parse JSON output** to extract:
- `qualityScore` — overall score (0-100)
- `diagnostics[]` — remaining issues after auto-fix
- `fixed[]` — issues automatically corrected
- `security[]` (when present) — security findings, recorded as advisory warnings (security issues do not block output)

Record quality score, remaining diagnostics, and security findings as validation issues.

**If skill-check is NOT available**, run the shared frontmatter validator instead of an LLM-walked checklist. Resolve `{frontmatterValidator}` by probing `{frontmatterValidatorProbeOrder}` (installed `{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py` first, dev `{project-root}/src/shared/scripts/skf-validate-frontmatter.py` fallback); first existing path wins. If neither candidate exists, log a high-severity issue ("frontmatter validator unavailable — both `npx skill-check` and `skf-validate-frontmatter.py` missing") and skip frontmatter validation.

```bash
python3 {frontmatterValidator} {skill_package}/SKILL.md --skill-dir-name {repo_name}
```

The validator emits JSON with `status` (`pass`/`fail`), `issues[]` (each with `severity`, `code`, `message`), and `frontmatter` (the parsed name/description). It checks frontmatter delimiters, name format (Unicode letters + digits + hyphens, no consecutive/trailing hyphens), name-directory match, description presence and length, and unknown fields against the agentskills.io spec — the same shape this step would otherwise hand-walk. Record each `issues[]` entry as a validation issue with its reported severity. Missing frontmatter or missing required fields are high-severity — skills without valid frontmatter will fail `npx skills add` and `npx skill-check check`.

### 5. Validate SKILL.md Body Structure

Check that SKILL.md has these required sections populated:

- [ ] **Overview section** present with package name, repo, language, authority
- [ ] **Description section** present with non-empty content
- [ ] **Key Exports section** present (may be empty if confidence is low)
- [ ] **Usage Patterns section** present (may have README fallback)

**For each missing or empty required section, log an issue.**

### 6. Validate Context Snippet Format

Check context-snippet.md format compliance:

- [ ] **Vercel-aligned indexed format** — pipe-delimited with version, retrieval instruction, section anchors
- [ ] **First line** matches pattern: `[{name} v{version}]|root: {prefix}{name}/` where prefix is `skills/` (draft form) or any IDE skill root (`.{dir}/skills/`)
- [ ] **Second line** starts with: `|IMPORTANT:`
- [ ] **Approximate token count** is ~80-120 tokens

**If format is wrong, log an issue.**

### 7. Validate Metadata JSON

Check metadata.json has required fields:

- [ ] `name` — present, non-empty
- [ ] `version` — present (auto-detected or "1.0.0")
- [ ] `source_authority` — must be "community"
- [ ] `source_repo` — present, valid GitHub URL
- [ ] `language` — present, non-empty
- [ ] `generated_by` — must be "quick-skill"
- [ ] `generation_date` — present
- [ ] `stats.exports_documented` — present, number
- [ ] `stats.exports_public_api` — present, number
- [ ] `stats.exports_total` — present, number
- [ ] `stats.public_api_coverage` — present, number
- [ ] `stats.total_coverage` — present, number
- [ ] `confidence_tier` — present

**For each missing or invalid field, log an issue.**

### 8. Security Scan (covered by §4)

Security findings are already collected from the §4 invocation (no separate `npx` round trip needed — `skill-check check ... --fix --format json` runs the security scan by default). If skill-check was unavailable in §3, log "security scan skipped — skill-check unavailable" in validation results.

### 9. Report Validation Results

"**Validation complete:**

**SKILL.md:** {pass/issues found} (quality score: {score}/100 if skill-check was available)
{list any issues}
{list any auto-fixed issues}

**context-snippet.md:** {pass/issues found}
{list any issues}

**metadata.json:** {pass/issues found}
{list any issues}

**Security:** {pass/warn/skipped}
{list any security findings}

**Overall:** {pass / N issues found}

{If issues found:}
These issues are advisory for community-tier skills. You can proceed to finalize or go back to adjust.

**Proceeding to finalize...**"

Set `validation_result` with pass/fail status, quality score, and issues list.

### 10. Auto-Proceed to Finalize

#### Menu Handling Logic:

- After validation report, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step — validation is advisory
- Proceed directly to finalize step after reporting results

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN deliverables have been written to `{skill_package}` and validation checks are complete and results reported will you load and read fully `{nextStepFile}` to execute finalization.

