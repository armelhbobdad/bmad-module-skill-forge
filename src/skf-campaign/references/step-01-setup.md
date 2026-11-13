---
nextStepFile: 'step-02-strategy.md'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
stateScript: 'scripts/campaign-state.py'
manifestScript: 'scripts/campaign-parse-manifest.py'
---

<!-- Config: communicate in {communication_language}. -->

# Setup

## STEP GOAL:

Collect campaign inputs from the operator, create the initial `_campaign-state.yaml`, and generate `campaign-brief.yaml` so the campaign has a persistent starting point that survives context death.

## RULES

- This is the only step that creates the state file, with the helper's `init` operation (`{stateScript}`); every later write goes through `{stateScript}` too (State Contract in `references/campaign-contracts.md`), so no target, timestamp or gate value is ever typed into the state or the brief by hand.
- If `{headless_mode}` is true, draw inputs from `--brief`/`--manifest` (On Activation step 4) and auto-proceed through confirmation gates with the default action, logging each auto-decision with `uv run {stateScript} log --log-file {decisionLogFile} --type auto --text '<entry>'`; emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`.

## TASKS

### §0: Archive the Previous Campaign

SKILL.md Mode Routing 3 sends an overwrite here with the old campaign still on disk. Run this section only when `{stateFile}` or `{stateFile}.bak` exists; otherwise start at §1. Run `uv run {stateScript} archive --state-file {stateFile} --brief-file {briefFile}`, which moves the state, its `.bak` and the brief into a new folder under `{campaignWorkspacePath}/archive/` (§2's `init` refuses a state or backup that exists), and log the `archive_dir` it returns (type `decision`): `uv run {stateScript} log --log-file {decisionLogFile} --type decision --text 'overwrite: previous campaign archived to <archive_dir>'`. On exit 2, HALT (exit code 2, `invalid-input`) with its `error`. A brief path that names `{briefFile}`, from `--brief` or from §1's answer, is read from `archive_dir` instead.

### §1: Collect Inputs

A campaign needs a `campaign_name` and its target libraries. Each target has:

- `name`: skill name
- `repo_url`: source repository URL
- `tier`: `"A"` (full pipeline) or `"B"` (batch)
- `pin`: version pin (string), or `null` for latest
- `depends_on`: array of skill names this target depends on (may be empty)

Two paths are optional:

- `directive_path`: a `_campaign-directive.md` file with operator directives (contract: `references/campaign-directive-spec.md`)
- `architecture_doc_path`: the architecture document the capstone (Stage 6), verify (Stage 7) and refine (Stage 8) stages consume. When no source gives one (a `--manifest`, a brief without `architecture_doc_path`, an answer that names none), look for it, in both modes: `{project-root}/docs/architecture.md`, then `{project-root}/_bmad-output/planning-artifacts/architecture.md`. Pass the path given or found to `init` with `--architecture-doc-path` (§2); with none, the capstone composes without it, and verification and refinement skip and log it.

A field no source gives takes its default: `tier` `"A"`, `pin` `null`, `depends_on` empty, and `campaign_name` the brief's `campaign_name`, else `{project_name}`. A Tier A target may not depend on a Tier B target: Tier B skills are built after the skill loop, so Strategy rejects that plan.

Every target goes through `{manifestScript}`, whatever its source, so no target reaches state unchecked. It rejects a malformed target, a `repo_url` that is no GitHub repository (it reads a URL, an SSH URL or `owner/repo`, and writes each as `https://github.com/<owner>/<repo>`), a name that is no skill name (lower-case letters, digits and hyphens, at most 64 characters), a Tier A pin that is no X.Y.Z version (the only pin brief-skill builds from) and a duplicate name. It fills an empty name from the repository (`filled_names`), and lists each `depends_on` name that is no target (`dangling_depends_on`) and each Tier A target that depends on a Tier B target (`tier_inversions`), each entry naming its `skill` and `depends_on`. The state and the brief take their targets from the script's `targets[]`, never from the raw source.

**Manifest format** (a `--manifest` file, and a pasted list rewritten for the script): one `name,repo_url,tier,pin` target per line, where an empty `name` takes the repository's name and an empty `pin` means the latest release; a trailing `;dep1,dep2` segment sets `depends_on`; blank and `#` lines are skipped.

**Headless** (`--brief` and `--manifest` imply it): take the inputs from the source On Activation parsed. Parse a `--manifest` file with `uv run {manifestScript} <manifest-file>` and a `--brief` file with `uv run {manifestScript} --brief <brief-file>`, which also returns the brief's `campaign_name`, `quality_gate`, `architecture_doc_path` and `notes` under `brief`. Headless asks nothing about `dangling_depends_on` or `tier_inversions`: Strategy halts on them (exit code 4).

**Interactive:** open with this one question, and ask nothing before it:

> Share the targets for this campaign in whatever form you have them: a manifest or `campaign-brief.yaml` path, a pasted list, or repository URLs. Add a campaign name and a directive or architecture document path if you have them.

Turn the answer into targets: a manifest path goes through `uv run {manifestScript} <manifest-file>`, and a brief path through `uv run {manifestScript} --brief <brief-file>`. A pasted list or bare repository URLs are first rewritten as manifest lines in the manifest format above (leave the name empty when none is given: the script takes it from the repository), then piped to `uv run {manifestScript} -`. Show the drafted campaign once for correction: the campaign name, the directive path (or none), "architecture doc: <path>" or "architecture doc: none found, so verification and refinement will be skipped", and one table of the targets with `name`, `repo_url`, `tier`, `pin` and `depends_on`. After the operator's corrections, ask only about what is still missing or ambiguous, all in one question, read from the script's output rather than by matching names yourself: each `dangling_depends_on` entry (a `depends_on` name that is no target), each `tier_inversions` entry (make the dependency Tier A, or drop it) and each `filled_names` entry (confirm the name). Run a corrected set through the script again before §2.

A target the script rejects (`errors[]` non-empty, exit 1, including a brief `pin` that is not a string) never yields a partial target set: in headless, HALT (exit code 2, `invalid-input`) listing each error's line or target number and message; interactively, show them and ask for those targets corrected. An exit 2 (a file that is missing, unreadable or not a YAML mapping) HALTs (exit code 2, `invalid-input`) with its `error`.

If no targets can be collected (an empty answer, or an empty `--brief` or `--manifest`), HALT (exit code 2, `invalid-input`) with guidance: a campaign needs at least one target.

### §2: Create State

Settle the campaign name (the brief's `campaign_name`, else the operator's, else `{project_name}`), then create the state in one call. Pipe in the parse of the settled targets: the last §1 parse run again (the manifest file, `--brief <brief-file>`, or the corrected manifest lines on stdin):

```
uv run {manifestScript} <the settled source> | uv run {stateScript} init --state-file {stateFile} --targets-file - --name "<campaign_name>" --soft-target {qualityGateSoftTarget} --soft-fallback {qualityGateSoftFallback} [--brief-file <brief-file>] [--directive-path <directive_path>] [--architecture-doc-path <architecture_doc_path>] --brief-out {briefFile} [--notes '<operator notes>']
```

Pass `--brief-file` when the targets came from a campaign brief: each value its `quality_gate` gives wins over the customize.toml one, and the new brief keeps only those values, so a campaign seeded from it again takes the others from customize.toml. After `init` exits 0, log one entry per key of its `gate_from_brief`: `uv run {stateScript} log --log-file {decisionLogFile} --type event --text 'quality_gate.<key> <value> comes from the campaign brief, not customize.toml'`. The directive's `## Quality Overrides` apply later, while the campaign runs, and are never written here. Pass `--notes` only with notes the operator gave, single-quoted as a decision-log entry is (`references/campaign-contracts.md`); without it a brief's own `notes` carry over.

On exit 2, HALT (exit code 2, `invalid-input`) with its `error` and `errors[]`; nothing is written: a gate the gate script rejects (a hard gate other than `zero-critical-high`, a soft value outside 0 to 100, a fallback above the target, or a brief it cannot read), targets that hold errors, a brief template that is no YAML mapping, or a state file or backup that already exists. On exit 3, HALT (exit code 3, `invalid-state`) with its `errors[]`.

## OUTPUT

Confirm state file creation and brief generation. Display summary:

- Campaign name
- Number of targets

Chain to `{nextStepFile}`.
