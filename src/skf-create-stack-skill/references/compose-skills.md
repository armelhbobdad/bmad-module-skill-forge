---
nextStepFile: 'compose-scope.md'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Pick the Constituent Skills

## STEP GOAL:

Pick the constituent skills of a compose-mode stack with the candidates helper, and record each one's package, metadata and hash for the steps that follow.

## Rules

- Render the candidates helper's JSON; never join candidates by hand
- Do not set the scope (Step 03) or read a constituent's SKILL.md (Step 04)

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "compose"}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

### 1. Pick the Constituent Skills

Pick the constituent skills with the shared helper, which keeps only the skills SKF generated (a `metadata.json` SKF marker: see `knowledge/version-paths.md` Ownership) and gates every candidate in one call. When step 1 kept `{skill_candidates}`, use that result: it ran this same call. Otherwise resolve `{enumerateStackSkillsHelper}` from `{enumerateStackSkillsProbeOrder}` (first existing path wins; if no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `compose-skills:enumerate`) with "**Cannot proceed.** `skf-enumerate-stack-skills.py` is missing, so no constituent skill can be picked. Re-install SKF, then re-run.") and run it, passing `--explicit` with the `explicit_deps` entries as given, comma-separated, when step 1 bound them (the helper reduces a package path to its skill folder):

```bash
uv run {enumerateStackSkillsHelper} candidates {skills_output_folder} [--explicit "<names>"]
```

Render its JSON as it stands, never re-joining candidates by hand. An exit `1` (no skills folder) counts as an empty `kept[]`:

- `manifest_parse_error` is not null: log `"{manifest_parse_error}: using the active links instead"`.
- `not_skf_output` is not empty: display it once, "Skipped (not SKF output): {not_skf_output}".
- Each `excluded[]` entry: log its `message` as given, one line each.
- `stale_manifest_keys` is not empty (**stale manifest**: the export manifest names a skill whose folder is gone): HALT (exit 3, `halt_reason: "resolution-failure"`, phase `compose-skills:stale-manifest`) with a manifest-corruption diagnostic naming each key and pointing the user at `[SKF-update-skill]` to repair.
- `kept[]` is empty: HALT (exit 3, `halt_reason: "resolution-failure"`, phase `compose-skills:no-skills`) with "**Cannot proceed in compose-mode.** No individual skills found in `{skills_output_folder}` (stack skills are never constituents). Run [CS] Create Skill or [QS] Quick Skill to generate individual skills first, then re-run [SS]."

A composes cycle is not an exclusion: step 4 (`references/compose-extract.md` §1) halts on one that involves a confirmed skill.

For each `kept[]` entry:
1. Store its `name`, the top-level folder, as `skill_dir` (distinct from the metadata `name`).
2. `skill_package_path` ← `{skills_output_folder}/{path}` from that entry: the package whose exports and `metadata_hash` the helper reported, so path and hash come from one resolution (the helper follows `active`, as the manifest-lag guard in `knowledge/version-paths.md` does).
3. Read `metadata.json` from `skill_package_path` for the fields the entry lacks: name, version and source_authority. The entry gives language, confidence_tier, source_repo and the export count (`exports`).
4. **Record the constituent metadata_hash:** take its `metadata_hash` (a `sha256:`-prefixed digest of the raw `metadata.json`) from the same `kept[]` entry and store it in workflow state alongside `skill_package_path`. The script is the single source of this hash (never hand-compute it); step 4 (`references/compose-extract.md` §1) checks it for drift and records the provenance anchor.
5. Store as `raw_dependencies` with source: "existing_skill" (`"explicit"` for a name from `explicit_deps`)

Report the `{N}` loaded skills, for each: name, language, confidence tier, export count, and source.

### 2. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.
