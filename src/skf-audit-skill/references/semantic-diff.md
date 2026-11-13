---
nextStepFile: 'severity-classify.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder: §4 saves the findings step 5 classifies.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
# §4: this skill's renderer of the Semantic Drift tables, from the skill root.
renderDriftTablesScript: 'scripts/render-drift-tables.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Semantic Diff

## STEP GOAL:

Compare what the skill documents about each export (retrieved from its QMD extraction collection, or read from its own files when none is registered or the one registered is empty) against the current source under `{source_root}` to detect meaning-level changes that structural diff cannot catch. This step executes ONLY at Deep tier: at Quick, Forge, and Forge+ tiers, it appends a skip notice and auto-proceeds.

## Rules

- At Quick/Forge/Forge+ tier, skip the entire analysis — append the skip notice only
- Find meaning-level changes in the current source; QMD only retrieves what the skill says. Do not repeat structural findings from Step 03
- Do not classify severity (Step 05)

## MANDATORY SEQUENCE

### 1. Check Forge Tier

**If forge tier is Quick, Forge, or Forge+:**

Append to {outputFile}:

```markdown
## Semantic Drift

**Status:** Skipped — Semantic diff requires Deep tier (current tier: {tier})

Semantic analysis checks what the skill documents (retrieved from its QMD collection) against the current source for meaning-level changes that structural diff cannot detect. To enable semantic diff, run setup with QMD available to unlock Deep tier.
```

Update frontmatter: append `'semantic-diff'` to `stepsCompleted`

"**Semantic diff skipped (requires Deep tier). Proceeding to severity classification...**"

→ Auto-proceed to {nextStepFile}

**If forge tier is Deep:**

Continue to section 2.

### 2. Query Original Knowledge Context

Run items 1 to 4 in the main thread (Pattern 3, data operations): only the main thread can end this step or choose its route, and §3 compares what items 2 and 3 read.
1. Read the `qmd_collections` registry from `{sidecar_path}/forge-tier.yaml`. Find the entry where `skill_name` matches `{skill_name}` AND `type` is `"extraction"`. Three cases must be handled distinctly — collapsing them into "found vs. not found" silently degrades semantic diff when a collection is registered but never indexed.

   - **Registry entry missing.** Whatever tier the skill was compiled at, a Deep-tier audit still checks its claims: log "No QMD extraction collection is registered for `{skill_name}`: semantic diff reads the skill's files instead.", bind `{collection_label}` ← `none (no QMD extraction collection is registered for {skill_name})` and take the **direct-content fallback** below. Never skip the step for it.
   - **Registry entry present but collection empty.** Run a pre-query probe — `qmd ls {collection_name}` (CLI) or the equivalent MCP call. If it reports zero files (`Files: 0 (updated never)` or an empty listing), the collection is registered but has never been indexed. Do **not** proceed to querying — queries will return nothing and the step would silently degrade.
     - Log: "QMD collection `{collection_name}` is registered but empty. Run `qmd update` to (re-)index `{collection.path}`, then re-audit for full Deep-tier semantic coverage."
     - Bind `{collection_label}` ← `{collection_name} (registered but empty)` and fall through to the **direct-content fallback** below instead of skipping outright.
   - **Registry entry present and populated.** Use the `name` field from the registry entry as the collection to query, bind `{collection_label}` ← `{collection_name}`, `{claims_source}` ← `from QMD` and `{confidence}` ← `T2`, and proceed to bullet 2.

   **Direct-content fallback** (used when no extraction collection is registered for the skill, or the one registered is empty): read what the skill documents about each export from `SKILL.md` and `references/*.md` of the audited skill in place of item 2's query, then run items 3 and 4 on those claims, checking the current source under `{source_root}` with the Deep-tier AST tooling this step already requires (ast_bridge; see step 2 §1 "Deep tier"). This fallback is reachable only from Deep tier: §1 short-circuits Quick/Forge/Forge+ before §2 runs, so AST tooling is guaranteed available here. Record findings with confidence label `T1-low-fallback` rather than T2: the claims come from reading the skill's files, not from its QMD collection. Bind `{claims_source}` ← `read from its SKILL.md and references/*.md in direct-content fallback mode` and `{confidence}` ← `T1-low-fallback`: §4's header then says the claims came from the skill's files and, in `{collection_label}`, why. The step's output schema is otherwise unchanged.

2. Query the collection for what the skill documents about each export (usage, conventions, dependencies, architecture): the original side
3. For each claim, read the export's current definition and call sites under `{source_root}` at the file and line `{forge_version}/extraction-snapshot.json` records for it: the current side (an export the snapshot no longer holds is a removed export step 3 already reports: skip it)
4. Keep each claim the source no longer supports, with that file:line, for §3

### 3. Compare Knowledge Context

Each claim of item 2, checked against the current source under `{source_root}` (item 3), that the source no longer supports is one row: in the category §4's mapping names, with the current source file:line (a claim with no source line is not recorded) and `{confidence}` (`T2`, or `T1-low-fallback` in direct-content fallback mode). Only categories with rows are shown.

### 4. Compile Semantic Drift Section

First save the rows to `{auditDataFolder}/semantic-findings.json`, `[]` when there is none: step 5 classifies this file, and the command below renders the tables from it. It is a JSON array with one object per row, `{"type": "semantic", "category", "name", "detail", "file", "line", "confidence"}`, plus `before` and `after` (strings), `exports` (an array of export names) and `skill_reference` (a string) when the row has them. `category` is its table's: Changed Conventions `convention` (a project convention that has shifted, such as a new error handling pattern), Dependency Shifts `dependency` (libraries or modules an export now depends on differently), Architectural Changes `architecture` (a structural reorganization that changes how exports relate to each other) and Deprecated Patterns `deprecated_pattern` (a usage the skill documents that the source no longer follows, such as a changed return value: the category of a claim no other one fits). `name` is what changed (the convention, the export whose dependencies shifted, the change or the pattern), `detail` its description, `before` and `after` what the skill documents and what the source now does (the dependencies, for a dependency shift), `exports` the exports it affects, `skill_reference` where the skill documents a deprecated pattern, `file` and `line` the current source line the row cites, and `confidence` `{confidence}`.

Render the tables from the saved file, never by hand. `{renderDriftTablesScript}` resolves relative to the skill root; from `{project-root}`, run:

```bash
uv run {renderDriftTablesScript} semantic "{auditDataFolder}/semantic-findings.json"
```

It prints a table for each category with rows, then the Summary (`--help` lists their columns). Append to {outputFile}:

```markdown
## Semantic Drift

**Method:** the skill's claims ({claims_source}) checked against the current source (Deep tier)
**QMD Collection:** {collection_label}

{what the command printed, unchanged}
```

When the command exits non-zero, its JSON `error`, else its first stderr line, says what it could not read: write `Semantic tables not rendered: {error}` in place of its output and go on, since step 5 classifies the saved file, not these tables.

### 5. Update Report and Auto-Proceed

Update {outputFile} frontmatter — append `'semantic-diff'` to `stepsCompleted`. Once the ## Semantic Drift section (or skip notice) has been appended, load, read fully, and execute `{nextStepFile}` (severity classification).

