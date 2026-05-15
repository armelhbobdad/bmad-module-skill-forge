---
briefSchemaFile: 'assets/skill-brief-schema.md'
versionResolutionFile: 'references/version-resolution.md'
qmdRegistrationFile: 'references/qmd-collection-registration.md'
nextStepFile: 'health-check.md'
writeSkillBriefScript: '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
emitBriefEnvelopeScript: '{project-root}/src/shared/scripts/skf-emit-brief-result-envelope.py'
forgeTierRwScript: '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
---

<!-- Config: communicate in {communication_language}. -->

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

`{briefSchemaPath}` and `{versionResolutionFile}` document the brief contract for human readers. The deterministic enforcement of that contract lives in `{writeSkillBriefScript}` and its JSON Schema artifact at `src/shared/scripts/schemas/skill-brief.v1.json`. Load `{briefSchemaPath}` only if you need to explain a specific field to the user during inline adjustments — otherwise skip the read; the script is the source of truth.

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
- **[N]** Cancel — emit a single-line stderr log `brief-skill: overwrite-cancelled at {path}` and HALT with exit code 5 (do not chain to step 6; the run produced no new artifact).

**Headless (`{headless_mode}` is true):**

If the file exists:

- If `force` was supplied as a headless argument: log `"headless: force-overwriting existing brief at {path}"` and proceed to §3.
- Otherwise: emit the error envelope per §4b with `halt_reason: "overwrite-cancelled"`, then HALT with exit code 5.

If the file does not exist, proceed normally.

### 3. Write the Brief

Assemble the brief context as a **flat** JSON object — every approved value is a top-level key, scope is split across four `scope_*` keys instead of nested, and every optional field is passed as `null` when not set rather than conditionally omitted. This eliminates the "decide what to omit" cognitive load that previously made this the most expensive HALT-typo site in the workflow:

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
  "scope_type":       "{approved scope type}",
  "scope_include":    ["{approved include patterns}"],
  "scope_exclude":    ["{approved exclude patterns}"],
  "scope_notes":      "{approved scope notes or empty string}",
  "doc_urls":         null | [{"url": "...", "label": "..."}],
  "scripts_intent":   null | "{detect|none|free-text}",
  "assets_intent":    null | "{detect|none|free-text}",
  "source_authority": null | "{official|community|internal}"
}
```

Pipe it into the writer script with the `--from-flat` flag:

```bash
echo '<context-json>' | uv run {writeSkillBriefScript} write --target {resolved-target-path} --from-flat
```

The script translates flat → nested internally, drops the null optional fields, and runs the same schema validation and atomic write as before — pass every key always, the writer decides what reaches the YAML.

The script:
- Validates the context against `src/shared/scripts/schemas/skill-brief.v1.json`
- Applies the version-precedence rule from `{versionResolutionFile}`
- Enforces the `target_version == version` invariant (refuses to write a brief that violates it)
- Renders YAML in canonical key order (byte-stable across runs)
- Atomically writes the file via temp + fsync + rename (no half-written file ever visible)
- Emits a JSON success envelope on stdout: `{"status":"ok","brief_path":"…","version":"…","bytes":…,"warnings":[…]}`

**On script failure (non-zero exit):**
- Exit 1 (validation/invariant): The error JSON on stderr names the offending field. This indicates a context-assembly bug, not a user error — surface the message to the user, log it, then HALT.
  - Interactive: **HALT** — display the error JSON's `message` field.
  - Headless: emit the error envelope per §4b with `halt_reason: "input-invalid"`, then `exit 2`.
- Exit 2 (I/O failure): The atomic write failed (target unwritable, disk full, etc.).
  - Interactive: **HALT** — "**Error:** Failed to write skill-brief.yaml. Check that the directory is writable and try again."
  - Headless: emit the error envelope per §4b with `halt_reason: "write-failed"`, then `exit 4`.

**On success:** capture `brief_path` and `version` from the response envelope — both are needed for §4b and §6.

**Draft cleanup.** After a successful write, remove `{forge_data_folder}/{skill-name}/.brief-draft.json` if it exists (`rm -f` — silent on absent). The draft was a step 1 §7 checkpoint covering the in-flight workflow window; once the brief is written it is no longer meaningful. In headless mode this rm is a no-op (drafts are only written interactively).

### 4b. Headless Result Envelope (Canonical)

This section is the canonical envelope-emission reference for the workflow. Every headless emission — the success terminal here and every HARD HALT in step 1/02/05 — uses this contract. Remote sites point here instead of restating it.

**Success (this call site only — emitted from §3 directly):**

```bash
echo '{"status":"success","brief_path":"<from §3 response>","skill_name":"<name>","version":"<from §3 response>","language":"<language>","scope_type":"<scope.type>","halt_reason":null}' | \
  uv run {emitBriefEnvelopeScript} emit
```

**Error (used by every HARD HALT site):**

```bash
echo '{"status":"error","skill_name":"<name>","halt_reason":"<reason>"}' | \
  uv run {emitBriefEnvelopeScript} emit --target stderr
```

When the HALT fires before `skill_name` has been resolved (step 1 §1 pre-flight write probe, step 1 §8 input-missing on a malformed args bundle), pass the partially-gathered value or the literal `"unknown"` — the script accepts any non-empty string at this position.

The script derives `exit_code` deterministically from `halt_reason` (null→0, input-missing/input-invalid→2, forge-tier-missing/target-inaccessible/gh-auth-failed→3, write-failed→4, overwrite-cancelled→5, user-cancelled→6 [interactive-only — headless never raises this]), validates against `src/shared/scripts/schemas/skf-brief-result-envelope.v1.json`, and prints the prefixed `SKF_BRIEF_RESULT_JSON: {…}` line.

The script enforces the success/error halt_reason invariant (success requires null halt_reason; error requires non-null). The `user-cancelled` halt_reason is accepted for completeness (interactive `[X]` Cancel sites in step 1/03/04) but never appears on the headless code path.

Invocation sites (each pointed at this block, not duplicated): step 1 §1 (write-failed pre-resolution), step 1 §8 (input-missing/input-invalid GATE), step 5 §2b (overwrite-cancelled), step 5 §3 (input-invalid/write-failed from script). Step-01 §1 forge-tier-missing and step 2 §1 (target-inaccessible/gh-auth-failed) currently HALT without emitting an envelope — pre-existing gaps tracked separately, not addressed by this canonicalization.

When `{headless_mode}` is false, skip this section silently — no envelope is emitted.

### 5. QMD Collection Registration (Deep Tier Only)

**IF forge tier is Deep AND QMD tool is available:** load `{qmdRegistrationFile}` and follow the procedure there to index the brief into a QMD collection and update the forge-tier registry.

**IF forge tier is NOT Deep OR QMD is not available:** skip this section silently — do not load `{qmdRegistrationFile}`. No messaging.

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
