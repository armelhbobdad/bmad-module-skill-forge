---
briefSchemaFile: 'assets/skill-brief-schema.md'
versionResolutionFile: 'references/version-resolution.md'
nextStepFile: './step-06-health-check.md'
writeSkillBriefScript: '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
emitBriefEnvelopeScript: '{project-root}/src/shared/scripts/skf-emit-brief-result-envelope.py'
forgeTierRwScript: '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
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
- **Determinism delegation:** YAML rendering, version-precedence, atomic write, the headless result envelope, and the QMD-collection registry mutation are all delegated to shared SKF scripts. The LLM's job in this step is to assemble inputs, branch on script results, and surface user-facing prose — not to render YAML, JSON envelopes, or YAML-mutation diffs in the model.

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Reference the Schema (LLM context only)

`{briefSchemaFile}` and `{versionResolutionFile}` document the brief contract for human readers. The deterministic enforcement of that contract lives in `{writeSkillBriefScript}` and its JSON Schema artifact at `src/shared/scripts/schemas/skill-brief.v1.json`. Load `{briefSchemaFile}` only if you need to explain a specific field to the user during inline adjustments — otherwise skip the read; the script is the source of truth.

### 2. Resolve Output Path

Resolve the target write path:
- Primary: `{forge_data_folder}/{skill-name}/skill-brief.yaml`
- Fallback (when `{forge_data_folder}` is not set or doesn't exist): `{output_folder}/forge-data/{skill-name}/skill-brief.yaml` and inform user "**Note:** forge_data_folder not configured. Writing to {output_folder}/forge-data/{skill-name}/ instead."

The script's atomic-write helper creates parent directories as needed (`mkdir -p`) — no separate mkdir call required.

### 2b. Existing Brief — Overwrite Policy

Before writing, check whether the resolved target path already exists.

**Interactive (`{headless_mode}` is false):**

If the file exists, present:

"**An existing brief was found at `{path}`.**
Overwrite it with the brief you just approved? [Y/N]"

- **[Y]** Overwrite — proceed to §3.
- **[N]** Cancel — emit a single-line stderr log `brief-skill: overwrite-cancelled at {path}` and HALT with exit code 5 (do not chain to step-06; the run produced no new artifact).

**Headless (`{headless_mode}` is true):**

If the file exists:

- If `force` was supplied as a headless argument: log `"headless: force-overwriting existing brief at {path}"` and proceed to §3.
- Otherwise: invoke `{emitBriefEnvelopeScript}` to emit the error-variant envelope on stderr (see §4b) with `halt_reason: "overwrite-cancelled"`, then HALT with exit code 5.

If the file does not exist, proceed normally.

### 3. Write the Brief

Assemble the brief context as a JSON object containing the approved field values from steps 01-04:

```json
{
  "name":             "{approved skill name}",
  "target_version":   "{target_version from step 01, or null}",
  "detected_version": "{auto-detected version from step 02, or null}",
  "source_type":      "{source or docs-only}",
  "source_repo":      "{approved source repo or doc site URL}",
  "language":         "{approved language}",
  "description":      "{approved description}",
  "forge_tier":       "{Quick|Forge|Forge+|Deep}",
  "created":          "{current ISO date YYYY-MM-DD}",
  "created_by":       "{user_name}",
  "scope": {
    "type":    "{approved scope type}",
    "include": ["{approved include patterns}"],
    "exclude": ["{approved exclude patterns}"],
    "notes":   "{approved scope notes or empty string}"
  },
  "doc_urls":         [{"url": "...", "label": "..."}],   // omit when not applicable
  "scripts_intent":   "{detect|none|free-text}",          // omit if "detect"
  "assets_intent":    "{detect|none|free-text}",          // omit if "detect"
  "source_authority": "{official|community|internal}"     // optional; defaults to "community" and is forced to "community" when source_type=docs-only
}
```

Pipe it into the writer script:

```bash
echo '<context-json>' | uv run {writeSkillBriefScript} write --target {resolved-target-path}
```

The script:
- Validates the context against `src/shared/scripts/schemas/skill-brief.v1.json`
- Applies the version-precedence rule from `{versionResolutionFile}` (target_version > detected_version > 1.0.0)
- Enforces the `target_version == version` invariant (refuses to write a brief that violates it)
- Renders YAML in canonical key order (byte-stable across runs)
- Atomically writes the file via temp + fsync + rename (no half-written file ever visible)
- Emits a JSON success envelope on stdout: `{"status":"ok","brief_path":"…","version":"…","bytes":…,"warnings":[…]}`

**On script failure (non-zero exit):**
- Exit 1 (validation/invariant): The error JSON on stderr names the offending field. This indicates a context-assembly bug, not a user error — surface the message to the user, log it, then HALT.
  - Interactive: **HALT** — display the error JSON's `message` field.
  - Headless: invoke `{emitBriefEnvelopeScript}` with `halt_reason: "input-invalid"`, exit code 2.
- Exit 2 (I/O failure): The atomic write failed (target unwritable, disk full, etc.).
  - Interactive: **HALT** — "**Error:** Failed to write skill-brief.yaml. Check that the directory is writable and try again."
  - Headless: invoke `{emitBriefEnvelopeScript}` with `halt_reason: "write-failed"`, exit code 4.

**On success:** capture `brief_path` and `version` from the response envelope — both are needed for §4b and §6.

### 4b. Headless Result Envelope

If `{headless_mode}` is true, emit the success envelope on **stdout** immediately after the write (before §5 / §6 / §7):

```bash
echo '{"status":"success","brief_path":"<from §3 response>","skill_name":"<name>","version":"<from §3 response>","language":"<language>","scope_type":"<scope.type>","halt_reason":null}' | \
  uv run {emitBriefEnvelopeScript} emit
```

The script derives `exit_code` deterministically from `halt_reason` (the canonical mapping is null→0, input-missing/input-invalid→2, forge-tier-missing/target-inaccessible/gh-auth-failed→3, write-failed→4, overwrite-cancelled→5), validates against `src/shared/scripts/schemas/skf-brief-result-envelope.v1.json`, and prints the prefixed `SKF_BRIEF_RESULT_JSON: {…}` line.

The envelope shape on HARD HALT (any phase) is the same call with `--target stderr`, `status: "error"`, and the matching `halt_reason` (one of `"input-missing"`, `"input-invalid"`, `"forge-tier-missing"`, `"target-inaccessible"`, `"gh-auth-failed"`, `"write-failed"`, `"overwrite-cancelled"`) — see the §3, §2b, §5 (no-halt) branches above and the §1/§2 HALTs in step-01/step-02 for invocation sites. The script enforces the success/error halt_reason invariant (success requires null halt_reason; error requires non-null).

When `{headless_mode}` is false, skip this section silently — no envelope is emitted.

### 5. QMD Collection Registration (Deep Tier Only)

**IF forge tier is Deep AND QMD tool is available:**

Index the skill brief into a QMD collection so portfolio-level searches can find existing briefs and avoid duplicate skill creation across large monorepos.

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
- If verification succeeds: proceed to registry update with no `status` field
- If verification fails: log warning "QMD embed verification failed for {skill-name}-brief — collection may not be searchable yet", proceed to registry update but include `status: "pending"` in the entry

**Registry update (delegated to script):**

Build the entry JSON and pipe it to the `register-qmd-collection` subcommand:

```bash
echo '{
  "name": "{skill-name}-brief",
  "type": "brief",
  "source_workflow": "brief-skill",
  "skill_name": "{skill-name}",
  "created_at": "{current ISO date}"
  // include "status": "pending" only when embed verification failed
}' | uv run {forgeTierRwScript} register-qmd-collection --target {forgeTierFile}
```

The script handles the upsert deterministically (replace existing entry with same `name`, else append) and preserves all other forge-tier state (tools, tier, ccc_index, ccc_index_registry, other qmd_collections entries) — no need to reason about YAML re-rendering or section comments.

**Error handling:**
- If `qmd embed` or `qmd collection add` fails: log the error. Do NOT fail the workflow — the brief file was already written successfully.
- If the `register-qmd-collection` script call fails: log the error JSON, continue. The brief is the user-visible artifact; the registry entry is a portfolio-search optimisation.

**IF forge tier is NOT Deep:** Skip this section silently. No messaging.

### 6. Display Success Summary

"**Skill brief written successfully.**

---

**File:** `{brief_path from §3 response}`
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
