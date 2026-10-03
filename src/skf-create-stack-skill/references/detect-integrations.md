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
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
bundleFile: '{run_dir}/extraction-bundle.json'
importCountsFile: '{run_dir}/import-counts.json'
pairsFile: '{run_dir}/pair-intersect.json'
# A fixed path: the compose rules are not a customization surface.
composeModeRulesPath: 'references/compose-mode-rules.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Detect Integrations

## STEP GOAL:

Analyze co-import patterns between confirmed libraries to identify integration points — where and how libraries connect in this specific codebase.

## Rules

- Focus on detecting cross-library patterns from step 3's import counts and the pair helpers; never grep for imports by hand
- Do not compile SKILL.md (Step 06)

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>", "stack_libraries": ["<confirmed library>", ...]}`, adding `"path"` when the halt names a file, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

Every library's tier (`per_library_extractions[].confidence`) comes from `{bundleFile}`, which step 4 wrote.

### 1. Generate Library Pairs

**If `compose_mode` is true:** step 3 counts no imports, so there are no per-library file lists to intersect: the §2 compose branch finds the candidates. Skip to [Detect Co-Import Files](#2-detect-co-import-files).

**If not compose_mode:**

Of the N*(N-1)/2 pairs of `confirmed_dependencies`, only those whose per-library file lists overlap can integrate. This pass finds them for every N, and their shared files are §2's co-import evidence.

**Compute the intersection deterministically via the shared script.** Resolve `{pairIntersectHelper}` from `{pairIntersectProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `detect-integrations:pair-intersect`) with "**Cannot proceed.** `skf-pair-intersect.py` is missing, so no library pair can be found. Re-install SKF, then re-run."

```bash
uv run {pairIntersectHelper} intersect --counts "{importCountsFile}" --only "<names>" > "{pairsFile}"
```

`{importCountsFile}` is the step 3 import-count JSON, read as it stands, and `--only` names the confirmed libraries, comma-separated, less those step 4 reported an extraction failure for. Its JSON, in `{pairsFile}`, holds `pairs[]` (`a`, `b`, `intersection_count` and `files[]`, each `{path, line_a, line_b}`: a file that imports both libraries, with the first line that imports each), sorted by `intersection_count` and capped at the Top-K below, with `truncated` and `total_pairs`. Use `pairs[]` as the candidate-pair set for §2 onward.

**Top-K cap (S7, 20):** When the script reports `truncated: true`, warn the user and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "pair-cap-truncated"`, `message`: "non-empty-intersection pair count {total_pairs} exceeds cap: analyzing top 20 by intersection size; {total_pairs - 20} pairs skipped"), which the evidence report lists.

Report: "**Analyzing {pair_count} library pairs for integration patterns** (pruned from {N*(N-1)/2} via file-list intersection; {capped_count} after Top-K if applicable)**...**"

### 2. Detect Co-Import Files

**If `compose_mode` is true:**

A helper reports candidate pairs with their evidence; a candidate becomes an integration only when that evidence shows how the two libraries work together. **Resolve `{comentionHelper}`** from `{comentionProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `detect-integrations:comention`) with "**Cannot proceed.** `skf-comention-pairs.py` is missing, so no compose-mode pair can be found. Re-install SKF, then re-run."

1. Load `{composeModeRulesPath}` for the integration evidence format and labels
2. **If `{architecture_doc_path}` is null or not available:** skip to the **No architecture document** path below
3. **Find the candidates with the shared script:**

   ```bash
   uv run {comentionHelper} comention --doc {architecture_doc_path} --skills -
   ```
   piping the `confirmed_dependencies` names as a JSON array on stdin (e.g. `["react", "express"]`; if stdin piping is unavailable, write it to `{run_dir}/skills.json` and pass that path to `--skills`). Its `pairs[]` holds each pair a body paragraph names in one unit or through a lead-in, with `paragraph_count`, `comention_count`, `lead_in_count` and one `evidence[]` entry per paragraph naming both; `unit_excerpt` quotes a `co-mention` or `lead-in` entry, from `unit_line` (a `list-only` entry quotes nothing), and `excluded_section` is true under an introductory heading (Overview, Introduction and the like). `list_only_pair_count` counts the pairs only listed together, which it leaves out. When `pairs[]` is empty, append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "info"`, `code: "comention-no-candidates"`, `message`: "no passage names two confirmed libraries together ({list_only_pair_count} pairs only listed, {excluded_section_count} introductory sections)").

4. **Pairs only listed together.** When `list_only_pair_count` is above 0, append one `workflow_warnings[]` entry (`step: "step-05"`, `severity: "info"`, `code: "comention-list-only"`, `message`: "{list_only_pair_count} pairs only listed together"), which the evidence report lists.
5. **Confirm each candidate** from the `unit_excerpt` of its `co-mention` and `lead-in` entries. Keep the pair only when an excerpt says how the two libraries work together: data flows from one to the other, one wraps or adapts the other, one configures or initializes the other, or one handles the other's events. The script reads fenced code as text, so a diagram line counts too: a Mermaid edge between the two (`react --> express`) shows data flow. Two names side by side ("built with React and Express") do not confirm a pair, and an `excluded_section` entry whose excerpt only names both confirms nothing; one excerpt that says how the two work together is enough, wherever it sits. Drop each pair no excerpt confirms and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "comention-unconfirmed"`, `message`: the pair and the excerpts read).
6. For each confirmed pair, compose an integration section in the evidence format of `{composeModeRulesPath}` from both skills' export lists and API signatures, with the confirming `unit_excerpt` as its architecture reference and the VS verdicts below; §4 keeps them in the pair's bundle entry. Its tier comes from `{renderStackMetadataHelper}` in §3 (see **Confidence Tier Inheritance** in `{composeModeRulesPath}`), and every compose-mode label takes the `[composed]` suffix except an inferred-shared-domain one.

**VS verdicts (architecture-document pairs).** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}` (first existing path wins) and locate the [VS] report through it (see `shared/references/feasibility-report-schema.md`):

```bash
uv run {validateFeasibilityReportHelper} --locate "{forge_data_folder}" --project-name "{project_name}"
```

Act on the first of these that applies:

- **`status: "ok"`:** add each confirmed pair's `pairVerdicts` row (`lib_a` and `lib_b` in either order) and the `overallVerdict` to its evidence, as `{composeModeRulesPath}` shows.
- **`status: "not-found"`, or no JSON** (no candidate resolves, or `uv` cannot run it): compose without VS verdicts. With no JSON, append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "vs-report-unread"`, `message`: the reason).
- **`schemaVersionOk` is false:** never interpret the report. HALT (exit 2, `halt_reason: "schema-version-mismatch"`, phase `detect-integrations:vs-report`, `path` the report's `path`) with "feasibility-report schemaVersion mismatch: expected '1.0', got '{schemaVersion}'; refusing to proceed".
- **`unknownTokens` is not empty:** a verdict token outside the schema's set is a hard error, as the schema requires: HALT (exit 2, `halt_reason: "unknown-verdict-token"`, phase `detect-integrations:vs-report`, `path` the report's `path`), naming each token with its line and pair, and never drop or map one.
- **Any other exit `1`, or exit `2` with a JSON:** the report breaks the contract otherwise (a section missing or out of order, no verdict table or a second one) or could not be read. Read no verdict from it: compose without VS verdicts and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "vs-report-unusable"`, `message`: its `path` and each problem its JSON names, or its `error`).

**No architecture document.** Find the candidates in the constituents themselves, with the `{comentionHelper}` resolved above:

```bash
uv run {comentionHelper} infer --skills - --top-k 20
```

piping one object per confirmed skill on stdin: `{"name": "<skill>", "keywords": ["<keyword>", ...], "language": "<language>", "docs": ["<path>", ...]}`. Its `keywords` are the domain terms its SKILL.md `description` names (such as `orm` or `validation`, never a language), `language` is the one step 2 read from its `metadata.json`, and `docs` are its `SKILL.md` and the `.md` files in its `references/`, under `skill_package_path`. A pair is a candidate only on this evidence, never on a shared language alone, and each candidate is judged like a co-mention:

- **`docs-mention`:** one skill's own docs name the other; `excerpt` quotes the first such line (`doc`, `line`). Keep the pair as a `constituent-documented-contract` integration only when that line says how the two work together, never on a "see also" or "unlike" line.
- **`shared-keywords`:** the two share a domain keyword. Keep the pair as an `inferred-shared-domain` integration only when both skills' descriptions and exports show how that domain makes them work together (one feeds, wraps, configures or consumes the other), never for two libraries that do the same job, such as `zod` and `yup` or `express` and `fastify`.

Drop every other candidate and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-unconfirmed"`, `message`: the pair and the evidence read). When `truncated` is true, append an entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-cap-truncated"`, `message`: its `total_pairs` and the top 20 analyzed); when `language_only_pair_count` is above 0, append an entry (`step: "step-05"`, `severity: "info"`, `code: "infer-language-only"`) giving that count. On exit `1` its stderr names the input it refused, such as a `docs` path that is missing, unreadable or not UTF-8: fix or drop it and run the call again. On exit `2`, or when `uv` cannot run it, compose with no inferred pairs and append an entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-unavailable"`, `message`: the reason).

Skip to section 3 (Classify Integration Types) with the compose-mode pairs.

**If not compose_mode:**

The pair's co-import files stay in `{pairsFile}`: each `files[]` entry of a §1 pair is a file that imports both libraries, as step 3's helper matched them, with `line_a` and `line_b`.

**Threshold:** A pair must have 2+ co-import files (`intersection_count` 2 or more) to qualify as an integration pattern (single file co-imports may be incidental).

**CCC Semantic Augmentation (Forge+ and Deep with ccc):**

If `tools.ccc` is true in forge-tier.yaml, augment each qualifying pair with one semantic search, with one exception: when `ccc_index.status` is `"none"` or `"failed"`, setup built no project index and this step builds none, so skip augmentation. Every other status augments: `"fresh"`, `"created"`, `"skipped"` (setup's `--ccc-skip-index` lane still wrote `settings.yml` with the SKF exclusions, so the first refresh search builds the index safely), or a status this SKF does not know, such as a `"stale"` an older SKF recorded.

For each pair with 2 or more co-import files, run `ccc_bridge.search("{libA} {libB}", project_root, top_k=10)` (`project_root` from step 1, where setup built the index) to rank the files where the two libraries interact. CCC never changes which pairs qualify: a file that imports both libraries is already in the pair's `files[]`, so a pair below the threshold, or one past the Top-K cap, gains nothing from a search.

**CCC precision guard (H3):** keep a CCC-surfaced file only when the pair's `files[]` lists it (both paths are relative to `{project_root}`, so they compare as they stand), and use the files kept to pick the ones §3 cites. Drop every other CCC file (one library only name-dropped in a comment or a string, say), and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "info"`, `code: "ccc-files-dropped"`, `message`: the pair and each file dropped) for the evidence report.

**Tool resolution for ccc_bridge.search:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `cd {project_root} && ccc search --limit 10 "{libA} {libB}"` (CLI). `ccc search` reads the index in the current working directory and has no project-selector flag (`--path` is a file-path glob filter *within* the index, and the result cap is `--limit`, not `--top`). See `knowledge/tool-resolution.md`.

**Refresh first:** run this step's first search as `cd {project_root} && ccc search --refresh --limit 10 "{libA} {libB}"`, with an extended timeout, because the refresh pass brings the index up to date before searching; later searches in this step can drop `--refresh`. The ccc MCP search tool refreshes by default: leave its `refresh_index` set to true. If the refresh search fails or times out, run the plain search once, with the same timeout, before treating it as a CCC failure.

CCC failures: skip augmentation silently; §3 picks its files from the pair's `files[]` alone.

### 3. Classify Integration Types

Load `{integrationPatternsPath}` for classification rules.

For each qualifying pair, classify the integration type against those pattern types (**in compose mode**: the candidates §2 kept qualify, with no co-import file threshold; **in code mode**: a pair must have 2+ co-import files).

**Pair tiers.** Resolve `{renderStackMetadataHelper}` from `{renderStackMetadataProbeOrder}`; first existing path wins. It holds the one rule for an integration's tier in both modes, so no step works a tier out by hand. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `detect-integrations:pair-tiers`) with "**Cannot proceed.** `skf-render-stack-metadata.py` is missing, so no integration tier can be set. Re-install SKF, then re-run."

When at least one pair qualifies, run it once on all of them:

```bash
uv run {renderStackMetadataHelper} pair-tiers --input -
```

piping `{"mode": "code|compose", "libraries": [{"name": "<library>", "confidence": "<its per_library_extractions[].confidence>"}, ...], "integrations": [{"a": "<library>", "b": "<library>"}, ...]}` on stdin, each qualifying pair once. Each entry of its `integrations[]` gives a pair's `tier`. On exit `2` its stderr names the input it refused, such as a pair naming a library the list lacks: fix the input and run it again.

For each detected integration:
- Identify the top 3 files demonstrating the pattern (the CCC files §2 kept first, when there are any)
- Extract a brief description of how the libraries connect
- **Assign confidence (M1/M3): the pair's `tier` and a detection-method qualifier, never AST:** integration detection here is co-import file evidence from step 3's import counts, or a compose-mode candidate §2 confirmed. Append the qualifier that says how the pair was found:
  - `grep-co-import`: the pair qualified on the co-import files its two libraries' import counts share (the default).
  - `architecture-co-mention`: compose-mode pair the architecture document names together, confirmed from its excerpt in §2. Maps to `detection_method: architecture_co_mention` in `provenance-map.json`.
  - `constituent-documented-contract`: compose-mode pair with no architecture document whose contract a constituent's own docs state, a docs mention §2 confirmed. Maps to `detection_method: constituent_documented_contract` in `provenance-map.json`.
  - `inferred-shared-domain`: compose-mode pair with no architecture document, a shared-keywords candidate §2 kept (no cited contract, never a shared language alone). Maps to `detection_method: inferred_from_shared_domain` in `provenance-map.json`.
  - Render as `{tier} ({qualifier})`, e.g. `T1-low (grep-co-import)`, `T1 (grep-co-import)`, `T1-low (architecture-co-mention) [composed]`. The `[composed]`/`[inferred from shared domain]` suffix from `{composeModeRulesPath}` is appended after the qualifier in compose-mode.

  **Provenance ↔ SKILL.md tier parity:** write the pair's `tier` to both the SKILL.md integration label and `provenance-map.json` `integrations[].confidence`. The qualifier, and the `detection_method` it maps to, say how the edge was found and never change the tier.

### 4. Build Integration Graph

Assemble the integration graph:
- **Nodes:** Confirmed libraries (with extraction data from step 04)
- **Edges:** Detected integration pairs with type, co-import file count (the pair's `intersection_count` in `{pairsFile}`, 0 in compose mode), and description
- Identify **hub libraries** (connected to 3+ other libraries)
- Identify **cross-cutting patterns** (patterns spanning 3+ libraries)

Write the graph into `{bundleFile}`: its `integrations[]` gets one entry per detected pair, `{"a": "<library>", "b": "<library>", "type": "<pattern type>", "tier": "<the pair's tier>", "qualifier": "<detection qualifier>", "detection_method": "<provenance detection_method>", "key_files": ["<path:line>"], "description": "<how they connect>"}`, and `hubs` and `cross_cutting` list the hub libraries and cross-cutting patterns, so steps 6 and 7 read the integration layer from disk. In compose mode each entry also holds its evidence in the format of `{composeModeRulesPath}`: `"evidence": ["[from skill: <A>] <signature>", "[from skill: <B>] <signature>"]`, `"reference": "<its Architecture reference, Contract reference or Shared domain line>"` and `"vs": {"pair": "<verdict>", "overall": "<overallVerdict>"}`, `null` when no usable [VS] report rated the pair; code mode leaves the three out.

### 5. Display Integration Summary

If integrations were detected, report the integration graph (`{lib_count}` libraries, `{pair_count}` pairs): the hub libraries (connected to 3+ others) with their partners, each detected pair (library A, library B, type, co-import file count, confidence tier), and any cross-cutting patterns spanning 3+ libraries. If none were detected, report that the libraries appear to operate independently: the stack skill carries library summaries without an integration layer.

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

