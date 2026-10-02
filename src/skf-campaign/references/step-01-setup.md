---
nextStepFile: 'step-02-strategy.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
templateFile: '{briefTemplatePath}'
stateScript: 'scripts/campaign-state.py'
manifestScript: 'scripts/campaign-parse-manifest.py'
---

<!-- Config: communicate in {communication_language}. -->

# Setup

## STEP GOAL:

Collect campaign inputs from the operator, create the initial `_campaign-state.yaml`, and generate `campaign-brief.yaml` so the campaign has a persistent starting point that survives context death.

## RULES

- This is the only step that creates the state file, with the helper's `init` operation (`{stateScript}`); every later write goes through `{stateScript}` too (State Contract in `references/campaign-contracts.md`), so no target, timestamp or gate value is ever typed into the state by hand.
- If `{headless_mode}` is true, draw inputs from `--brief`/`--manifest` (On Activation step 4) and auto-proceed through confirmation gates with the default action, logging each auto-decision with `uv run {stateScript} log --log-file {decisionLogFile} --type auto --text '<entry>'`; emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`.

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

A field no source gives takes its default: `tier` `"A"`, `pin` `null`, `depends_on` empty, and `campaign_name` the brief's `campaign_name`, else `{project_name}`. A Tier A target may not depend on a Tier B target: Tier B skills are built after the skill loop, so Strategy rejects that plan.

Every target goes through `{manifestScript}`, whatever its source, so no target reaches state unchecked. It rejects a malformed target, a `repo_url` that is no GitHub repository (it reads a URL, an SSH URL or `owner/repo`, and writes each as `https://github.com/<owner>/<repo>`), a name that is no skill name (lower-case letters, digits and hyphens, at most 64 characters), a Tier A pin that is no X.Y.Z version (the only pin brief-skill builds from) and a duplicate name. It fills an empty name from the repository (`filled_names`), and lists each `depends_on` name that is no target (`dangling_depends_on`) and each Tier A target that depends on a Tier B target (`tier_inversions`), each entry naming its `skill` and `depends_on`. The state and the brief take their targets from the script's `targets[]`, never from the raw source.

**Manifest format** (a `--manifest` file, and a pasted list rewritten for the script): one `name,repo_url,tier,pin` target per line, where an empty `name` takes the repository's name and an empty `pin` means the latest release; a trailing `;dep1,dep2` segment sets `depends_on`; blank and `#` lines are skipped.

**Headless** (`--brief` and `--manifest` imply it): take the inputs from the source On Activation parsed. Parse a `--manifest` file with `uv run {manifestScript} <manifest-file>` and a `--brief` file with `uv run {manifestScript} --brief <brief-file>`, which also returns the brief's `campaign_name`, `quality_gate`, `architecture_doc_path` and `notes` under `brief`. Headless asks nothing about `dangling_depends_on` or `tier_inversions`: Strategy halts on them (exit code 4).

**Interactive:** open with this one question, and ask nothing before it:

> Share the targets for this campaign in whatever form you have them: a manifest or `campaign-brief.yaml` path, a pasted list, or repository URLs. Add a campaign name and a directive or architecture document path if you have them.

Turn the answer into targets: a manifest path goes through `uv run {manifestScript} <manifest-file>`, and a brief path through `uv run {manifestScript} --brief <brief-file>`. A pasted list or bare repository URLs are first rewritten as manifest lines in the manifest format above (leave the name empty when none is given: the script takes it from the repository), then piped to `uv run {manifestScript} -`. Show the drafted campaign once for correction: the campaign name, the directive and architecture paths (or none), and one table of the targets with `name`, `repo_url`, `tier`, `pin` and `depends_on`. After the operator's corrections, ask only about what is still missing or ambiguous, all in one question, read from the script's output rather than by matching names yourself: each `dangling_depends_on` entry (a `depends_on` name that is no target), each `tier_inversions` entry (make the dependency Tier A, or drop it) and each `filled_names` entry (confirm the name). Run a corrected set through the script again before §2.

A target the script rejects (`errors[]` non-empty, exit 1: a malformed manifest line or brief target, a `repo_url` that is no GitHub repository, a name that is no skill name, a Tier A pin that is no X.Y.Z version, a duplicate name, a brief `pin` that is not a string) never yields a partial target set: in headless, HALT (exit code 2, `invalid-input`) listing each error's line or target number and message; interactively, show them and ask for those targets corrected. An exit 2 (a file that is missing, unreadable or not a YAML mapping) HALTs (exit code 2, `invalid-input`) with its `error`.

If no targets can be collected (an empty answer, or an empty `--brief` or `--manifest`), HALT (exit code 2, `invalid-input`) with guidance: a campaign needs at least one target.

### §2: Create State

Settle the campaign name (the brief's `campaign_name`, else the operator's, else `{project_name}`), then create the state in one call. Pipe in the parse of the settled targets: the last §1 parse run again (the manifest file, `--brief <brief-file>`, or the corrected manifest lines on stdin), so the state takes its targets from the script's `targets[]`, never from the raw source:

```
uv run {manifestScript} <the settled source> | uv run {stateScript} init --state-file {stateFile} --targets-file - --name "<campaign_name>" --hard "{qualityGateHard}" --soft-target {qualityGateSoftTarget} --soft-fallback {qualityGateSoftFallback} [--brief-file <brief-file>] [--directive-path <directive_path>] [--architecture-doc-path <architecture_doc_path>]
```

Pass `--brief-file` when the targets came from a campaign brief: each value its `quality_gate` gives wins over the customize.toml one. The directive's `## Quality Overrides` apply later, while the campaign runs, and are never written here. The helper settles and checks the gate with `campaign-quality-gate.py check`, creates `{campaignWorkspacePath}/`, writes every target as a `pending` skill (`repo_url` stays in the brief: the state schema has no place for it), stamps `started_at` and `last_updated` from the clock, and validates the state before it writes it. There is no earlier state, so no `.bak` is written.

On exit 2, HALT (exit code 2, `invalid-input`) with its `error` and `errors[]`; nothing is written: a gate the gate script rejects (a hard gate other than `zero-critical-high`, a soft value outside 0 to 100, a fallback above the target, or a brief it cannot read), targets that hold errors, or a state file or backup that already exists. On exit 3, HALT (exit code 3, `invalid-state`) with its `errors[]`.

### §3: Generate Brief

Populate `{templateFile}` with collected inputs and write to `{briefFile}`. Fill in:

- `campaign_name`: the name §2 settled
- `created_at`: the `last_updated` of the §2 output
- `targets`: one entry per target with `name`, `repo_url`, `tier`, `pin` and `depends_on`, plus every other field its source gave it (a language or scope hint, for example)
- `quality_gate`: the `quality_gate` of the §2 output
- `architecture_doc_path`: from collected input, or empty string if not provided
- `notes`: operator-provided context, or empty string

The brief is a machine-readable snapshot enabling fresh-context resume.

## OUTPUT

Confirm state file creation and brief generation. Display summary:

- Campaign name
- Number of targets

Chain to `{nextStepFile}`.
