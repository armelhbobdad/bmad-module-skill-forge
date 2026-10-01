---
ratifyTargetFile: 'confirm-brief.md'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Ratify an Existing Brief

A pre-authored `skill-brief.yaml` (typically from `skf-analyze-source`) is reviewed and rewritten in place instead of derived again. Step 1 loads this file with the brief's path in two ways: interactively, when the §3.1 target is a brief or a folder holding one (§3.1a), and headlessly, when the input gate in `references/headless-args.md` finds a `from_brief` argument. Steps 2 and 3 do not run: they would derive again what the brief already holds. The run goes on at step 4, which reviews the brief, and step 5 writes it in place. `references/invocation-contract.md` states the ratify contract.

## 1. Validate the Brief

The brief path is the given path when it ends in `skill-brief.yaml`, else `<path>/skill-brief.yaml`. Resolve `{validateBriefSchemaHelper}` from `{validateBriefSchemaProbeOrder}` (first existing path wins; HALT if no candidate exists), then run:

```bash
uv run {validateBriefSchemaHelper} <resolved-brief-path>
```

It returns `{valid, errors[], warnings[], halt_reason, brief}`:

- **`valid: false`**, interactive: display "**Brief at `{path}` is invalid:** {first error message}. Pick a different brief, or supply a repo / docs URL instead." and re-display the step 1 §3.1 prompt: the user may have pointed at the wrong file.
- **`valid: false`**, headless, with the script's `halt_reason` `brief-missing` (the path is absent or unreadable): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-missing"` (SKILL.md Halt Contract), surface `errors[]` to the operator log, then HALT (exit code 2).
- **`valid: false`**, headless, with any other `halt_reason` (`brief-malformed` or `brief-invalid`): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-invalid"` (SKILL.md Halt Contract), surface `errors[]` to the operator log, then HALT (exit code 2).
- **`valid: true`**: log any non-empty `warnings[]`, add each to `workflow_warnings[]` as `<field>: <message>`, and continue with the parsed `brief`.

## 2. Ratify Menu

**GATE [default: R]**: a headless run takes `[R]` without showing the menu: its `from_brief` argument already chose to ratify.

```
**Existing brief detected at `{path}`.**

- **Name:** {brief.name}
- **Target:** {brief.source_repo}
- **Description:** "{brief.description}"
- **Created:** {brief.created} by {brief.created_by}
- **Scope:** {brief.scope.type}

Pick one:
  [R] Ratify: review in step 4 and write (overwriting this file once approved)
  [F] Start fresh: discard this brief and re-prompt for a target
  [X] Cancel and exit
```

Wait for the user's response:

- **[R]**: continue at §3.
- **[F]**: discard the brief and re-display the step 1 §3.1 prompt.
- **[X]**: remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). The brief at `{path}` is left as it is.
- **Any other input**: treat it as a new step 1 §3.1 response and route it there (a GitHub URL typed here means the user wants that repository briefed instead).

## 3. Hydrate and Route

Store `ratify_mode: true` and `ratify_source_path: <resolved-brief-path>` in workflow context, then hydrate the brief context variables from the parsed `brief`, so step 4 has the field set steps 1 to 3 would derive. This is the one mapping list every route uses:

- `name` ← `brief.name`; `version` ← `brief.version`; `target_version` ← `brief.target_version`
- `target_ref` ← `brief.target_ref`; `source_ref` ← `brief.source_ref` (optional git refs; preserve when present)
- `source_repo` ← `brief.source_repo`; `source_type` ← `brief.source_type` (`source` when absent, the schema default); `source_authority` ← `brief.source_authority`; `doc_urls` ← `brief.doc_urls`
- `language` ← `brief.language`; `description` ← `brief.description`; `forge_tier` ← `brief.forge_tier`
- `created` ← `brief.created`; `created_by` ← `brief.created_by`
- `scope.type` / `scope.include` / `scope.exclude` / `scope.tier_a_include` / `scope.notes` / `scope.rationale` / `scope.amendments` ← `brief.scope.*` (preserve `tier_a_include` and the `amendments` log verbatim: do not re-derive or drop them)
- `scope.registry_path` / `scope.ui_variants` / `scope.demo_patterns` ← `brief.scope.*` (a component library's registry file, design system variants and demo globs; skf-create-skill writes the registry file and the demo globs back once the user confirms them: preserve all three verbatim)
- `scripts_intent` ← `brief.scripts_intent`; `assets_intent` ← `brief.assets_intent`

Then load, read entirely, and execute `{ratifyTargetFile}` (step 4). Under headless it confirms with `[C]`, and step 5 overwrites the brief in place with no `force` needed.
