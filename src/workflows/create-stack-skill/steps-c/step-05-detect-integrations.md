---
name: 'step-05-detect-integrations'
description: 'Detect co-import patterns and integration points between confirmed libraries'

nextStepFile: './step-06-compile-stack.md'
integrationPatterns: '../data/integration-patterns.md'
composeModeRules: '../data/compose-mode-rules.md'
---

# Step 5: Detect Integrations

## STEP GOAL:

Analyze co-import patterns between confirmed libraries to identify integration points — where and how libraries connect in this specific codebase.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are an integration architect operating in Ferris Architect mode
- ✅ Zero hallucination — only document integrations evidenced in actual code
- ✅ Every integration pattern must cite co-import files with file:line references

### Step-Specific Rules:

- 🎯 Focus on detecting cross-library patterns using Pattern 1 (grep/search): In Claude Code, use the Grep tool or Bash with `rg`. In Cursor, use built-in search. In CLI, use `grep`/`rg` directly. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
- 🚫 FORBIDDEN to compile SKILL.md — that is step 06
- 💬 Integration detection is the core differentiator of stack skills vs individual skills
- ⚙️ If subprocess unavailable, perform grep operations in main thread

## EXECUTION PROTOCOLS:

- 🎯 Load integration-patterns.md for detection rules
- 💾 Store integration_graph as workflow state
- 📖 Auto-proceed to step 06 after detection complete
- 🚫 Graceful handling if no integrations detected

## CONTEXT BOUNDARIES:

- From step 03: confirmed_dependencies[] — in code-mode, includes file lists per library; in compose-mode, file lists are not present (use per_library_extractions[] from step 04 for skill content)
- From step 04: per_library_extractions[] with exports and patterns
- This step produces: integration_graph {pairs[], types[], files[]}
- This is the VALUE-ADD step — what makes stack skills different from individual skills

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Generate Library Pairs

From `confirmed_dependencies`, generate all unique pairs:
- N libraries → N*(N-1)/2 pairs
- Skip pairs where either library had extraction failure in step 04

Report: "**Analyzing {pair_count} library pairs for integration patterns...**"

### 2. Detect Co-Import Files

**If `compose_mode` is true:**

Instead of co-import grep, detect integrations from architecture document:

1. Load `{composeModeRules}` for integration evidence format rules
2. **If `{architecture_doc_path}` is null or not available:** Skip directly to the "If no architecture document available" fallback below
3. Load the architecture document from `{architecture_doc_path}`
4. Use prose-based co-mention analysis: find paragraphs mentioning 2+ confirmed skill names
5. For each detected integration pair:
   - Load both skills' export lists and API signatures
   - Compose an integration section following the format from `{composeModeRules}`
   - Include VS feasibility verdict if a feasibility report (`feasibility-report-{project_name}.md`) exists in `{forge_data_folder}/`
   - Cite evidence from both skills: `[from skill: {skill_name}]`

All integration evidence inherits confidence tiers from the source skills. Load and apply the full **Confidence Tier Inheritance** matrix from `{composeModeRules}` to compute the correct tier for each pair (covers T1+T1, T1+T1-low, T1-low+T1-low, T1+T2, T1-low+T2, T2+T2 cases). Apply the `[composed]` suffix to all confidence labels — e.g., `T1 [composed]`, `T1-low [composed, +T2 annotations]`.

**VS verdict parsing (if feasibility report exists):** Read the `overall_verdict` from the report's YAML frontmatter. Parse the `## Integration Verdicts` markdown table for per-pair verdicts. For each architecture-detected pair, include `VS overall: {verdict}` and `VS pair: {verdict}` in the integration evidence per the format in `{composeModeRules}`. VS verdicts do not apply to inferred integrations since the VS report operates on architecture-described interactions only. Additionally, flag any pairs where VS reported `Risky` or `Blocked` by appending a `[VS: Risky]` or `[VS: Blocked]` warning annotation to the integration entry.

If no architecture document available:
- Infer potential integrations from skills sharing the same `language` field or sharing domain keywords in their SKILL.md descriptions (use the `usage_patterns` and `exports` fields from `per_library_extractions[]` built in step-04, or reload `{skills_output_folder}/{skill_dir}/SKILL.md` if full prose text is needed for keyword extraction)
- Mark inferred integrations: `[inferred from shared domain]` — use this suffix instead of `[composed]` for inferred integrations
- Inferred integrations qualify automatically — no file-count threshold applies

Skip to section 3 (Classify Integration Types) with the compose-mode pairs.

**If not compose_mode:**

For each library pair (A, B):

**Launch a subprocess** that greps across all source files to find files importing BOTH library A and library B. Return only file paths and import line numbers.

**Subprocess resolution:** Use the Grep tool (Claude Code), built-in search (Cursor), or `grep`/`rg` (CLI). See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

**Subprocess returns:** `{pair: [A, B], co_import_files: [{path, line_A, line_B}], count: N}`

**If subprocess unavailable:** Intersect the file lists from step 03 import counts for each pair.

**Threshold:** A pair must have 2+ co-import files to qualify as an integration pattern (single file co-imports may be incidental).

**CCC Semantic Augmentation (Forge+ and Deep with ccc):**

If `tools.ccc` is true AND `ccc_index.status` is `"fresh"` or `"stale"` in forge-tier.yaml, augment co-import detection with semantic search (max 1 query per library pair):

For each library pair that has exactly 1 co-import file (below the 2-file threshold), run `ccc_bridge.search("{libA} {libB}", source_root, top_k=10)` to find files where the two libraries interact semantically — even without explicit import co-location. If CCC returns additional files where both libraries appear, add them to the pair's co-import candidate list and re-evaluate against the 2-file threshold.

**Tool resolution for ccc_bridge.search:** Use `/ccc` skill search (Claude Code), ccc MCP server (Cursor), or `ccc search "{libA} {libB}" --path {source_root} --top 10` (CLI). See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md).

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
- Assign confidence: T1 if AST-verified, T1-low if source reading

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All library pairs analyzed for co-imports
- Integration types classified using pattern rules
- Hub libraries and cross-cutting patterns identified
- Integration graph built with confidence labels
- Graceful handling of zero integrations (not a failure)
- Auto-proceeded to step 06

### ❌ SYSTEM FAILURE:

- Fabricating integrations not evidenced in code
- Not applying the 2+ file threshold for pairs
- Starting to compile SKILL.md (step 06's job)
- Treating zero integrations as a workflow failure (it's valid)

**Master Rule:** Only document integrations that exist in actual code. Zero integrations is a valid result.
