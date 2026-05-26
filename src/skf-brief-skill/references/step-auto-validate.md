---
nextStepFile: 'health-check.md'
rejectTargetFile: 'confirm-brief.md'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
emitBriefEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-brief-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-brief-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1b: Auto-Brief Validation

## STEP GOAL:

To present the user with a concise summary of the auto-generated brief and offer three actions — approve, edit, or reject — before the pipeline continues. On approve or edit, the result envelope is emitted and the pipeline chains to the health check. On reject, the pipeline falls back to the interactive brief review cycle with pre-populated fields.

## Rules

- This step is conditional — only loaded from step-auto-brief.md when `[auto]` mode is active
- The brief MUST already exist on disk (written by step-auto-brief §5) before this step runs
- Do NOT render YAML or JSON envelopes in the LLM — delegate to deterministic scripts
- Do NOT modify confirm-brief.md or write-brief.md — the [R]eject path reuses them as-is
- The 10-line summary is always displayed, even in headless mode, for logging transparency

## MANDATORY SEQUENCE

### 1. Load Auto-Brief

Read the brief from `{forge_data_folder}/{skill_name}/skill-brief.yaml` (written by step-auto-brief §5).

**Resolve `{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`; first existing path wins. HALT if no candidate exists.

Validate the brief against the schema:

```bash
uv run {validateBriefSchemaHelper} {forge_data_folder}/{skill_name}/skill-brief.yaml
```

The script returns JSON `{valid, errors[], warnings[], halt_reason, brief}`.

- **`valid: false`** — HARD HALT with exit code 2 (`input-invalid`): "**Auto-brief at `{forge_data_folder}/{skill_name}/skill-brief.yaml` is invalid: {first error message}.**" Emit error envelope per §7 with `halt_reason: "input-invalid"`.
- **`valid: true`** — proceed with the parsed `brief` payload. Surface any non-empty `warnings[]` to the log.

**IF the file does not exist:**
- HARD HALT with exit code 2 (`input-missing`): "**Auto-brief not found at `{forge_data_folder}/{skill_name}/skill-brief.yaml` — step-auto-brief must write the brief before this step runs.**" Emit error envelope per §7 with `halt_reason: "input-missing"`.

Extract from the parsed brief:
- `skill_name` ← `brief.name`
- `version` ← `brief.version`
- `source_repo` ← `brief.source_repo`
- `language` ← `brief.language`
- `scope_type` ← `brief.scope.type`
- `scope_include` ← `brief.scope.include`
- `scope_exclude` ← `brief.scope.exclude`
- `forge_tier` ← `brief.forge_tier`
- `description` ← `brief.description`
- `doc_urls` ← `brief.doc_urls`

### 2. Present 10-Line Summary

Render a concise summary from the brief fields for rapid scanning:

```
Auto-Brief Summary: {skill_name}
─────────────────────────────────
Source:       {source_repo}
Language:     {language}
Scope:        {scope_type} ({N} include, {M} exclude patterns)
Docs:         {doc_urls count} sources detected | "None detected"
Version:      {version}
Forge Tier:   {forge_tier}
Quality:      90% target (deepwiki pipeline)
Description:  "{description}"
```

Where `{N}` is the count of `scope_include` patterns and `{M}` is the count of `scope_exclude` patterns. If `doc_urls` is null or empty, display "None detected".

### 3. Validation Gate

**GATE: [A]pprove** — Present `[A]pprove` / `[E]dit` / `[R]eject` to user.

"**Review the auto-generated brief above.**

Select an action:
  [A] Approve — accept the brief as-is and continue the pipeline
  [E] Edit — modify specific fields before continuing
  [R] Reject — fall back to interactive brief review with pre-populated fields"

If `{headless_mode}`: auto-proceed with `[A]pprove`, log: "headless: auto-approve auto-brief".

Wait for user response. Branch on the response:

- `[A]` or `approve` → §4 ([A]pprove path)
- `[E]` or `edit` → §5 ([E]dit path)
- `[R]` or `reject` → §6 ([R]eject path)
- Any other input → answer briefly, re-display the menu

### 4. [A]pprove Path

**Resolve `{emitBriefEnvelopeHelper}`** from `{emitBriefEnvelopeProbeOrder}`; first existing path wins. HALT if no candidate exists.

Emit the `SKF_BRIEF_RESULT_JSON` envelope with `mode: "auto"`:

```bash
echo '{"status":"success","brief_path":"{brief_path}","skill_name":"{skill_name}","version":"{version}","language":"{language}","scope_type":"{scope_type}","halt_reason":null,"mode":"auto"}' | \
  uv run {emitBriefEnvelopeHelper} emit
```

Where `{brief_path}` is `{forge_data_folder}/{skill_name}/skill-brief.yaml`.

Chain to {nextStepFile} (health-check.md) — load, read fully, then execute.

### 5. [E]dit Path

Present each brief field with its current value and accept natural language modification requests.

"**Editable fields:**

1. **Name:** {skill_name}
2. **Source:** {source_repo}
3. **Language:** {language}
4. **Scope type:** {scope_type}
5. **Include patterns:** {scope_include}
6. **Exclude patterns:** {scope_exclude}
7. **Description:** {description}
8. **Doc URLs:** {doc_urls or "None"}
9. **Version:** {version}
10. **Forge tier:** {forge_tier}

Tell me what to change (e.g. 'change scope type to public-api', 'add doc URL https://...')."

Wait for user response. Apply changes to the brief context.

**Re-write the modified brief** through the canonical writer:

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}`; first existing path wins.

Assemble the modified brief context as a flat JSON object (same format as step-auto-brief §4):

```bash
echo '<modified-flat-json>' | uv run {writeSkillBriefHelper} write --target {forge_data_folder}/{skill_name}/skill-brief.yaml --from-flat
```

The canonical writer validates the brief internally — on non-zero exit, surface the error and re-prompt for corrections. The edit loop allows multiple modifications — each write re-validates before accepting.

**Re-validate the written brief** against the schema to confirm correctness:

**Resolve `{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`; first existing path wins.

```bash
uv run {validateBriefSchemaHelper} {forge_data_folder}/{skill_name}/skill-brief.yaml
```

If validation fails (the writer missed a constraint), surface the error and re-prompt for corrections.

Re-present the 10-line summary (§2 format) with updated values so the user can verify the change.

"Updated brief written. **Select:** [A] Approve and continue · [E] Edit more · [R] Reject"

- `[A]` → emit envelope per §4, chain to {nextStepFile}
- `[E]` → repeat §5 edit loop
- `[R]` → §6 ([R]eject path)

### 6. [R]eject Path

"**Falling back to interactive brief — fields pre-populated from auto-detection.**"

Hydrate brief context variables from the auto-brief on disk, using the same field mapping as the ratify path in gather-intent §3.1a:

- `name` ← `brief.name`; `version` ← `brief.version`; `target_version` ← `brief.target_version`
- `target_ref` ← `brief.target_ref`; `source_ref` ← `brief.source_ref` (optional git refs; preserve when present)
- `source_repo` ← `brief.source_repo`; `source_type` ← `brief.source_type`; `source_authority` ← `brief.source_authority`; `doc_urls` ← `brief.doc_urls`
- `language` ← `brief.language`; `description` ← `brief.description`; `forge_tier` ← `brief.forge_tier`
- `created` ← `brief.created`; `created_by` ← `brief.created_by`
- `scope.type` / `scope.include` / `scope.exclude` / `scope.tier_a_include` / `scope.notes` / `scope.rationale` / `scope.amendments` ← `brief.scope.*` (preserve `tier_a_include` and the `amendments` log verbatim — do not re-derive or drop them)
- `scripts_intent` ← `brief.scripts_intent`; `assets_intent` ← `brief.assets_intent`

Set `ratify_mode: true` and `ratify_source_path: {forge_data_folder}/{skill_name}/skill-brief.yaml` in workflow context.

Chain to {rejectTargetFile} (confirm-brief.md) — load, read fully, then execute. The user gets the full interactive review experience: view, adjust fields inline, revise scope via [R], or approve via [C] → write-brief.md → health-check.md.

The interactive chain's write-brief.md handles its own envelope emission with `mode: null` (interactive), which is correct since the user explicitly chose to leave auto mode.

### 7. Error Envelope (Canonical)

Every HARD HALT in this step emits the error envelope on stderr:

**Resolve `{emitBriefEnvelopeHelper}`** from `{emitBriefEnvelopeProbeOrder}`; first existing path wins.

```bash
echo '{"status":"error","skill_name":"{skill_name or unknown}","halt_reason":"{reason}","mode":"auto"}' | \
  uv run {emitBriefEnvelopeHelper} emit --target stderr
```

### 8. Chain

Load, read fully, then execute the appropriate next step file based on the user's choice:
- [A]pprove or [E]dit (after final approve): {nextStepFile} (health-check.md)
- [R]eject: {rejectTargetFile} (confirm-brief.md)

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user has made their choice (approve, edit-then-approve, or reject) and the appropriate action has been taken (envelope emitted or context hydrated) will you load and read fully the next step file.
