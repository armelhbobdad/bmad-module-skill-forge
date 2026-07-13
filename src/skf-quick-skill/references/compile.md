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

**Scripts & Assets Note** (add as an optional section if source contains `scripts/`, `bin/`, `assets/`, `templates/`, or `schemas/` directories): "This package may include scripts and assets. Run create-skill for full extraction with provenance tracking."

**If confidence is low** — include a note: "This skill was generated with limited source data. Consider running create-skill for a more thorough compilation."

### 3. Generate Context Snippet

**If `{overrides.skip_snippet}` is true** — skip generation and note in the §5 preview: "context-snippet.md skipped per `--skip-snippet` override." Step-05 §2 will skip the corresponding write; step 5 §5 advisory snippet validation will report a "skipped" entry.

Otherwise, produce context-snippet.md in the Vercel-aligned indexed format from `{skillTemplateData}` § "context-snippet.md Format" (~80-120 tokens).

The snippet anchors point to the QS template's actual headings — `#usage-patterns` (Usage Patterns) and `#key-exports` (Key Exports). The QS template has no `## Quick Start` / `## Key Types` headings (those are Deep-tier sections), so the Deep-tier anchors `#quick-start` / `#key-types` would dangle. If the assembled SKILL.md is missing the referenced heading, omit that line rather than emit a dangling anchor.

**If fewer than 5 exports:** Use all available exports.
**If no exports:** Omit the api line.
**If no gotchas known:** Omit the gotchas line.

### 4. Generate Metadata JSON

Run the shared renderer against the assembled state. The helper applies the constants, echoes input-derived fields, computes export counts and the ISO 8601 UTC timestamp, and emits the canonical envelope per `{skillTemplateData}` § "metadata.json Format".

**Resolve `{quickMetadataRenderer}`** from `{quickMetadataRendererProbeOrder}`; first existing path wins. If no candidate exists, fall back to in-prompt rendering of the canonical envelope per `{skillTemplateData}` § "metadata.json Format".

**Probe `tool_versions.skf` first** (the helper expects it as input — the filesystem walk stays here because the helper does no I/O):

1. Read `{project-root}/_bmad/skf/package.json` → take `version`
2. If absent, read `{project-root}/_bmad/skf/VERSION`
3. If absent, set to `"unknown"`

Build the input payload from the extraction inventory + step 1 resolution + the probed `tool_versions.skf` and pipe it to the renderer:

```bash
echo '{"name":"<name>","version":"<v>","description":"<desc>","language":"<lang>","source_repo":"<url>","source_root":"<path or empty>","source_commit":"<source_ref or empty>","source_package":"<package or name>","exports":[{"name":"...","type":"..."}],"dependencies":["..."],"compatibility":"<semver-range or empty>","language_hint":<hint or null>,"scope_hint":<hint or null>,"skf_version":"<probed>"}' \
  | python3 {quickMetadataRenderer}
```

The renderer emits the rendered metadata.json on stdout. Capture the output as `metadata` for the §5 preview and step 5 §2's deliverable write.

### 5. Present Compiled Output for Review

**If `{headless_mode}` is true** — skip the inline preview (no human reviewer reads it) and emit a one-line summary instead:

"Compiled: SKILL.md ({section_count} sections, {export_count} exports), context-snippet.md (~{snippet_token_count} tokens), metadata.json (version {version}, confidence {confidence}). Auto-approving [C]."

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

**metadata.json:**

{Display the JSON}

---

**Extraction confidence:** {confidence}
**Exports documented:** {count}

Review the output above, then choose: [C] continue to validation, [E] edit the description, [S] adjust scope and re-extract, or [Q] quit without writing."

### 6. Present MENU OPTIONS

Display: **Select:** [C] Continue to Validation · [E] Edit description · [S] Adjust scope and re-extract · [Q] Quit without writing

#### Menu Handling Logic:

- **IF C** — Load, read entire file, then execute {nextStepFile}.
- **IF E** — Ask the user for a replacement description ("New description (1–1024 chars):"). Update SKILL.md frontmatter `description` and `metadata.json.description` in the in-memory compiled output, then re-render the §5 preview and redisplay this menu. Do not re-run extraction.
- **IF S** — Ask the user for an adjusted `scope_hint` ("New scope (e.g. `src/server/`, `packages/core/`):") and optionally a `language_hint`. Update the extraction context with the new hints, then load `quick-extract.md` to re-extract. The new extraction returns to §1 of this step on completion. Discards the prior compiled output.
- **IF Q** — HARD HALT with **exit code 6 (user-cancelled)** per the exit-code map in `references/halt-contract.md`: "Compilation cancelled. No files written." Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "compile"`, `error.code: "user-cancelled"`, `skill_package: null`). Do not proceed to validation; do not write any artifacts.
- **IF Any other** — Help the user adjust the compiled output (treated as a free-form revision request), then redisplay the menu.

#### Gate:

- Halt and wait for user input after presenting the compiled output; only [C] (or a headless auto-approve) chains to `{nextStepFile}` for validation.
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-approve compiled output"
- [E] re-renders the preview without re-running extraction; [S] discards the compiled output and re-runs step 3 with new hints.

