---
nextStepFile: 'compile-stack.md'
integrationPatterns: 'references/integration-patterns.md'
composeModeRules: 'references/compose-mode-rules.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Detect Integrations

## STEP GOAL:

Analyze co-import patterns between confirmed libraries to identify integration points — where and how libraries connect in this specific codebase.

## Rules

- Focus on detecting cross-library patterns using subprocess Pattern 1 (grep/search)
- Do not compile SKILL.md (Step 06)
- Integration detection is the core differentiator of stack skills vs individual skills

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Generate Library Pairs

From `confirmed_dependencies`, generate all unique pairs:
- N libraries → N*(N-1)/2 pairs
- Skip pairs where either library had extraction failure in step 04

**File-list intersection fast path (MANDATORY first pass, all N):** before issuing any pair grep, compute each pair's candidate file set by **intersecting the per-library file lists recorded by step 3 import-count extraction**. Pairs with an empty intersection cannot be integration candidates by construction — drop them. Subsequent grep passes run only against pairs with a non-empty intersection, and grep scope is restricted to those intersection files rather than the whole source tree. This is NOT a "subprocess-unavailable" fallback; it is the default strategy for every N. Rationale: at N≈21 this collapses 210 prescribed pair greps to ~12 non-empty-intersection pairs in typical codebases; at larger N the compression is even greater.

**Top-K cap (S7, lowered to 20):** If the file-list-intersection prune still leaves more than **20** non-empty-intersection pairs, cap at the top 20 pairs ranked by intersection size (or by import count if tied). Dropped pairs are excluded from integration detection — warn the user explicitly: `"non-empty-intersection pair count {N} exceeds cap — analyzing top 20 by intersection size; {excluded_count} pairs skipped"`. Record this cap in the evidence report. The legacy 50-dependency threshold that formerly gated a separate Top-K pass is retired — the file-intersection prune does the bulk of the work and the cap is now a second-order safety limit, not a primary strategy.

Report: "**Analyzing {pair_count} library pairs for integration patterns** (pruned from {N*(N-1)/2} via file-list intersection; {capped_count} after Top-K if applicable)**...**"

### 2. Detect Co-Import Files

**If `compose_mode` is true:**

Instead of co-import grep, detect integrations from architecture document:

1. Load `{composeModeRules}` for integration evidence format rules
2. **If `{architecture_doc_path}` is null or not available:** Skip directly to the "If no architecture document available" fallback below
3. Load the architecture document from `{architecture_doc_path}`
4. **Prose-based co-mention analysis with precision guards (H2):**
   - Use **word-boundary matching** when searching for skill names in the architecture document: `\b{skill_name}\b` (case-insensitive). This prevents substring false positives (e.g., `react` matching inside `reactive`).
   - **Exclude non-body sections.** Detect H1 and H2 markdown headers (`^# ` and `^## `) and skip any paragraphs under headers that normalise to `introduction`, `overview`, `glossary`, `table of contents`, `references`, `appendix`, or `index`. Co-mentions inside headings themselves also do not qualify.
   - **Require ≥2 qualifying paragraphs.** A pair `(A, B)` qualifies only when at least two distinct body paragraphs each contain word-boundary matches for both `A` and `B`. A single co-mention paragraph is insufficient evidence.
   - Risks and rationale are documented in `{composeModeRules}` under "Compose-mode co-mention precision".
5. For each detected integration pair:
   - Load both skills' export lists and API signatures
   - Compose an integration section following the format from `{composeModeRules}`
   - Include VS feasibility verdict if a feasibility report matching the filename pattern defined in `src/shared/references/feasibility-report-schema.md` exists under `{forge_data_folder}/` (timestamped `feasibility-report-{project_slug}-{YYYYMMDD-HHmmss}.md` or the stable `feasibility-report-{project_slug}-latest.md` copy). Schema version `"1.0"` is required; see the schema for the full contract.
   - Cite evidence from both skills: `[from skill: {skill_name}]`

All integration evidence inherits confidence tiers from the source skills. Load and apply the full **Confidence Tier Inheritance** matrix from `{composeModeRules}` to compute the correct tier for each pair (covers T1+T1, T1+T1-low, T1-low+T1-low, T1+T2, T1-low+T2, T2+T2 cases). Apply the `[composed]` suffix to all confidence labels — e.g., `T1 [composed]`, `T1-low [composed, +T2 annotations]`.

**VS verdict parsing (if feasibility report exists):** The feasibility report format is defined by the shared schema at `src/shared/references/feasibility-report-schema.md` (single source of truth; skf-verify-stack is the producer, this skill is the consumer). Follow the schema strictly:

- Locate the report via the filename pattern in the schema: `{forge_data_folder}/feasibility-report-{project_slug}-{YYYYMMDD-HHmmss}.md` (or the stable `feasibility-report-{project_slug}-latest.md` copy next to it).
- **Schema version guard:** Parse the report's YAML frontmatter and verify `schemaVersion == "1.0"`. If the field is missing or mismatched, HALT with an explicit error: `"feasibility-report schemaVersion mismatch: expected '1.0', got '{value}' — refusing to proceed"`. Do NOT attempt to interpret unknown versions.
- Read `overallVerdict` from frontmatter (exactly one of `FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE`).
- Parse the `## Integration Verdicts` markdown table for per-pair verdicts (exactly one of `Verified|Plausible|Risky|Blocked`). Any unknown verdict token is a hard error per the schema — do not silently drop or map.
- For each architecture-detected pair, include `VS overall: {overallVerdict}` and `VS pair: {verdict}` in the integration evidence per the format in `{composeModeRules}`. VS verdicts do not apply to inferred integrations since the VS report operates on architecture-described interactions only. Additionally, flag any pairs where VS reported `Risky` or `Blocked` by appending a `[VS: Risky]` or `[VS: Blocked]` warning annotation to the integration entry.

If no architecture document available:
- Infer potential integrations from skills sharing the same `language` field or sharing domain keywords in their SKILL.md descriptions (use the `usage_patterns` and `exports` fields from `per_library_extractions[]` built in step 4, or reload SKILL.md from the version-aware path: use `skill_package_path` from step 2, or resolve via `{skills_output_folder}/{skill_dir}/active/{skill_dir}/SKILL.md` — see `knowledge/version-paths.md`)
- Mark inferred integrations: `[inferred from shared domain]` — use this suffix instead of `[composed]` for inferred integrations
- Inferred integrations qualify automatically — no file-count threshold applies

Skip to section 3 (Classify Integration Types) with the compose-mode pairs.

**If not compose_mode:**

For each library pair (A, B):

**Launch a subprocess** that greps across all source files to find files importing BOTH library A and library B. Return only file paths and import line numbers.

**Subprocess resolution:** Use the Grep tool (Claude Code), built-in search (Cursor), or `grep`/`rg` (CLI). See `knowledge/tool-resolution.md`.

**Subprocess returns:** `{pair: [A, B], co_import_files: [{path, line_A, line_B}], count: N}`

**Note on file-list intersection:** per §1, the intersection has already been computed and the pair's `intersection_files` set is known. The grep below runs against that set only, not the whole source tree. If a subprocess is entirely unavailable, the intersection itself is the integration evidence — count the intersection files against the 2-file threshold below without the grep. The intersection is mandatory first-pass work, not a fallback.

**Threshold:** A pair must have 2+ co-import files to qualify as an integration pattern (single file co-imports may be incidental).

**CCC Semantic Augmentation (Forge+ and Deep with ccc):**

If `tools.ccc` is true AND `ccc_index.status` is `"fresh"` or `"stale"` in forge-tier.yaml, augment co-import detection with semantic search (max 1 query per library pair):

For each library pair with **0 or 1 co-import files** (below the 2-file threshold — S9, symmetric to give the 0-hit case the same chance as the 1-hit case), run `ccc_bridge.search("{libA} {libB}", source_root, top_k=10)` to find files where the two libraries interact semantically — even without explicit import co-location. If CCC returns additional files where both libraries appear, add them to the pair's co-import candidate list and re-evaluate against the 2-file threshold.

**CCC precision guard for 1-file pairs (H3):** When a CCC hit would elevate a 1-file pair to qualifying status, run a post-hoc verification on that file: re-grep the file and confirm it contains explicit import statements for **both** libraries (per the ecosystem import patterns from `references/manifest-patterns.md`). If either import is missing (e.g., one library is only name-dropped in a comment or string), drop the CCC-added file from the candidate list. Only pairs with ≥2 files that each contain explicit imports for both libraries qualify. Log rejected CCC candidates in workflow state for the evidence report.

**Tool resolution for ccc_bridge.search:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `ccc search "{libA} {libB}" --path {source_root} --top 10` (CLI). See `knowledge/tool-resolution.md`.

For pairs that already qualify (2+ files), CCC is not needed for detection — but the CCC results may surface additional integration files for richer classification in section 3.

CCC failures: skip augmentation silently, proceed with grep-only results.

### 3. Classify Integration Types

Load `{integrationPatterns}` for classification rules.

For each qualifying pair, analyze to classify the integration type (**in compose-mode**: all architecture-document-detected pairs qualify automatically — the 2+ co-import file threshold applies only in code-mode; **in code-mode**: pair must have 2+ co-import files):

- **Type 1: Middleware Chain** — Sequential function calls piping output between libraries
- **Type 2: Shared Types** — Type definitions exchanged between libraries
- **Type 3: Configuration Bridge** — One library configuring or initializing another
- **Type 4: Event Handler** — Event patterns crossing library boundaries
- **Type 5: Adapter/Wrapper** — Thin wrapper connecting library interfaces
- **Type 6: State Sharing** — Shared state stores or context providers

For each detected integration:
- Identify the top 3 files demonstrating the pattern
- Extract a brief description of how the libraries connect
- **Assign confidence (M1/M3) — derive from per-library tiers + detection-method qualifier (NOT from AST):** integration detection here is grep + co-import (optionally CCC-augmented), never AST. The integration's confidence is the **weaker** of the two libraries' tiers from `per_library_extractions[]` (tie-break: T1-low > T1, T2 > T1-low, T3 > T2 — never overstate). Then append a detection-method qualifier:
  - `grep-co-import` — the pair qualified via direct co-import grep (the default).
  - `ccc-augmented` — the pair qualified only after CCC semantic search elevated it (per §2 CCC augmentation), and the post-hoc import verification (H3) confirmed both imports.
  - `architecture-co-mention` — compose-mode pair qualified via word-boundary co-mention in the architecture document (per §2 H2 guards).
  - `inferred-shared-domain` — compose-mode pair without an architecture document, inferred from shared `language` or domain keywords.
  - Render as `{tier} ({qualifier})` — e.g., `T1-low (grep-co-import)`, `T1 (ccc-augmented)`, `T1-low (architecture-co-mention) [composed]`. The `[composed]`/`[inferred from shared domain]` suffix from `compose-mode-rules.md` is appended after the qualifier in compose-mode.

### 4. Build Integration Graph

Assemble the integration graph:
- **Nodes:** Confirmed libraries (with extraction data from step 04)
- **Edges:** Detected integration pairs with type, file count, and description
- Identify **hub libraries** (connected to 3+ other libraries)
- Identify **cross-cutting patterns** (patterns spanning 3+ libraries)

### 5. Display Integration Summary

**If integrations detected:**

"**Integration detection complete.**

**Integration graph:** {lib_count} libraries, {pair_count} integration pairs

**Hub libraries** (connected to 3+ others):
{For each hub:} - **{library}** — integrates with {partner_list}

**Detected integrations:**
| Library A | Library B | Type | Co-import Files | Confidence |
|-----------|-----------|------|-----------------|------------|
| {name} | {name} | {type} | {count} | {tier} |

{If cross-cutting patterns:}
**Cross-cutting patterns:**
- {description spanning 3+ libraries}

**Proceeding to stack compilation...**"

**If no integrations detected:**

"**No co-import integration patterns detected** between confirmed libraries.

The libraries in this project appear to operate independently. The stack skill will contain library summaries without an integration layer.

**Proceeding to stack compilation...**"

### 6. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

