---
nextStepFile: 'generate-snippet.md'
# `{validateOutputHelper}` resolves from `{validateOutputProbeOrder}` (first
# existing path wins). Step 1 §2 already ran `--export-gate` and retained the
# JSON verdict; this step renders its status from that verdict. Only re-run the
# command below if the step-1 JSON is not in context (e.g. package.md entered
# directly). The verdict is deterministic — same package → same result.
validateOutputProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-output.py'
  - '{project-root}/src/shared/scripts/skf-validate-output.py'
---

<!-- Config: communicate in {communication_language}. Validate package contents in {document_output_language}. -->

# Step 2: Package

## STEP GOAL:

To assemble and validate an agentskills.io-compliant package structure from the loaded skill artifacts, ensuring all required components are present and properly formatted for distribution.

## Rules

- Focus only on package structure assembly and validation — do not modify SKILL.md content
- Auto-proceed when complete
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), iterate sections 1–4 below per skill using each skill's `{resolved_skill_package}`. Collect per-skill status; report the aggregate in §4 as one row per skill. Halt the batch if any skill is NOT READY. See step 1 §1c.

## MANDATORY SEQUENCE

### 1. Validate Package Structure

Verify the skill package at `{resolved_skill_package}` (resolved in step 1 via manifest or `active` symlink — see `knowledge/version-paths.md`) contains the expected agentskills.io package layout:

```
{skill_package} = {skills_output_folder}/{skill-name}/{version}/{skill-name}/
├── SKILL.md              ← Required: Active skill document
├── metadata.json         ← Required: Machine-readable metadata
├── context-snippet.md    ← Will be generated/updated in step 3
├── references/           ← Optional: Progressive disclosure
│   ├── {function-a}.md
│   └── {function-b}.md
├── scripts/              ← Optional: Executable automation
└── assets/               ← Optional: Templates, schemas, configs
```

**Component checks — from the export-gate verdict (do not re-derive):**

Step 1 §2 already ran the export gate (`python3 {validateOutputHelper} {resolved_skill_package} --export-gate`) and retained its JSON. Read that verdict rather than re-listing the required fields, enum values, or Section 7b rules here — it deterministically covers all of it:

- `SKILL.md` present and non-empty; `metadata.json` present and valid JSON — `validation.skill_md.issues` / `validation.metadata.issues`
- Required agentskills.io fields present (`name`, `version`, `skill_type`, `source_authority`, `exports`, `generation_date`, `confidence_tier`) — `validation.metadata.issues`
- Enum membership (`skill_type`, `source_authority`, `confidence_tier`) — `validation.metadata.enum_issues`
- SKILL.md Section 7b ↔ on-disk `scripts/`/`assets/` cross-reference — `validation.crossref_7b.missing` (high: §7b-named file absent on disk) and `validation.crossref_7b.orphans` (low: on-disk file not referenced in §7b)

If the step-1 JSON is not in context (e.g. this step was entered directly), re-run the command above to regenerate it — the verdict is deterministic. `references/` presence (at least one `.md`) remains a simple on-disk observation for the §4 report.

### 2. Validate Metadata Completeness

Check metadata.json for recommended (non-required) fields:

- `description` — Brief skill description
- `source_repo` — Source repository URL
- `language` — Primary language of source code
- `ast_node_count` — Number of AST nodes analyzed
- `tool_versions` — Tools used during generation

**For each missing recommended field:** Note as warning, do not halt.

### 3. Assess Package Readiness

Read `export_status` directly from the export-gate verdict (step 1 §2) — do not re-compute the status by hand:

- **READY** — the verdict has no issues (`export_status: "READY"`).
- **WARNINGS** — only medium/low issues remain (`export_status: "WARNINGS"`): §7b orphans, an empty `exports` array, or the recommended-field notes from §2 above.
- **NOT READY** — any high-severity issue (`export_status: "NOT_READY"`). Step 1 §2 halts on this, so a healthy run never reaches here; if it does, surface the high-severity messages and halt.

### 4. Report Package Status

"**Package structure validated.**

**Status:** {export_status: READY / WARNINGS}

**Required Components:**
- SKILL.md: ✅
- metadata.json: ✅ (required fields valid per export-gate verdict)
- references/: {✅ present ({count} files) / ⚠️ not present}

{If warnings (export_status: WARNINGS):}
**Warnings:**
- {list missing recommended fields from §2, plus any `validation.crossref_7b.orphans` and an empty `exports` warning from the verdict}

**Package is ready for snippet generation.**"

### 5. Proceed to Snippet Generation

Display: "**Proceeding to snippet generation...**"

Auto-proceed (no user choices): once package validation is complete, load, read entirely, and execute `{nextStepFile}`.

