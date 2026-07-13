---
nextStepFile: 'map-and-detect.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
heuristicsFile: '{unitDetectionHeuristicsPath}'
disqualifyCandidatesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-disqualify-candidates.py'
  - '{project-root}/src/shared/scripts/skf-disqualify-candidates.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Identify Units

## STEP GOAL:

To classify each detected boundary from the project scan into discrete skillable units by applying detection heuristics, assigning boundary types and scope types, and filtering out disqualified candidates.

## Rules

- Focus only on unit classification — do not map exports or integration points yet
- Do not generate skill-brief.yaml in this step
- Every classification must cite the detection signals that justify it

## MANDATORY SEQUENCE

### 1. Load Context

Read {outputFile} to obtain:
- Project Scan results (detected boundaries, manifests, entry points)
- `forge_tier` from frontmatter
- `existing_skills` from frontmatter

Load {heuristicsFile} for classification rules.

### 2. Apply Detection Heuristics

**Resolve `{disqualifyCandidatesHelper}`** from `{disqualifyCandidatesProbeOrder}`; first existing path wins. HALT if no candidate exists.

For each detected boundary from the scan, apply the classification rules from {heuristicsFile} (loaded in §1):

**Step A — Count detection signals:** tally the Strong / Moderate / Weak signals per its Detection Signals tables.

**Step B — Classify boundary type** per its Boundary Classification section. (Composite is detected separately in §3b below — not during this initial per-boundary pass.)

**Step C — Assign scope type** from that same section for the boundary's type.

**Step D — Run deterministic disqualification filter (script):**

Run the shared disqualification helper to apply the deterministic subset of the rules from {heuristicsFile} (file-count, LoC, generated-code paths, auto-generated header sentinels). The script collapses what was prose-orchestrated counting + path-substring + header scanning into one deterministic call.

1. **Build the boundaries JSON** from the detected boundaries (one entry per candidate boundary). Use forward-slash paths throughout. Shape:
   ```json
   [
     {"name": "<unit-name>",
      "path": "<rel-from-analyzed-source-root (project_paths[0])>",
      "files": ["<rel-path>", ...]},
     ...
   ]
   ```
2. **Invoke the script** via stdin:
   ```bash
   uv run {disqualifyCandidatesHelper} filter --boundaries - --source-root {project_paths[0]}
   ```
   piping the boundaries JSON on stdin. `--source-root` is the analyzed-source root (`project_paths[0]`) — the directory the boundaries/manifest scan ran against — not `{project-root}` (the forge workspace), which differs whenever the analyzed target lives outside the forge workspace. The script emits:
   ```json
   {
     "kept":    [{"name": "...", "path": "...", "files_count": N, "loc_total": L}, ...],
     "dropped": [{"name": "...", "reason": "<too-few-files|too-low-loc|generated-code|auto-generated-tag>", "context": {...}}, ...],
     "stats":   {"kept": N, "dropped": N, "by_reason": {"<reason>": N, ...}}
   }
   ```
3. **Parse the JSON result** and stash `kept[]` and `dropped[]` in workflow state for §3 (classification table) and §5 (recommendation summary). The `kept` set is the candidate pool for the boundary-type + scope-type classification that follows; the `dropped` set drives the Disqualification table.

**LLM-judged disqualifications (not in script — apply on top of `kept[]`):**
- **Pure configuration** — only config files (e.g., `.json`/`.yaml`) with no executable logic
- **Test-only** — test utilities with no production code
- **Already skilled** — exists in `existing_skills` list (recommend `update-skill` instead)

Remove any boundary that fails one of these LLM-judged rules from the working `kept` set and append it to `dropped[]` with the appropriate reason. Reasons recorded by the script (`too-few-files`, `too-low-loc`, `generated-code`, `auto-generated-tag`) are authoritative — do not re-evaluate those rules manually.

**Qualification check:** Visually skim the script's `kept`/`dropped` decisions for sanity (e.g., a boundary you expected to qualify that landed in `dropped` — surface the script's `reason` and `context.first_match` to the user in §5 so they can override if the heuristic was wrong for this project).

### 3. Build Unit Classification Table

For each candidate that passes disqualification:

| # | Unit Name | Path | Boundary Type | Scope Type | Signals | Confidence | Status |
|---|-----------|------|---------------|------------|---------|------------|--------|
| 1 | {name} | {path} | {type} | {scope} | {signal count: strong/moderate/weak} | {high/medium/low} | {new/already-skilled} |

For disqualified candidates, note reason:

**Disqualified:**
| Path | Reason |
|------|--------|
| {path} | {disqualification reason} |

### 3b. Detect Composite Unit Merges

After building the classification table, apply the Composite Boundary detection heuristic from {heuristicsFile} against the qualifying units:

1. **Scan for merge candidates:** Among the qualifying units (from `kept[]`), find groups of ≥2 Package or Module boundaries that meet either Composite trigger — **Mutual hard dependency** or **Shared integration surface** — as defined in {heuristicsFile}'s Composite Boundary heuristic.

2. **If candidate groups are found**, propose each merge:
   - Derive a composite name from the common namespace prefix or repo name
   - List the constituents (boundary names and paths being merged)
   - State the triggering heuristic and evidence

3. **If no candidate groups are found**, skip to §4.

**Merge does not fire for:** Units already flagged as Stack Skill Candidates in step 4 (map-and-detect §5) — those are multi-unit groupings that deliver value *separately* but are *also* useful together. Composite merges are for units that are *only* useful together (the key distinction). If a group of units is independently useful but commonly combined, it remains as separate units and is flagged as a stack skill candidate later.

**This step is a recommendation — not automatic.** Merges are presented to the user in §5 for confirmation (see "Composite Merge Proposals" below). If the user rejects a merge, the constituents remain as separate units in the classification table.

### 4. Detect Primary Language Per Unit

For each qualifying unit (including any approved composites from §3b), detect the primary language deterministically via the shared helper — the single source of truth for the manifest→language rule table (no in-prose restatement, which drifts from the script's tsconfig JS-vs-TS and `build.gradle` Java-vs-Kotlin disambiguation).

**Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins.

For each unit, pipe its file list — the `files` array built for that boundary in the §2 boundaries JSON — as the tree:

```bash
echo '{"tree": [<unit files — forward-slash, repo-relative>]}' | uv run {detectLanguageHelper}
```

Read `.language` and `.confidence` for the unit. When confidence is low (the extension-frequency fallback fired — no manifest matched), surface it in §5 so the user can override the guess.

### 5. Present Classifications

"**Unit Identification Complete**

**Qualifying Units:** {count}

{Classification table}

**Disqualified Candidates:** {count}
{Disqualification table}

**Already-Skilled Units:** {count from existing_skills match}
{List with recommendation to run update-skill if source has changed}

{IF composite merge proposals exist from §3b:}

**Composite Merge Proposals:** {count}

| # | Composite Name | Constituents | Heuristic | Evidence |
|---|----------------|--------------|-----------|----------|
| 1 | {name} | {list of constituent unit names} | {mutual hard dependency / shared integration surface} | {brief evidence} |

If approved, each composite replaces its constituents in the classification table as a single Composite Boundary unit. The constituents are recorded in the composite's metadata for downstream workflows (create-skill reads constituents to scope extraction across all member paths).

{END IF}

**Notes:**
- {Any observations about project structure patterns}
- {Any ambiguous boundaries that need user clarification}

Do these classifications look correct? Should any units be added, removed, or reclassified?
{IF composites proposed:} Are the composite merge proposals correct? (Accept/reject each individually.)"

Wait for user feedback. Adjust classifications based on user input. For approved composites: remove the constituent rows from the qualifying units table and add a single composite row with `Boundary Type: Composite`, scope type inherited from the dominant constituent, and confidence reflecting the merge heuristic strength.

### 6. Append to Report

Append the complete "## Identified Units" section to {outputFile}:

Replace the placeholder `[Appended by identify-units]` with:
- Classification table (qualifying units, including approved composites)
- Composite merge details (if any): composite name, constituents list, heuristic, evidence
- Disqualification table
- Already-skilled units list
- Language detection results
- Any user adjustments noted

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'identify-units' to existing array]
lastStep: 'identify-units'
confirmed_composites: [{list of approved composite merge objects: {name, constituents[], heuristic}}]
```

(`confirmed_composites` is an empty array when no composites were proposed or all were rejected.)

### 7. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Export Mapping and Integration Detection | [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: Save classifications to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF X: HARD HALT with exit code 6 (`user-cancelled`). Emit the error envelope on stderr with `halt_reason: "user-cancelled"` and counts/paths reflecting state at cancellation (shape in `references/headless-contract.md`)
- IF Any other: help user, then [Redisplay Menu Options](#7-present-menu-options)

**GATE [default: C]** — present the menu and wait for the user's choice. If `{headless_mode}`: accept all classifications and auto-proceed, log: "headless: auto-accept unit classifications".

