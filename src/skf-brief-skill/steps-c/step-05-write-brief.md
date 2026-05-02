---
briefSchemaFile: 'assets/skill-brief-schema.md'
nextStepFile: './step-06-health-check.md'
---

# Step 5: Write Brief

## STEP GOAL:

To generate the complete skill-brief.yaml from the approved brief data and write it to the forge data folder, completing the brief-skill workflow.

## Rules

- Focus only on writing the file — all decisions have been made
- Do not change any field values without user request — the brief was already approved
- Create the output directory if it doesn't exist
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing success summary is NOT the terminal step
- All user-facing output in `{communication_language}`; written artifact (`description`, `notes`) in `{document_output_language}`

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Schema Template

Load `{briefSchemaFile}` to reference the YAML template structure.

### 2. Create Output Directory

Create the directory `{forge_data_folder}/{skill-name}/` if it doesn't already exist.

If `{forge_data_folder}` is not set or doesn't exist:
- Fall back to `{output_folder}/forge-data/{skill-name}/`
- Inform user: "**Note:** forge_data_folder not configured. Writing to {output_folder}/forge-data/{skill-name}/ instead."

### 2b. Existing Brief — Overwrite Policy

Before writing, check whether `{forge_data_folder}/{skill-name}/skill-brief.yaml` already exists.

**Interactive (`{headless_mode}` is false):**

If the file exists, present:

"**An existing brief was found at `{path}`.**
Overwrite it with the brief you just approved? [Y/N]"

- **[Y]** Overwrite — proceed to §3.
- **[N]** Cancel — emit a single-line stderr log `brief-skill: overwrite-cancelled at {path}` and HALT with exit code 5 (do not chain to step-06; the run produced no new artifact).

**Headless (`{headless_mode}` is true):**

If the file exists:

- If `force` was supplied as a headless argument: log `"headless: force-overwriting existing brief at {path}"` and proceed to §3.
- Otherwise: emit the error-variant `SKF_BRIEF_RESULT_JSON` envelope (see §4b) on stderr with `halt_reason: "overwrite-cancelled"`, exit code 5, and HALT.

If the file does not exist, proceed normally.

### 3. Generate skill-brief.yaml

**Resolve the `version` field before generating the YAML:**

- If `target_version` was set in step 01 (the user explicitly asked for a specific version), use `target_version` as the value of the `version` field. This is the authoritative version for create-skill.
- Otherwise, use the auto-detected source version from step 02, or `1.0.0` if none was detected.

`target_version` and `version` must never carry different values in the written brief. When the user provided a `target_version`, also include it as a separate `target_version` field so downstream tooling can distinguish "user-requested" from "auto-detected" without re-deriving the provenance — but its value must be identical to `version`.

Generate the YAML file using the approved field values and the schema template:

```yaml
---
name: "{approved skill name}"
version: "{resolved version — target_version if set, else detected source version, else 1.0.0}"
source_type: "{source or docs-only}"
source_repo: "{approved source repo or doc site URL}"
language: "{approved language}"
description: "{approved description}"
forge_tier: "{approved forge tier}"
created: "{current date}"
created_by: "{user_name}"
scope:
  type: "{approved scope type}"
  include:
    - "{approved include patterns}"
  exclude:
    - "{approved exclude patterns}"
  notes: "{approved scope notes or empty string}"
---
```

**Conditional optional field inclusion:**

**If `target_version` was set in step 01:**
Include the `target_version` field in the generated YAML — its value MUST be identical to the `version` field above:
```yaml
target_version: "{target_version — same value as version}"
```

**If `source_type: "docs-only"` OR supplemental `doc_urls` were collected:**
Include the `doc_urls` array (uncommented) in the generated YAML:
```yaml
doc_urls:
  - url: "{documentation URL}"
    label: "{page label}"
```
When `source_type: "docs-only"`: `doc_urls` is required (at least one entry), `source_repo` may be set to the doc site URL for reference or omitted.

**If `scripts_intent` was collected and is not the default `"detect"`:**
Include the `scripts_intent` field (uncommented):
```yaml
scripts_intent: "{none or description}"
```

**If `assets_intent` was collected and is not the default `"detect"`:**
Include the `assets_intent` field (uncommented):
```yaml
assets_intent: "{none or description}"
```

**Always include** `source_authority` (default: `"community"`, forced to `"community"` when `source_type: "docs-only"`):
```yaml
source_authority: "{official|community|internal}"
```

### 4. Write the File

Write the generated YAML to `{forge_data_folder}/{skill-name}/skill-brief.yaml`.

If write fails:
- Interactive: **HALT** — "**Error:** Failed to write skill-brief.yaml. Please check that the directory is writable and try again."
- Headless: emit the error-variant `SKF_BRIEF_RESULT_JSON` envelope (see §4b) on stderr with `halt_reason: "write-failed"`, exit code 4, and HALT.

### 4b. Headless Result Envelope

If `{headless_mode}` is true, emit a single-line JSON envelope on **stdout** immediately after the successful write (before §5 / §6 / §7) so pipeline schedulers can parse the outcome without grepping the prose summary:

```
SKF_BRIEF_RESULT_JSON: {"status":"success","brief_path":"{abs_path}","skill_name":"{name}","version":"{resolved version}","language":"{language}","scope_type":"{scope.type}","exit_code":0,"halt_reason":null}
```

The envelope shape on HARD HALT (any phase, written to **stderr**) uses the same keys with `status: "error"`, `brief_path: null` when no file was written, the matching `exit_code` from the table in `SKILL.md`, and `halt_reason` set to one of: `"input-missing"`, `"forge-tier-missing"`, `"target-inaccessible"`, `"gh-auth-failed"`, `"write-failed"`, `"overwrite-cancelled"`.

When `{headless_mode}` is false, skip this section silently — no envelope is emitted.

### 5. QMD Collection Registration (Deep Tier Only)

**IF forge tier is Deep AND QMD tool is available:**

Index the skill brief into a QMD collection so that portfolio-level searches can find existing briefs and avoid duplicate skill creation across large monorepos.

**Collection creation:**

Create a QMD collection targeting only the brief file:
```bash
qmd collection add {forge_data_folder}/{skill-name} --name {skill-name}-brief --mask "skill-brief.yaml"
qmd embed
```

If collection already exists (re-briefing): remove and recreate for atomic replace:
```bash
qmd collection remove {skill-name}-brief
qmd collection add {forge_data_folder}/{skill-name} --name {skill-name}-brief --mask "skill-brief.yaml"
qmd embed
```

**Embed verification:**

After `qmd embed` completes, verify the collection was embedded:
- Run `qmd status` or `qmd collection list` and confirm `{skill-name}-brief` shows document count > 0
- If verification succeeds: proceed to registry update normally
- If verification fails: log warning "QMD embed verification failed for {skill-name}-brief — collection may not be searchable yet", still proceed to registry update but add `status: "pending"` field to the registry entry

**Registry update:**

Read `{sidecar_path}/forge-tier.yaml` and update the `qmd_collections` array.

If an entry with `name: "{skill-name}-brief"` already exists, replace it. Otherwise, append:

```yaml
  - name: "{skill-name}-brief"
    type: "brief"
    source_workflow: "brief-skill"
    skill_name: "{skill-name}"
    created_at: "{current ISO date}"
    # status: "pending"    # Added only when embed verification fails
```

Write the updated forge-tier.yaml.

**Error handling:**
- If QMD collection creation fails: log the error. Do NOT fail the workflow — the brief file was already written successfully.
- If forge-tier.yaml update fails: log the error, continue.

**IF forge tier is NOT Deep:** Skip this section silently. No messaging.

### 6. Display Success Summary

"**Skill brief written successfully.**

---

**File:** `{forge_data_folder}/{skill-name}/skill-brief.yaml`
**Skill:** {name}
**Language:** {language}
**Scope:** {scope type}
**Forge Tier:** {forge tier}

---

## Next Steps

Your skill brief is ready. To compile the actual skill from this brief, run:

**create-skill** — Reads your skill-brief.yaml and compiles a complete SKILL.md with AST-backed analysis.

After compilation, you can:
- **test-skill** — Validate the compiled skill
- **export-skill** — Package the skill for distribution

---

**Brief-skill workflow complete.**"

### 7. Chain to Health Check

ONLY WHEN the brief file has been written and the success summary displayed will you then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step — do not stop here even though the summary reads as final.

## CRITICAL STEP COMPLETION NOTE

This step chains to the local health-check step (`{nextStepFile}`), which in turn delegates to `shared/health-check.md`. After the health check completes, the brief-skill workflow is fully done.

