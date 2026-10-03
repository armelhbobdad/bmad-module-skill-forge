---
nextStepFile: 'generate-output.md'
renderStackMetadataProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-stack-metadata.py'
  - '{project-root}/src/shared/scripts/skf-render-stack-metadata.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
bundleFile: '{run_dir}/extraction-bundle.json'
exportRecordsFile: '{run_dir}/export-records.json'
draftFolder: '{run_dir}/draft'
# A fixed path: the compose rules are not a customization surface.
composeModeRulesPath: 'references/compose-mode-rules.md'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 6: Compile Stack Skill

## STEP GOAL:

Assemble the main SKILL.md by combining per-library extractions with the integration layer, write it as the run's draft, and get it approved before step 7 writes the package.

## Rules

- Compile SKILL.md following the stack-skill-template structure — integration patterns go first
- Write only the draft in `{draftFolder}`: every file of the package is step 7's, staged from the approved draft
- Present the stats and the draft's path for review; display the full draft only when the user asks, never in a headless run

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>", "stack_libraries": ["<confirmed library>", ...]}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

### 1. Load Template Structure

Load `{stackSkillTemplatePath}` and prepare SKILL.md section structure. Every section below compiles from `{bundleFile}`: step 4's per-library extractions and step 5's integration graph (`integrations[]`, `hubs`, `cross_cutting`), never from memory. A library's key exports are its records in `{exportRecordsFile}` in code mode (each with its `source_library`), and its bundle entry's `exports` in compose mode.

**The stack's counts.** Take them from the helper step 7 §6 also runs, never by hand. Resolve `{renderStackMetadataHelper}` from `{renderStackMetadataProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `compile-stack:stats`) with "**Cannot proceed.** `skf-render-stack-metadata.py` is missing, so the stack cannot be counted. Re-install SKF, then re-run." Otherwise run:

```bash
uv run {renderStackMetadataHelper} metadata --input -
```

piping `{"mode": "code|compose", "libraries": [{"name": "<library>", "confidence": "<its per_library_extractions[].confidence>"}, ...], "integrations": [{"a": "<library>", "b": "<library>"}, ...]}`, every library and every pair of `{bundleFile}`. On exit `2`, fix the input its stderr names and run it again. Bind `{lib_count}` ← its `library_count` and `{integration_count}` ← its `integration_count`, which §2's description and §7's stats name, and keep its `confidence_distribution` for §7.

### 2. Generate Frontmatter

Use the template's frontmatter with the counts §1 bound; its Sizing Guidance caps the description.

### 3. Compile Integration Layer

Compile in order:

**Zero-integration guard:** If the integration graph from step 05 has zero edges (no detected integration pairs), skip the integration layer compilation and note: "No integration patterns detected — stack skill will contain library summaries without an integration layer." Proceed directly to section 4 (Per-Library Sections).

**Cross-cutting patterns** (if any):
- Patterns spanning 3+ libraries
- Middleware chains, shared configuration, common architectural patterns

**Library pair integrations:**
- For each detected integration pair from step 05:
  - Type classification
  - Pattern description with file:line citations
  - Key files demonstrating the integration
  - Confidence tier label
- **In compose mode**, render each pair in the evidence format of `{composeModeRulesPath}` instead, from its entry's `evidence`, `reference`, `tier` and `qualifier`, adding the VS lines and annotation that file's Feasibility Report Integration gives when the entry's `vs` is set; a compose pair has no key files.

**Hub library connections:**
- For each hub library (3+ connections):
  - Role in the stack architecture
  - How it connects to partner libraries

### 4. Compile Per-Library Sections

**Catalog placement (decide once, applies to this section and §6).** By the template's Sizing Guidance, a large stack authors the `Per-Library Summaries` and `Library Reference Index` into `references/stack-catalog.md`, whose per-library links read `[ref]({name}.md)`, and leaves the inline pointer in SKILL.md; a small stack keeps both inline, its links reading `[ref](references/{name}.md)`. A link resolves from the file that holds it.

Order the libraries by integration connectivity, then import count (**in compose-mode**, connectivity then skill confidence tier, since import counts are not available).

### 5. Compile Project Conventions

The conventions the extractions show recurring across libraries.

### 6. Compile Library Reference Index

Per the template and §4's placement (**in compose-mode**: replace the Imports column with Export Count from source skill metadata, since import counts are not available).

The Reference column follows the §4 link rule: `[ref](references/{name}.md)` when the index stays in SKILL.md, `[ref]({name}.md)` when it goes to `references/stack-catalog.md`.

### 7. Write the Draft and Its Stats

Write the compiled SKILL.md to `{draftFolder}/SKILL.md`, and, when §4 moved the catalog out, the catalog to `{draftFolder}/stack-catalog.md`. The draft is what the review approves: step 7 stages it verbatim.

Then display, with the counts and the distribution of the §1 helper run:

"**Stack skill compilation complete. Please review the draft:** `{draftFolder}/SKILL.md`{IF catalog:} and `{draftFolder}/stack-catalog.md`{END IF}

**Compilation stats:**
- **Libraries:** {lib_count}
- **Integration pairs:** {integration_count}
- **Cross-cutting patterns:** {each entry of the bundle's `cross_cutting`, or none}
- **Confidence (libraries per tier, `per_library_extractions[].confidence`):** T1: {its `confidence_distribution.t1`}, T1-low: {`t1_low`}, T2: {`t2`}, T3: {`t3`}

**Please review the integration layer and per-library sections.**
- Does the integration layer capture how your libraries connect?
- Are the per-library summaries accurate?
- Any sections to adjust before writing output? Edit the draft yourself, or tell me what to change."

### 8. Present MENU OPTIONS

Display: **Select:** [C] Continue to Output Generation | [P] Preview the full draft | [X] Cancel and exit

#### EXECUTION RULES:

- This is a review gate: advancing without the user's `C` would write output files from a compilation they never reviewed. Halt and wait for input after presenting the stats.
- **GATE [default: C]**: If `{headless_mode}`: auto-proceed with [C] Continue, displaying no draft, and record the auto-decision: stage `{"gate": "compile-stack.review", "default_action": "C", "taken_action": "C", "reason": "headless: approved the compiled draft"}` as `{run_dir}/decision.json` and run:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-create-stack-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
  ```

- Proceed to the next step only once the user approves by selecting `C`.

#### Menu Handling Logic:

- IF C: The draft files as they stand on disk, the user's own edits included, are the approved compilation. Load, read entire file, then execute {nextStepFile}
- IF P: Display the full draft files, then [Redisplay Menu Options](#8-present-menu-options)
- IF X: HALT (exit 6, `halt_reason: "user-cancelled"`, phase `compile-stack:review`): leave any existing committed stack package untouched, emit the envelope, then delete the run folder (`rm -rf "{run_dir}"`), the draft and the bundle with it
- IF Any other: Process it as feedback: apply it to the draft files in `{draftFolder}`. When it drops a library or a pair, drop it from `{bundleFile}` too (a library with its pairs, and its records from `{exportRecordsFile}`), so step 7 writes no file the draft no longer covers; then run the §1 helper call again, rebinding the counts, and rewrite the draft's `description` with them. Show the stats again, then [Redisplay Menu Options](#8-present-menu-options)
