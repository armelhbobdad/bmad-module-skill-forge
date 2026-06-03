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

This is the only step that creates the state file (it does not yet exist). All subsequent steps use **read-backup-modify-write** per the State Contract in SKILL.md.

## RULES

- This step creates the state file — there is no existing state to read or back up.
- Validate the written state with `uv run {validateScript} --state-file {stateFile}` before generating the brief. HALT (exit code 3, `invalid-state`) on non-zero, surfacing the script's `errors[]`.
- If `{headless_mode}` is true, draw inputs from `--brief`/`--manifest` (On Activation step 4) and auto-proceed through confirmation gates with the default action, logging each auto-decision to the decision log.

## TASKS

### §1 — Collect Inputs

Accept from the operator (or, in headless mode, from the `--brief`/`--manifest` source parsed in On Activation):

- `campaign_name` — string identifier for this campaign run
- Target libraries — each entry requires:
  - `name` — skill name
  - `repo_url` — source repository URL
  - `tier` — `"A"` (full pipeline) or `"B"` (batch)
  - `pin` — version pin (string) or `null` for latest
  - `depends_on` — array of skill names this target depends on (may be empty)
- `directive_path` (optional) — path to a `_campaign-directive.md` file with operator directives (contract: `references/campaign-directive-spec.md`)
- `architecture_doc_path` (optional) — path to the architecture document the verify (Stage 7) and refine (Stage 8) stages consume. If omitted here, those stages discover it at runtime (`docs/architecture.md`, then `_bmad-output/planning-artifacts/architecture.md`). Capturing it now persists the choice across resume and avoids re-prompting.

When seeding from `--manifest`, parse it deterministically: `uv run {manifestScript} <manifest-file>`. If the result's `errors[]` is non-empty (exit 1), HALT listing the offending line numbers — never run a partial target set. When seeding from `--brief`, read the existing `campaign-brief.yaml` directly.

If no targets can be collected (empty interactive input or empty `--brief`/`--manifest`), HALT with guidance — a campaign needs at least one target.

### §2 — Health Queue Preference

Default to `"local"` (project-local findings queue). Present the opt-in prompt:

> Send anonymized quality findings to the shared improvement queue? [y/N]

- **y** — set `health_findings_queue` to `"improvement"`
- **N** (default) — keep `health_findings_queue` as `"local"`

In headless mode: auto-select `"local"` (N) and log the auto-decision.

### §3 — Build State Object

Construct `_campaign-state.yaml` in memory from collected inputs. Use the campaign-wide quality gate resolved in On Activation: `{qualityGateHard}` / `{qualityGateSoftTarget}` / `{qualityGateSoftFallback}`. Note: `repo_url` (collected in §1) is NOT part of the state schema — it belongs in the brief only (§5). The state schema enforces `additionalProperties: false`, so including it would fail validation.

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
  health_findings_queue: "{local or improvement}"
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

### §4 — Write + Validate State

1. Ensure the directory `{campaignWorkspacePath}/` exists (create if missing).
2. Write the constructed state to `{stateFile}`. This is the initial creation — no `.bak` is needed for the first write; all subsequent steps use read-backup-modify-write.
3. Run `uv run {validateScript} --state-file {stateFile}`. On non-zero (invalid), **HALT** (exit 3) with the script's `errors[]` — do not proceed to brief generation with an invalid state file.

### §5 — Generate Brief

Populate `{templateFile}` with collected inputs and write to `{briefFile}`. Fill in:

- `campaign_name` — from collected input
- `created_at` — current ISO-8601 timestamp with timezone
- `targets` — array of target entries with `name`, `repo_url`, `tier`, `pin`, `depends_on`
- `quality_gate` — `{qualityGateHard}` / `{qualityGateSoftTarget}` / `{qualityGateSoftFallback}`
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
