---
nextStepFile: 'write-and-validate.md'
skillTemplateData: '{skillTemplatePath}'
quickMetadataRendererProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-quick-metadata.py'
  - '{project-root}/src/shared/scripts/skf-render-quick-metadata.py'
---

<!-- Config: communicate in {communication_language}. Generated SKILL.md text in {document_output_language}. -->

# Step 4: Compile

## STEP GOAL:

To assemble the best-effort SKILL.md document, context-snippet.md in Vercel-aligned indexed format, and metadata.json with `source_authority: community` from the extraction inventory. Present compiled output for review before validation.

## Rules

- Focus only on assembling the three output documents — do not write files to disk (that's step 6)
- Follow template structure exactly from {skillTemplateData}
- Mark any sections with insufficient data as best-effort
- A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true. Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even when the halt reads as the end of the run (`references/halt-contract.md`).

## Steps

### 1. Load Skill Template

Load {skillTemplateData} to understand:
- SKILL.md required and optional sections
- context-snippet.md Vercel-aligned indexed format
- metadata.json field requirements

### 2. Assemble SKILL.md

Populate the SKILL.md section structure from `{skillTemplateData}` § "SKILL.md Section Structure" (the frontmatter skeleton and the Required/Optional section list live there) using extraction_inventory. The rules below are the deltas the template does not encode:

**Frontmatter rules (agentskills.io compliance):**
- `name`: lowercase alphanumeric + hyphens only, must match the skill output directory name. Prefer gerund form (`processing-pdfs`) for clarity.
- `description`: non-empty, max 1024 chars, optimized for agent discovery. Use third-person voice ("Processes..." not "I can..." / "You can...") so it reads correctly in the agent's skill index.
- No other frontmatter fields — only `name` and `description` for community skills

**Per-section override wiring:**
- **Description:** From `{overrides.description}` if set (subject to the same length/voice checks as extracted descriptions); otherwise from extraction_inventory.description (README-derived)
- **Key Exports:** From `{overrides.exports}` if set (comma-separated names parsed and trimmed; empty items skipped); otherwise from extraction_inventory.exports — list each with name, type, brief description

**Skills module** (`repo_shape: skills-module`): Unless `{overrides.exports}` is set, Key Exports lists the skills first, each with its description, then the menu codes, each with its description, display name and the skill it runs, in the inventory's order. Usage Patterns gives one entry per `module-help.csv` usage pattern in the inventory; with no `module-help.csv`, it comes from the README as for a library.

**Scripts & Assets Note** (add as an optional section when step 3's `{run_dir}/sniff.json` lists a `scripts/`, `bin/`, `assets/`, `templates/` or `schemas/` folder: its `asset_dir_count` is above 0): "This package may include scripts and assets. Run create-skill for full extraction with provenance tracking."

**If confidence is low** — include a note: "This skill was generated with limited source data. Consider running create-skill for a more thorough compilation."

### 3. Generate Context Snippet

**If `{overrides.skip_snippet}` is true** — skip generation and note in the §5 preview: "context-snippet.md skipped per `--skip-snippet` override." Step-05 §2 will skip the corresponding write; step 5 §5 advisory snippet validation will report a "skipped" entry.

Otherwise, produce context-snippet.md in the Vercel-aligned indexed format from `{skillTemplateData}` § "context-snippet.md Format" (~80-120 tokens).

Its `{version}` is the version §4 gives `metadata.json`, which names the version folder: `{target_version}` when step 1 parsed one from the target, else the first `version` set in step 3's extraction files (`{run_dir}/extract.json` first), else `1.0.0`.

The snippet anchors point to the QS template's actual headings — `#usage-patterns` (Usage Patterns) and `#key-exports` (Key Exports). The QS template has no `## Quick Start` / `## Key Types` headings (those are Deep-tier sections), so the Deep-tier anchors `#quick-start` / `#key-types` would dangle. If the assembled SKILL.md is missing the referenced heading, omit that line rather than emit a dangling anchor.

**If fewer than 5 exports:** Use all available exports.
**If no exports:** Omit the api line.
**If no gotchas known:** Omit the gotchas line.
**If `repo_shape` is `skills-module`:** the api line names up to five skills, without `()`, and the key-types summary lists the menu codes when there are any.

### 4. Generate Metadata JSON

Run the shared renderer. It applies the constants, takes the export list, the dependencies and the manifest's version from step 3's extraction files, probes the installed SKF's version for `tool_versions.skf`, computes export counts and the ISO 8601 UTC timestamp, and writes the canonical envelope per `{skillTemplateData}` § "metadata.json Format".

**Resolve `{quickMetadataRenderer}`** from `{quickMetadataRendererProbeOrder}`; first existing path wins. If no candidate exists, fall back to in-prompt rendering of the canonical envelope per `{skillTemplateData}` § "metadata.json Format", and write it to `{run_dir}/metadata.json`.

Stage the fields this step and step 1 decide through a quoted heredoc, so a description holding an apostrophe, a quote or a `$` reaches the file as written, then run the renderer:

```bash
cat > "{run_dir}/metadata-input.json" <<'SKF_JSON'
{"name": "{repo_name}", "description": "<the SKILL.md frontmatter description>", "version": <"{target_version}" or null>, "language": "{language}", "source_repo": "{resolved_url}", "source_root": "<path or empty>", "source_commit": "<source_ref or empty>", "source_package": "<package name or empty>", "compatibility": "<semver-range or empty>", "language_hint": <"{language_hint}" or null>, "scope_hint": <"{scope_hint}" or null>, "exports": <the --exports names as a JSON list, or null>}
SKF_JSON
uv run {quickMetadataRenderer} --input "{run_dir}/metadata-input.json" --extraction "{run_dir}/extract.json" --skf-root "{project-root}/_bmad/skf" --output "{run_dir}/metadata.json"
```

Write each value as JSON: a string in double quotes with any `"` or `\` escaped, and `null` where the line says so. `version` is the version step 1 parsed from the target, else `null`, which takes the manifest's version (else `1.0.0`); `exports` is `{overrides.exports}` when set, else `null`, which takes the extraction's exports; an empty `source_package` takes the manifest's package name. Pass one `--extraction` per file step 3 wrote, the parent first: `{run_dir}/extract.json`, then each `{run_dir}/extract-module-<n>.json` of a multi-module build in `<n>` order and `{run_dir}/extract-added.json` when §3 staged it. Do not type the export list or the dependencies: the renderer reads them from those files.

The renderer writes `{run_dir}/metadata.json` and prints it on stdout. Read it as `metadata` for the §5 preview; step 5 §2 installs that file.

If the renderer exits non-zero, its error line names the file or the field at fault: fix that file once (stage `metadata-input.json` again with the missing field, or stage an empty extraction file as quick-extract §3's empty envelope) and run the command again. If it fails a second time, render the envelope in-prompt as the no-candidate fallback above does.

### 5. Present Compiled Output for Review

**If `{headless_mode}` is true** — skip the inline preview (no human reviewer reads it) and emit a one-line summary instead:

"Compiled: SKILL.md ({section_count} sections, {export_count} exports), context-snippet.md (~{snippet_token_count} tokens), metadata.json (version {metadata.version}, confidence {confidence}). Auto-approving [C]."

Then proceed directly to §6 — the GATE default action takes over.

**Otherwise (interactive mode):**

"**Compilation complete. Review before validation:**

---

**SKILL.md Preview:**

{Display the full assembled SKILL.md content}

---

**context-snippet.md:**

{Display the snippet}

---

**metadata.json:** version {metadata.version}, confidence tier {metadata.confidence_tier}, {metadata.stats.exports_documented} exports documented (step 5 writes the full file)

---

**Extraction confidence:** {confidence}

Review the output above, then choose: [C] continue to validation, [E] edit the description, [S] adjust scope and re-extract, or [Q] quit without writing."

### 6. Present MENU OPTIONS

Display: **Select:** [C] Continue to Validation · [E] Edit description · [S] Adjust scope and re-extract · [Q] Quit without writing

#### Menu Handling Logic:

- **IF C** — Load, read entire file, then execute {nextStepFile}.
- **IF E**: Ask the user for a replacement description ("New description (1–1024 chars):"). Update SKILL.md frontmatter `description` in the compiled output, stage `{run_dir}/metadata-input.json` again with the new description and run §4's renderer command again, so `{run_dir}/metadata.json` carries it, then re-render the §5 preview and redisplay this menu. Do not edit `metadata.json` by hand, and do not re-run extraction.
- **IF S**: Ask the user for an adjusted `scope_hint` ("New scope (e.g. `src/server/`, `packages/core/`):") and optionally a `language_hint`. A non-empty new language hint sets `language` to it, `language_resolution` to `hint` and `detected_languages` to `[]`, as step 1 §4 does for a hint. Update the extraction context with the new hints, then load `quick-extract.md` to re-extract. The new extraction returns to §1 of this step on completion. Discards the prior compiled output.
- **IF Q**: HARD HALT with **exit code 6 (user-cancelled)**: "Compilation cancelled. No files written." Stage `{"phase": "compile", "halt_reason": "user-cancelled", "reason": "Compilation cancelled. No files written.", "skill_package": null}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"` (`references/halt-contract.md`). Do not proceed to validation; do not write any artifacts.
- **IF Any other** — Help the user adjust the compiled output (treated as a free-form revision request), then redisplay the menu.

#### Gate:

- Halt and wait for user input after presenting the compiled output; only [C] (or a headless auto-approve) chains to `{nextStepFile}` for validation.
- **GATE [default: C]**: if `{headless_mode}`, auto-proceed with [C] Continue, log "headless: auto-approve compiled output", record the decision (stage `{"gate": "compile.review", "default_action": "C", "taken_action": "C", "reason": "headless: auto-approved the compiled output"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`), and print this step's `done` event and step 5's `start` event (`references/halt-contract.md`) before loading `{nextStepFile}`.
- [E] re-renders the preview without re-running extraction; [S] discards the compiled output and re-runs step 3 with new hints.

