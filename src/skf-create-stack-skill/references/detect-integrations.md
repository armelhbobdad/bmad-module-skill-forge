---
nextStepFile: 'compile-stack.md'
pairIntersectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-pair-intersect.py'
  - '{project-root}/src/shared/scripts/skf-pair-intersect.py'
comentionProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'
  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
renderStackMetadataProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-stack-metadata.py'
  - '{project-root}/src/shared/scripts/skf-render-stack-metadata.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Detect Integrations

## STEP GOAL:

Analyze co-import patterns between confirmed libraries to identify integration points — where and how libraries connect in this specific codebase.

## Rules

- Focus on detecting cross-library patterns using subprocess Pattern 1 (grep/search)
- Do not compile SKILL.md (Step 06)

## MANDATORY SEQUENCE

### 1. Generate Library Pairs

**If `compose_mode` is true:** step 3 counts no imports, so there are no per-library file lists to intersect: the §2 compose branch finds the candidates. Skip to [Detect Co-Import Files](#2-detect-co-import-files).

**If not compose_mode:**

Of the N*(N-1)/2 pairs of `confirmed_dependencies`, only those whose per-library file lists overlap can integrate. This pass finds them for every N, and §2 greps each such pair's intersection files only.

**Compute the intersection deterministically via the shared script:**

1. **Build the libraries JSON** from the per-library file enumeration recorded by step 3 import-count extraction. Skip libraries where step 04 reported extraction failure. Shape:
   ```json
   [
     {"name": "<library-name>", "files": ["<rel-path-forward-slash>", ...]},
     ...
   ]
   ```
2. **Invoke the script** via stdin (or a temp file under `{forge_data_folder}/` if stdin piping is unavailable):

   **Resolve `{pairIntersectHelper}`** from `{pairIntersectProbeOrder}`; first existing path wins. HALT if no candidate exists.

   ```bash
   uv run {pairIntersectHelper} intersect --libraries -
   ```
   piping the libraries JSON on stdin. It emits `pairs[]` (`a`, `b`, `intersection_count`, `files`), sorted by `intersection_count` and capped at the Top-K below, with `truncated` and `total_pairs`.
3. **Use `pairs[]` as the qualifying-pair set** for §2 onward: each pair's `files[]` is its grep scope.

**Top-K cap (S7, 20):** When the script reports `truncated: true`, warn the user: `"non-empty-intersection pair count {total_pairs} exceeds cap: analyzing top 20 by intersection size; {total_pairs - 20} pairs skipped"`, and record the cap in the evidence report.

Report: "**Analyzing {pair_count} library pairs for integration patterns** (pruned from {N*(N-1)/2} via file-list intersection; {capped_count} after Top-K if applicable)**...**"

### 2. Detect Co-Import Files

**If `compose_mode` is true:**

A helper reports candidate pairs with their evidence; a candidate becomes an integration only when that evidence shows how the two libraries work together.

1. Load `{composeModeRulesPath}` for the integration evidence format and labels
2. **If `{architecture_doc_path}` is null or not available:** skip to the **No architecture document** path below
3. **Find the candidates with the shared script**, which applies the co-mention guards `{composeModeRulesPath}` documents (never apply them in-prompt). **Resolve `{comentionHelper}`** from `{comentionProbeOrder}`; first existing path wins.

   ```bash
   uv run {comentionHelper} comention --doc {architecture_doc_path} --skills -
   ```
   piping the `confirmed_dependencies` names as a JSON array on stdin (e.g. `["react", "express"]`; use a temp file under `{forge_data_folder}/` if stdin piping is unavailable). Each pair of its `pairs[]` has `comention_count`, `lead_in_count` and one `evidence[]` entry per body paragraph naming both, of `kind` `co-mention` (one run of prose, list item, table row or code line names both), `lead-in` (prose names one, an item or row under it the other) or `list-only` (separate items only, as a Tech Stack table gives every pair); `unit_excerpt` quotes a co-mention or lead-in, from `unit_line`. A lead-in with a blank line before its list gives no evidence.

   **Graceful degradation:** if no `{comentionProbeOrder}` candidate exists (e.g. `uv` unavailable on claude.ai web), perform the equivalent scan directly per those guards and the script's `--help` contract, then proceed with the same candidates.
4. **Drop the pairs that are only listed together.** A pair whose `comention_count` and `lead_in_count` are both 0 is no integration: drop it and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "info"`, `code: "comention-list-only"`, `message`: the pair and its `paragraph_count`), which the evidence report lists.
5. **Confirm each remaining candidate** from the `unit_excerpt` of its `co-mention` and `lead-in` entries. Keep the pair only when an excerpt says how the two libraries work together: data flows from one to the other, one wraps or adapts the other, one configures or initializes the other, or one handles the other's events. The script reads fenced code as text, so a diagram line counts too: a Mermaid edge between the two (`react --> express`) shows data flow. Two names side by side ("built with React and Express") or an intro line that only names both does not confirm a pair. Drop each pair no excerpt confirms and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "comention-unconfirmed"`, `message`: the pair and the excerpts read).
6. For each confirmed pair, compose an integration section in the evidence format of `{composeModeRulesPath}` from both skills' export lists and API signatures, with the confirming `unit_excerpt` as its architecture reference and the VS verdicts below. Its tier comes from `{renderStackMetadataHelper}` in §3 (see **Confidence Tier Inheritance** in `{composeModeRulesPath}`), and every compose-mode label takes the `[composed]` suffix except an inferred-shared-domain one.

**VS verdicts (architecture-document pairs).** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}` (first existing path wins) and locate the [VS] report through it (see `shared/references/feasibility-report-schema.md`):

```bash
uv run {validateFeasibilityReportHelper} --locate "{forge_data_folder}" --project-name "{project_name}"
```

Act on the first of these that applies:

- **`status: "ok"`:** add each confirmed pair's `pairVerdicts` row (`lib_a` and `lib_b` in either order) and the `overallVerdict` to its evidence, as `{composeModeRulesPath}` shows.
- **`status: "not-found"`, or no JSON** (no candidate resolves, or `uv` cannot run it): compose without VS verdicts. With no JSON, append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "vs-report-unread"`, `message`: the reason).
- **`schemaVersionOk` is false:** never interpret the report. HALT with `"feasibility-report schemaVersion mismatch: expected '1.0', got '{schemaVersion}'; refusing to proceed"`, then emit the result envelope on stderr per the Result Contract in SKILL.md and exit `2`:

  ```
  SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":[],"mode":"compose","exit_code":2,"halt_reason":"schema-version-mismatch"}
  ```
- **`unknownTokens` is not empty:** a verdict token outside the schema's set is a hard error, as the schema requires: HALT, naming each token with its line and pair, and never drop or map one.
- **Any other exit `1`, or exit `2` with a JSON:** the report breaks the contract otherwise (a section missing or out of order, no verdict table or a second one) or could not be read. Read no verdict from it: compose without VS verdicts and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "vs-report-unusable"`, `message`: its `path` and each problem its JSON names, or its `error`).

**No architecture document.** Find the candidates in the constituents themselves, with `{comentionHelper}` resolved as in step 3:

```bash
uv run {comentionHelper} infer --skills - --top-k 20
```

piping one object per confirmed skill on stdin: `{"name": "<skill>", "keywords": ["<keyword>", ...], "language": "<language>", "docs": ["<path>", ...]}`. Its `keywords` are the domain terms its SKILL.md `description` names (such as `orm` or `validation`, never a language), `language` is the one step 2 read from its `metadata.json`, and `docs` are its `SKILL.md` and the `.md` files in its `references/`, under `skill_package_path`. A pair is a candidate only on this evidence, never on a shared language alone, and each candidate is judged like a co-mention:

- **`docs-mention`:** one skill's own docs name the other; `excerpt` quotes the first such line (`doc`, `line`). Keep the pair as a `constituent-documented-contract` integration only when that line says how the two work together, never on a "see also" or "unlike" line.
- **`shared-keywords`:** the two share a domain keyword. Keep the pair as an `inferred-shared-domain` integration only when both skills' descriptions and exports show how that domain makes them work together (one feeds, wraps, configures or consumes the other), never for two libraries that do the same job, such as `zod` and `yup` or `express` and `fastify`.

Drop every other candidate and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-unconfirmed"`, `message`: the pair and the evidence read). When `truncated` is true, record the cap as §1 does (`total_pairs` found, the top 20 analyzed); when `language_only_pair_count` is above 0, append an entry (`step: "step-05"`, `severity: "info"`, `code: "infer-language-only"`) giving that count. On exit `1` its stderr names the input it refused, such as a `docs` path that is missing, unreadable or not UTF-8: fix or drop it and run the call again. On exit `2`, or when no candidate resolves or `uv` cannot run it, compose with no inferred pairs and append an entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-unavailable"`, `message`: the reason).

Skip to section 3 (Classify Integration Types) with the compose-mode pairs.

**If not compose_mode:**

For each library pair (A, B) from §1:

**Launch a subprocess** that greps the pair's §1 intersection files (never the whole source tree) for files importing BOTH library A and library B. Return only file paths and import line numbers.

**Subprocess returns:** `{pair: [A, B], co_import_files: [{path, line_A, line_B}], count: N}`

With no subprocess available, the intersection files are the evidence: count them against the threshold below.

**Threshold:** A pair must have 2+ co-import files to qualify as an integration pattern (single file co-imports may be incidental).

**CCC Semantic Augmentation (Forge+ and Deep with ccc):**

If `tools.ccc` is true in forge-tier.yaml, augment co-import detection with semantic search (max 1 query per library pair), with one exception: when `ccc_index.status` is `"none"` or `"failed"`, setup built no project index and this step builds none, so skip augmentation. Every other status augments: `"fresh"`, `"created"`, `"skipped"` (setup's `--ccc-skip-index` lane still wrote `settings.yml` with the SKF exclusions, so the first refresh search builds the index safely), or a status this SKF does not know, such as a `"stale"` an older SKF recorded.

For each library pair with **0 or 1 co-import files** (below the 2-file threshold — S9, symmetric to give the 0-hit case the same chance as the 1-hit case), run `ccc_bridge.search("{libA} {libB}", source_root, top_k=10)` to find files where the two libraries interact semantically — even without explicit import co-location. If CCC returns additional files where both libraries appear, add them to the pair's co-import candidate list and re-evaluate against the 2-file threshold.

**CCC precision guard for 1-file pairs (H3):** When a CCC hit would elevate a 1-file pair to qualifying status, run a post-hoc verification on that file: re-grep the file and confirm it contains explicit import statements for **both** libraries (per the ecosystem import patterns from `{manifestPatternsPath}`). If either import is missing (e.g., one library is only name-dropped in a comment or string), drop the CCC-added file from the candidate list. Only pairs with ≥2 files that each contain explicit imports for both libraries qualify. Log rejected CCC candidates in workflow state for the evidence report.

**Tool resolution for ccc_bridge.search:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `cd {source_root} && ccc search --limit 10 "{libA} {libB}"` (CLI). `ccc search` reads the index in the current working directory and has no project-selector flag (`--path` is a file-path glob filter *within* the index, and the result cap is `--limit`, not `--top`). See `knowledge/tool-resolution.md`.

**Refresh first:** run this step's first search as `cd {source_root} && ccc search --refresh --limit 10 "{libA} {libB}"`, with an extended timeout, because the refresh pass brings the index up to date before searching; later searches in this step can drop `--refresh`. The ccc MCP search tool refreshes by default: leave its `refresh_index` set to true. If the refresh search fails or times out, run the plain search once, with the same timeout, before treating it as a CCC failure.

For pairs that already qualify (2+ files), CCC is not needed for detection — but the CCC results may surface additional integration files for richer classification in section 3.

CCC failures: skip augmentation silently, proceed with grep-only results.

### 3. Classify Integration Types

Load `{integrationPatternsPath}` for classification rules.

For each qualifying pair, classify the integration type against those pattern types (**in compose mode**: the candidates §2 kept qualify, with no co-import file threshold; **in code mode**: a pair must have 2+ co-import files).

**Pair tiers.** Resolve `{renderStackMetadataHelper}` from `{renderStackMetadataProbeOrder}`; first existing path wins. It holds the one rule for an integration's tier in both modes, so no step works a tier out by hand. If no candidate exists, HALT with "**Cannot proceed.** `skf-render-stack-metadata.py` is missing, so no integration tier can be set. Re-install SKF, then re-run.", then emit the result envelope on stderr per the Result Contract in SKILL.md and exit `3`:

```
SKF_STACK_RESULT_JSON: {"status":"error","skill_package":null,"skill_name":"{project_name}-stack","stack_libraries":["<confirmed-lib>", "..."],"mode":"{code|compose}","exit_code":3,"halt_reason":"resolution-failure"}
```

When at least one pair qualifies, run it once on all of them:

```bash
uv run {renderStackMetadataHelper} pair-tiers --input -
```

piping `{"mode": "code|compose", "libraries": [{"name": "<library>", "confidence": "<its per_library_extractions[].confidence>"}, ...], "integrations": [{"a": "<library>", "b": "<library>"}, ...]}` on stdin, each qualifying pair once. Each entry of its `integrations[]` gives a pair's `tier`. On exit `2` its stderr names the input it refused, such as a pair naming a library the list lacks: fix the input and run it again.

For each detected integration:
- Identify the top 3 files demonstrating the pattern
- Extract a brief description of how the libraries connect
- **Assign confidence (M1/M3): the pair's `tier` and a detection-method qualifier, never AST:** integration detection here is grep plus co-import (optionally CCC-augmented), or a compose-mode candidate §2 confirmed. Append the qualifier that says how the pair was found:
  - `grep-co-import`: the pair qualified via direct co-import grep (the default).
  - `ccc-augmented`: the pair qualified only after CCC semantic search elevated it (per §2 CCC augmentation), and the post-hoc import verification (H3) confirmed both imports.
  - `architecture-co-mention`: compose-mode pair the architecture document names together, confirmed from its excerpt in §2. Maps to `detection_method: architecture_co_mention` in `provenance-map.json`.
  - `constituent-documented-contract`: compose-mode pair with no architecture document whose contract a constituent's own docs state, a docs mention §2 confirmed. Maps to `detection_method: constituent_documented_contract` in `provenance-map.json`.
  - `inferred-shared-domain`: compose-mode pair with no architecture document, a shared-keywords candidate §2 kept (no cited contract, never a shared language alone). Maps to `detection_method: inferred_from_shared_domain` in `provenance-map.json`.
  - Render as `{tier} ({qualifier})`, e.g. `T1-low (grep-co-import)`, `T1 (ccc-augmented)`, `T1-low (architecture-co-mention) [composed]`. The `[composed]`/`[inferred from shared domain]` suffix from `{composeModeRulesPath}` is appended after the qualifier in compose-mode.

  **Provenance ↔ SKILL.md tier parity:** write the pair's `tier` to both the SKILL.md integration label and `provenance-map.json` `integrations[].confidence`. The qualifier, and the `detection_method` it maps to, say how the edge was found and never change the tier.

### 4. Build Integration Graph

Assemble the integration graph:
- **Nodes:** Confirmed libraries (with extraction data from step 04)
- **Edges:** Detected integration pairs with type, file count, and description
- Identify **hub libraries** (connected to 3+ other libraries)
- Identify **cross-cutting patterns** (patterns spanning 3+ libraries)

### 5. Display Integration Summary

If integrations were detected, report the integration graph (`{lib_count}` libraries, `{pair_count}` pairs): the hub libraries (connected to 3+ others) with their partners, each detected pair (library A, library B, type, co-import file count, confidence tier), and any cross-cutting patterns spanning 3+ libraries. If none were detected, report that no co-import integration patterns were found — the libraries appear to operate independently, so the stack skill will carry library summaries without an integration layer.

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

