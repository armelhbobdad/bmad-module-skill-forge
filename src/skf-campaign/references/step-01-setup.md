---
nextStepFile: 'step-02-strategy.md'
templateFile: 'templates/campaign-brief-template.yaml'
stateSchemaFile: 'assets/campaign-state-schema.json'
---

<!-- Config: communicate in {communication_language}. -->

# Setup

## STEP GOAL:

Collect campaign inputs from the operator, create the initial `_campaign-state.yaml`, and generate `campaign-brief.yaml` so the campaign has a persistent starting point that survives context death.

This is the only step that uses the **create-validate-write** pattern (the state file does not yet exist). All subsequent steps use **read-backup-modify-write** per the State Contract in SKILL.md.

## RULES

- This step creates the state file — there is no existing state to read or back up.
- Validate the constructed state against `{stateSchemaFile}` before writing to disk.
- Halt on any schema validation error with the specific violation.
- All field names use `snake_case`, dates use ISO-8601 with timezone, enums use lowercase or uppercase as defined by the schema.
- If `{headless_mode}` is true, auto-proceed through confirmation gates with the default action and log each auto-decision.

## TASKS

### 1. Collect Inputs

Accept from the operator (or from arguments in headless mode):

- `campaign_name` — string identifier for this campaign run
- Target libraries — each entry requires:
  - `name` — skill name
  - `repo_url` — source repository URL
  - `tier` — `"A"` (full pipeline) or `"B"` (batch)
  - `pin` — version pin (string) or `null` for latest
  - `depends_on` — array of skill names this target depends on (may be empty)
- `directive_path` (optional) — path to a `_campaign-directive.md` file with operator directives
- `architecture_doc_path` (optional) — path to the architecture document the verify (Stage 7) and refine (Stage 8) stages consume. If omitted here, those stages discover it at runtime (`docs/architecture.md`, then `_bmad-output/planning-artifacts/architecture.md`). Capturing it now persists the choice across resume and avoids re-prompting.

If headless, all inputs come from arguments — no interactive prompts.

### 2. Health Queue Preference

Default to `"local"` (project-local findings queue).

Present the opt-in prompt:

> Send anonymized quality findings to the shared improvement queue? [y/N]

- **y** — set `health_findings_queue` to `"improvement"`
- **N** (default) — keep `health_findings_queue` as `"local"`

In headless mode: auto-select `"local"` (N) and log the auto-decision.

### 3. Build State Object

Construct `_campaign-state.yaml` in memory from collected inputs. Note: `repo_url` (collected in §1) is NOT part of the state schema — it belongs in the brief only (§6). The state schema enforces `additionalProperties: false` so including it would halt validation.

```yaml
campaign:
  name: "{campaign_name}"
  started_at: "{current_iso8601_with_tz}"
  last_updated: "{current_iso8601_with_tz}"
  current_stage: 0
  directive_path: "{directive_path or omit if not provided}"
  architecture_doc_path: "{architecture_doc_path or omit if not provided}"
  quality_gate:
    hard: "zero-critical-high"
    soft_target: 90
    soft_fallback: 80
  health_findings_queue: "{local or improvement}"
skills:
  # One entry per target:
  - name: "{target.name}"
    status: "pending"
    depends_on: []            # from target.depends_on
    tier: "{target.tier}"
    pin: null                 # from target.pin
    brief_path: null
    skill_path: null
    quality_score: null
    workarounds_applied: []
    started_at: null
    completed_at: null
dependency_graph:
  execution_order: []         # populated by step-02-strategy
  circular_deps_detected: false
```

### 4. Validate State

Validate the constructed YAML against `{stateSchemaFile}` before writing.

- Load the JSON Schema from `{stateSchemaFile}`
- Validate the in-memory state object against the schema
- On validation error: **HALT** with the specific schema violation — do not write an invalid state file

### 5. Write State

Write `_campaign-state.yaml` to `forge-data/_campaign/`.

- Ensure the directory `forge-data/_campaign/` exists (create if missing)
- This is the initial creation — no `.bak` file needed for the first write
- All subsequent steps use the read-backup-modify-write pattern

### 6. Generate Brief

Populate `{templateFile}` with collected inputs and write to `forge-data/_campaign/campaign-brief.yaml`.

Fill in:
- `campaign_name` — from collected input
- `created_at` — current ISO-8601 timestamp with timezone
- `targets` — array of target entries with `name`, `repo_url`, `tier`, `pin`, `depends_on`
- `quality_gate` — use defaults: `hard: "zero-critical-high"`, `soft_target: 90`, `soft_fallback: 80`
- `health_findings_queue` — from the §2 preference decision
- `architecture_doc_path` — from collected input, or empty string if not provided
- `notes` — operator-provided context, or empty string

The brief is a machine-readable snapshot enabling fresh-context resume (FR-35).

## OUTPUT

Confirm state file creation and brief generation. Display summary:

- Campaign name
- Number of targets
- Tier distribution (count of A vs B)
- Health queue setting

Chain to `{nextStepFile}`.
