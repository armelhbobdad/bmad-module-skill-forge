---
nextStepFile: 'step-02-strategy.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
templateFile: '{briefTemplatePath}'
validateScript: 'scripts/campaign-validate-state.py'
manifestScript: 'scripts/campaign-parse-manifest.py'
---

<!-- Config: communicate in {communication_language}. -->

# Setup

## STEP GOAL:

Collect campaign inputs from the operator, create the initial `_campaign-state.yaml`, and generate `campaign-brief.yaml` so the campaign has a persistent starting point that survives context death.

This is the only step that creates the state file (it does not yet exist). All subsequent steps use **read-backup-modify-write** per the State Contract in `references/campaign-contracts.md`.

## RULES

- This step creates the state file — there is no existing state to read or back up.
- Validate the written state with `uv run {validateScript} --state-file {stateFile}` before generating the brief. HALT (exit code 3, `invalid-state`) on non-zero, surfacing the script's `errors[]`.
- If `{headless_mode}` is true, draw inputs from `--brief`/`--manifest` (On Activation step 4) and auto-proceed through confirmation gates with the default action, logging each auto-decision to the decision log.

## TASKS

### §1: Collect Inputs

A campaign needs a `campaign_name` and its target libraries. Each target has:

- `name`: skill name
- `repo_url`: source repository URL
- `tier`: `"A"` (full pipeline) or `"B"` (batch)
- `pin`: version pin (string), or `null` for latest
- `depends_on`: array of skill names this target depends on (may be empty)

Two paths are optional:

- `directive_path`: a `_campaign-directive.md` file with operator directives (contract: `references/campaign-directive-spec.md`)
- `architecture_doc_path`: the architecture document the verify (Stage 7) and refine (Stage 8) stages consume. If omitted here, those stages discover it at runtime (`{project-root}/docs/architecture.md`, then `{project-root}/_bmad-output/planning-artifacts/architecture.md`). Capturing it now persists the choice across resume and avoids re-prompting.

A field no source gives takes its default: `tier` `"A"`, `pin` `null`, `depends_on` empty, and `campaign_name` the brief's `campaign_name`, else `{project_name}`.

**Headless** (`--brief` and `--manifest` imply it): take the inputs from the source On Activation parsed. Parse a `--manifest` file deterministically with `uv run {manifestScript} <manifest-file>`; read a `--brief` file's `campaign-brief.yaml` fields directly.

**Interactive:** open with this one question, and ask nothing before it:

> Share the targets for this campaign in whatever form you have them: a manifest or `campaign-brief.yaml` path, a pasted list, or repository URLs. Add a campaign name and a directive or architecture document path if you have them.

Turn the answer into targets: a manifest path goes through `uv run {manifestScript} <manifest-file>`, and a brief path is read directly. A pasted list or bare repository URLs are first rewritten as manifest lines in the `--manifest` format On Activation describes (the name taken from the repository when none is given), then piped to `uv run {manifestScript} -`. Show the drafted campaign once for correction: the campaign name, the directive and architecture paths (or none), and one table of the targets with `name`, `repo_url`, `tier`, `pin` and `depends_on`. After the operator's corrections, ask only about what is still missing or ambiguous (a target with no repository URL, a `depends_on` name that is no target), all in one question.

A manifest line the parser rejects (`errors[]` non-empty, script exit 1) never yields a partial target set: in headless, HALT (exit code 2, `invalid-input`) listing the offending line numbers; interactively, show those lines and ask for them corrected.

If no targets can be collected (an empty answer, or an empty `--brief` or `--manifest`), HALT (exit code 2, `invalid-input`) with guidance: a campaign needs at least one target.

### §2: Build State Object

Construct `_campaign-state.yaml` in memory from collected inputs. Use the campaign-wide quality gate resolved in On Activation: `{qualityGateHard}` / `{qualityGateSoftTarget}` / `{qualityGateSoftFallback}`. Note: `repo_url` (collected in §1) is NOT part of the state schema: it belongs in the brief only (§4). The state schema enforces `additionalProperties: false`, so including it would fail validation.

```yaml
campaign:
  name: "{campaign_name}"
  started_at: "{current_iso8601_with_tz}"
  last_updated: "{current_iso8601_with_tz}"
  current_stage: 0
  directive_path: "{directive_path or omit if not provided}"
  architecture_doc_path: "{architecture_doc_path or omit if not provided}"
  quality_gate:
    hard: "{qualityGateHard}"
    soft_target: {qualityGateSoftTarget}
    soft_fallback: {qualityGateSoftFallback}
skills:
  # One entry per target:
  - name: "{target.name}"
    status: "pending"
    depends_on: []            # from target.depends_on
    tier: "{target.tier}"
    pin: null                 # from target.pin
    brief_path: null          # populated in step-05 once BS produces the skill's brief
    skill_path: null
    quality_score: null
    workarounds_applied: []
    started_at: null
    completed_at: null
dependency_graph:
  execution_order: []         # populated by step-02-strategy
  circular_deps_detected: false
```

### §3: Write + Validate State

1. Ensure the directory `{campaignWorkspacePath}/` exists (create if missing).
2. Write the constructed state to `{stateFile}`. This is the initial creation — no `.bak` is needed for the first write; all subsequent steps use read-backup-modify-write.
3. Run `uv run {validateScript} --state-file {stateFile}`. On non-zero (invalid), **HALT** (exit 3) with the script's `errors[]` — do not proceed to brief generation with an invalid state file.

### §4: Generate Brief

Populate `{templateFile}` with collected inputs and write to `{briefFile}`. Fill in:

- `campaign_name`: from collected input
- `created_at`: current ISO-8601 timestamp with timezone
- `targets`: one entry per target with `name`, `repo_url`, `tier`, `pin` and `depends_on`, plus every other field its source gave it (a language or scope hint, for example)
- `quality_gate`: `{qualityGateHard}` / `{qualityGateSoftTarget}` / `{qualityGateSoftFallback}`
- `architecture_doc_path`: from collected input, or empty string if not provided
- `notes`: operator-provided context, or empty string

The brief is a machine-readable snapshot enabling fresh-context resume.

## OUTPUT

Confirm state file creation and brief generation. Display summary:

- Campaign name
- Number of targets

Chain to `{nextStepFile}`.
