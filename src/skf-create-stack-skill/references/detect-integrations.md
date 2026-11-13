---
nextStepFile: 'compile-stack.md'
pairIntersectProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-pair-intersect.py'
  - '{project-root}/src/shared/scripts/skf-pair-intersect.py'
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

Find the library pairs whose co-imports show where and how they connect in this codebase, classify every pair, compose mode's included, and build the integration graph.

## Rules

- Focus on detecting cross-library patterns from step 3's import counts and the pair helpers; never grep for imports by hand
- Do not compile SKILL.md (Step 06)

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>", "stack_libraries": ["<confirmed library>", ...]}`, adding `"path"` when the halt names a file, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

Every library's tier (`per_library_extractions[].confidence`) comes from `{bundleFile}`, which step 4 wrote.

### 1. Generate Library Pairs

**If `compose_mode` is true:** `references/compose-pairs.md` found the pairs and wrote them to `{bundleFile}`'s `integrations[]`. Skip to [Classify Integration Types](#3-classify-integration-types).

Of the N*(N-1)/2 pairs of `confirmed_dependencies`, only those whose per-library file lists overlap can integrate. This pass finds them for every N, and their shared files are §2's co-import evidence.

**Compute the intersection deterministically via the shared script.** Resolve `{pairIntersectHelper}` from `{pairIntersectProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `detect-integrations:pair-intersect`) with "**Cannot proceed.** `skf-pair-intersect.py` is missing, so no library pair can be found. Re-install SKF, then re-run."

```bash
uv run {pairIntersectHelper} intersect --counts "{importCountsFile}" --only "<names>" > "{pairsFile}"
```

`{importCountsFile}` is the step 3 import-count JSON, read as it stands, and `--only` names the confirmed libraries, comma-separated, less those step 4 reported an extraction failure for. Its JSON, in `{pairsFile}`, holds `pairs[]` (`a`, `b`, `intersection_count` and `files[]`, each `{path, line_a, line_b}`: a file that imports both libraries, with the first line that imports each), sorted by `intersection_count` and capped at the Top-K below, with `truncated` and `total_pairs`. Use `pairs[]` as the candidate-pair set for §2 onward.

**Top-K cap:** When the script reports `truncated: true`, warn the user and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "pair-cap-truncated"`, `message`: "non-empty-intersection pair count {total_pairs} exceeds cap: analyzing top 20 by intersection size; {total_pairs - 20} pairs skipped"), which the evidence report lists.

Report: "**Analyzing {pair_count} library pairs for integration patterns** (pruned from {N*(N-1)/2} via file-list intersection; {capped_count} after Top-K if applicable)**...**"

### 2. Detect Co-Import Files

The pair's co-import files stay in `{pairsFile}`: each `files[]` entry of a §1 pair is a file that imports both libraries, as step 3's helper matched them, with `line_a` and `line_b`.

**Threshold:** A pair must have 2+ co-import files (`intersection_count` 2 or more) to qualify as an integration pattern (single file co-imports may be incidental).

**CCC Semantic Augmentation (Forge+ and Deep with ccc):**

If `tools.ccc` is true in forge-tier.yaml, augment each qualifying pair with one semantic search, with one exception: when `ccc_index.status` is `"none"` or `"failed"`, setup built no project index and this step builds none, so skip augmentation. Every other status augments: `"fresh"`, `"created"`, `"skipped"` (setup's `--ccc-skip-index` lane still wrote `settings.yml` with the SKF exclusions, so the first refresh search builds the index safely), or a status this SKF does not know, such as a `"stale"` an older SKF recorded.

For each pair with 2 or more co-import files, run `ccc_bridge.search("{libA} {libB}", project_root, top_k=10)` (`project_root` from step 1, where setup built the index) to rank the files where the two libraries interact. CCC never changes which pairs qualify: a file that imports both libraries is already in the pair's `files[]`, so a pair below the threshold, or one past the Top-K cap, gains nothing from a search.

**CCC precision guard:** keep a CCC-surfaced file only when the pair's `files[]` lists it (both paths are relative to `{project_root}`, so they compare as they stand), and use the files kept to pick the ones §3 cites. Drop every other CCC file (one library only name-dropped in a comment or a string, say), and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "info"`, `code: "ccc-files-dropped"`, `message`: the pair and each file dropped) for the evidence report.

**Tool resolution for ccc_bridge.search:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `cd {project_root} && ccc search --limit 10 "{libA} {libB}"` (CLI). `ccc search` reads the index in the current working directory and has no project-selector flag (`--path` is a file-path glob filter *within* the index, and the result cap is `--limit`, not `--top`). See `knowledge/tool-resolution.md`.

**Refresh first:** run this step's first search as `cd {project_root} && ccc search --refresh --limit 10 "{libA} {libB}"`, with an extended timeout, because the refresh pass brings the index up to date before searching; later searches in this step can drop `--refresh`. The ccc MCP search tool refreshes by default: leave its `refresh_index` set to true. If the refresh search fails or times out, run the plain search once, with the same timeout, before treating it as a CCC failure.

CCC failures: skip augmentation silently; §3 picks its files from the pair's `files[]` alone.

### 3. Classify Integration Types

Load `{integrationPatternsPath}` for classification rules.

For each qualifying pair, classify the integration type against those pattern types (**in compose mode**: the pairs `references/compose-pairs.md` wrote qualify, with no co-import file threshold; **in code mode**: a pair must have 2+ co-import files).

**Pair tiers.** Resolve `{renderStackMetadataHelper}` from `{renderStackMetadataProbeOrder}`; first existing path wins. It holds the one rule for an integration's tier in both modes, so no step works a tier out by hand. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `detect-integrations:pair-tiers`) with "**Cannot proceed.** `skf-render-stack-metadata.py` is missing, so no integration tier can be set. Re-install SKF, then re-run."

When at least one pair qualifies, run it once on all of them:

```bash
uv run {renderStackMetadataHelper} pair-tiers --bundle "{bundleFile}" [--pairs -]
```

In code mode pass `--pairs -` and pipe the qualifying pairs as `[{"a": "<library>", "b": "<library>"}, ...]`, each once; in compose mode leave it out: the helper reads the pairs `references/compose-pairs.md` wrote. Each entry of its `integrations[]` gives a pair's `tier`. On exit `2` its stderr names the input it refused, such as a pair naming a library the bundle lacks: fix the input and run it again.

For each detected integration:
- Identify the top 3 files demonstrating the pattern (the CCC files §2 kept first, when there are any); a compose-mode pair has none, so its `key_files` is `[]`
- Extract a brief description of how the libraries connect
- **Assign confidence: the pair's `tier` and a detection-method qualifier, never AST:** integration detection here is co-import file evidence from step 3's import counts, or a compose-mode pair `references/compose-pairs.md` confirmed. Append the qualifier that says how the pair was found:
  - `grep-co-import`: the pair qualified on the co-import files its two libraries' import counts share (every code-mode pair).
  - A compose-mode pair keeps the `qualifier` `references/compose-pairs.md` wrote.
  - Render as `{tier} ({qualifier})`, e.g. `T1-low (grep-co-import)`, `T1 (grep-co-import)`, `T1-low (architecture-co-mention) [composed]`. The `[composed]`/`[inferred from shared domain]` suffix from `{composeModeRulesPath}` is appended after the qualifier in compose-mode.

  **Provenance ↔ SKILL.md tier parity:** write the pair's `tier` to both the SKILL.md integration label and `provenance-map.json` `integrations[].confidence`. The qualifier, from which step 7 derives the `detection_method`, says how the edge was found and never changes the tier.

### 4. Build Integration Graph

Assemble the integration graph:
- **Nodes:** Confirmed libraries (with extraction data from step 04)
- **Edges:** Detected integration pairs with type, co-import file count (the pair's `intersection_count` in `{pairsFile}`, 0 in compose mode), and description
- Identify **cross-cutting patterns** (patterns spanning 3+ libraries)

Write the graph into `{bundleFile}`: its `integrations[]` gets one entry per detected pair, `{"a": "<library>", "b": "<library>", "type": "<pattern type>", "tier": "<the pair's tier>", "qualifier": "<detection qualifier>", "key_files": ["<path:line>"], "description": "<how they connect>"}`, and `cross_cutting` lists the cross-cutting patterns, so steps 6 and 7 read the integration layer from disk. In compose mode each entry keeps the `evidence`, `reference` and `vs` `references/compose-pairs.md` wrote; code mode leaves the three out.

Then read the hubs off the written graph with the §3 helper:

```bash
uv run {renderStackMetadataHelper} metadata --bundle "{bundleFile}"
```

Its `hubs` lists each hub library and its partners; on exit `2`, fix the bundle field its stderr names and run it again.

### 5. Display Integration Summary

If integrations were detected, report the integration graph (`{lib_count}` libraries, `{pair_count}` pairs): each hub library of §4's `hubs` with its partners, each detected pair (library A, library B, type, co-import file count, confidence tier), and any cross-cutting patterns spanning 3+ libraries. If none were detected, report that the libraries appear to operate independently: the stack skill carries library summaries without an integration layer.

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

