---
nextStepFile: 'health-check.md'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1b: Auto-Brief Validation

## STEP GOAL:

To check the auto-generated brief against the schema and show a concise summary of it, then print the result envelope, run the `on_complete` hook and chain to the health check. `[auto]` is a pipeline stage, which the forger always runs headless, so this step asks nothing.

## Rules

- This step is conditional — only loaded from step-auto-brief.md when `[auto]` mode is active
- The brief MUST already exist on disk (written by step-auto-brief §4) before this step runs
- Do NOT render YAML or JSON envelopes in the LLM — delegate to deterministic scripts
- The 10-line summary is always displayed, even in headless mode, for logging transparency

## MANDATORY SEQUENCE

### 1. Load Auto-Brief

Read the brief from `{forge_data_folder}/{skill_name}/skill-brief.yaml` (written by step-auto-brief §4).

**Resolve `{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`; first existing path wins. HALT if no candidate exists.

Validate the brief against the schema:

```bash
uv run {validateBriefSchemaHelper} {forge_data_folder}/{skill_name}/skill-brief.yaml
```

The script returns JSON `{valid, errors[], warnings[], halt_reason, brief}`.

- **`valid: false`**: emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-invalid"` (SKILL.md Halt Contract), then HARD HALT (exit code 2): "**Auto-brief at `{forge_data_folder}/{skill_name}/skill-brief.yaml` is invalid: {first error message}.**"
- **`valid: true`**: proceed with the parsed `brief` payload. Log any non-empty `warnings[]` and add each to `workflow_warnings[]` as `<field>: <message>`.

**IF the file does not exist:** emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-missing"` (SKILL.md Halt Contract), then HARD HALT (exit code 2): "**Auto-brief not found at `{forge_data_folder}/{skill_name}/skill-brief.yaml`: step-auto-brief must write the brief before this step runs.**"

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
Pipeline:     forge-auto ({forge_tier} tier)
Description:  "{description}"
```

Where `{N}` is the count of `scope_include` patterns and `{M}` is the count of `scope_exclude` patterns. If `doc_urls` is null or empty, display "None detected". The `Pipeline` line names the auto pipeline and the resolved `{forge_tier}` — it carries no numeric quality target, which would be an unverified guarantee an automator might parse as fact.

### 3. Envelope, Hook and Chain

Print the `SKF_BRIEF_RESULT_JSON` envelope with `mode: "auto"`, through the `{emitBriefEnvelopeHelper}` SKILL.md On Activation step 4 resolved (`references/invocation-contract.md` defines each field), and display the line it prints verbatim:

```bash
uv run {emitBriefEnvelopeHelper} emit <<'SKF_BRIEF_RESULT'
{"status":"success","brief_path":"{brief_path}","skill_name":"{skill_name}","version":"{version}","language":"{language}","scope_type":"{scope_type}","halt_reason":null,"mode":"auto","warnings":[<workflow_warnings[] as JSON strings>]}
SKF_BRIEF_RESULT
```

Where `{brief_path}` is `{forge_data_folder}/{skill_name}/skill-brief.yaml`. If `{emitBriefEnvelopeHelper}` has no path, or the helper exits non-zero or prints no line, display its error: the brief is already written, so the run goes on.

**On-complete hook.** Right after the envelope, if `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`), run it:

```bash
{onCompleteCommand} --result-path={brief_path}
```

A hook error never fails the run: on a non-zero exit or a process error, display one line, `on_complete hook failed (exit {code}): {first line of its stderr}`, and continue. The envelope is already printed, so it does not carry this line. When `{onCompleteCommand}` is empty, skip the hook.

**Remove the run folder.** The brief is written, so the folder step 1 §1 created has done its job; remove it (the guard keeps the command to that folder):

```bash
case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac
```

Chain to {nextStepFile} (health-check.md): load, read fully, then execute. The health check only relays to the shared check: the envelope and the hook of this path run here.
