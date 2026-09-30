---
nextStepFile: 'issue-detection.md'
refinementRulesData: '{refinementRulesPath}'
# §2 runs `{comentionHelper}` mentions once (which inventory skills the
# architecture document names, and the pairs a paragraph names together);
# §3 runs `{enumerateStackSkillsHelper}` scope to split the pairs by the
# scope. Each resolves from its probe order (installed SKF module path
# first, src/ dev-checkout fallback); first existing path wins.
comentionProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'
  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
---

<!-- Config: communicate in {communication_language}. Append gap-analysis findings to the RA state file in {document_output_language}. -->

# Step 2: Gap Analysis

## STEP GOAL:

Find undocumented integration paths — library pairs that have compatible APIs (from the generated skills) but are not described in the architecture document. For each gap, document what APIs connect and propose an architecture section describing the integration.

## Rules

- Focus only on undocumented integration paths (gaps) — do not detect contradictions (Step 03) or suggest expansions (Step 04)
- Every gap must include evidence citations from actual skill content

## MANDATORY SEQUENCE

### 1. Reference Refinement Rules

Use the refinement rules loaded in Step 01 from `{refinementRulesData}`. If not available in context, reload from `{refinementRulesData}`.

Extract: gap classification (Missing Integration Path, Undocumented Data Flow, Absent Bridge Layer) and detection method.

### 2. Extract Integration Claims from Architecture

**Run the mentions helper once.** Resolve `{comentionHelper}` from `{comentionProbeOrder}`; first existing path wins. Then run:

```bash
uv run {comentionHelper} mentions --doc "{architecture_doc}" --skills -
```

piping on stdin a JSON array with one object per `skill_inventory.skills[]` entry: `{"name": "<name>", "aliases": [...]}`, where `aliases` holds the entry's `source_repo_basename` and `source_root_basename` that are not null (the repository and folder the skill was built from, so a skill named `oms-cognee` is matched where the document says "Cognee"). Use a temp file under `{forge_data_folder}/` if stdin piping is unavailable. The helper matches each name and alias case-insensitively at word boundaries, reads each occurrence as its longest term (so `react-dom` never counts as `react`) and skips fenced code; its module docstring gives the contract. Cache its JSON as `{doc_mentions}`: §2b builds the document scope from it too.

**Documented pairs.** `{doc_mentions}.candidates[]` holds each pair of skills that a body paragraph names in one unit (a run of prose, a list item, a table row) or through a lead-in (prose that names one skill, with a list item under it that names the other), each with those paragraphs as `evidence[]`. Judge every candidate, a lead-in one included, from its evidence (`unit_excerpt`, with its `header` and `unit_line`): it is a documented pair when an entry describes an *integration relationship* (data flowing between the two, one wrapping, bridging, extending or consuming the other, or a layer boundary connecting them), not mere co-mention in the same text. A pair outside `candidates[]` is not documented: no paragraph names both, or they are only ever listed together (`list_only_pair_count` counts those pairs).

**Mermaid limitation:** the helper skips fenced code, so an integration drawn only in a diagram is never a candidate and may surface as a false-positive gap. When an entry of `{doc_mentions}.fenced_blocks[]` has the info string `mermaid`, inform the user: "Integration paths documented exclusively in Mermaid diagrams are excluded from co-mention analysis and may appear as false-positive gaps. Consider adding prose descriptions for diagram-only integration paths." When `{doc_mentions}.fenced_only` is not empty, add: "Named only inside fenced blocks: {fenced_only}." Display this warning informatively and immediately continue: it does not halt or modify the analysis sequence.

**Build documented pairs list:**
- Each pair: `{library_a, library_b, architectural_context}`
- `architectural_context`: the quoted `unit_excerpt` of the evidence entry that shows the relationship

**Graceful degradation:** if `{comentionHelper}` has no existing candidate, or `uv` cannot run it, find the same facts by hand under the rule above (name and aliases, case-insensitive, word boundaries, the longest term at each occurrence, fenced code skipped), then judge them the same way.

### 2b. Establish Document Scope

The skill inventory (Step 01 §2) can span a wider product surface than the architecture document under refinement. Pairs drawn from a different surface are not actionable gaps for this document — surfacing them injects irrelevant integration recommendations (e.g. wiring real-time A/V libraries into an admin-dashboard architecture).

Resolve the in-scope skill set:

- **If `{scope_skills}` was provided** (via `--scope-skills`, resolved in Step 01 §1): take it as `{in_scope_skills}`: it is authoritative. §3 checks each name against the inventory and names any that is not an inventory skill, so a mistyped name is reported instead of used.
- **Otherwise derive:** `{in_scope_skills}` = `{doc_mentions}.mentioned` plus `{doc_mentions}.fenced_only`: every inventory skill whose name or alias a body paragraph or a heading of the architecture document names, and every skill it names only inside fenced blocks, such as a diagram (the document still names it). Add an unmentioned skill only when its relevance is ambiguous (the document describes its technology without naming it, say): be conservative and treat it as **in-scope**. Surfacing a borderline gap is safer than burying a real one. A skill the document names only through a repository or folder alias that is also a common word (`core`, `ai`, `sdk` or `src`, matched in "core services" or "AI features") is ambiguous too: it stays in scope, but the confirmation below lists it as ambiguous, not as named.

`{out_of_scope_skills}` = inventory skills not in `{in_scope_skills}`. A library pair is **out-of-scope** when either of its libraries is in `{out_of_scope_skills}`.

**Safe default:** If scope cannot be derived (`mentioned` and `fenced_only` are both empty: the architecture names no inventory skill) and no `{scope_skills}` was provided, treat all skills as in-scope and note: "Could not derive document scope: analyzing all skill pairs." This keeps borderline gaps visible rather than hiding them.

**Confirm a derived scope.** When the scope was derived (no `{scope_skills}`) and `{out_of_scope_skills}` is not empty or an in-scope skill is ambiguous, show the split once, before §4 loads the API surfaces, so the user can correct it without a re-run. A scope from `--scope-skills` is already the user's choice, and the safe default leaves no skill out, so neither shows this gate. In the Why column, `{term}` is the skill's name or the alias that names it in the document (its `{doc_mentions}.skills[].paragraphs[]` show where), so a surprising match shows.

"**Document scope** (derived from the architecture document)

| Skill | Scope | Why |
|-------|-------|-----|
| {skill} | In scope | {named as `{term}` in {paragraph_count} paragraph(s) and {heading_count} heading(s), or only in a fenced block; or ambiguous and kept in scope: named only as the common word `{term}`, or not named} |
| {skill} | Out of scope | not named in the document |

Pairs, VS verdicts and improvement suggestions that involve an out-of-scope skill are listed for awareness only and stay out of the refined document.

- Type **C** to keep this scope
- Type skill names to bring them **into** scope
- Type **-skill_name** to take a skill **out** of scope"

Display: **Select:** [C] Continue with this scope | [X] Cancel

**GATE [default: C]**: present the menu and wait for the user's choice. If `{headless_mode}`: keep the derived sets and auto-proceed with [C], log: "headless: auto-confirm derived document scope (in scope: {in_scope_skills}; out of scope: {out_of_scope_skills})", giving each in-scope skill its Why from the table (the term that named it, or why it is ambiguous).

- IF C: keep the current sets and go on with the rest of this section.
- IF cancel / exit / [X] / q / :q: HALT (exit code 6, `halt_reason: "user-cancelled"`) and display "Cancelled: no refinement was performed." These global cancel tokens pre-empt the edit branch below.
- IF the input names skills: each skill name moves that skill into `{in_scope_skills}` and each `-skill_name` moves it out; recompute `{out_of_scope_skills}`. Name any entry that is not an inventory skill, and refuse an edit that would leave `{in_scope_skills}` empty. Then redisplay the table and the menu.
- IF anything else: answer it (a question about the split, say), then redisplay the menu.

**Technologies with no skill.** `{unverified_technologies}` = the libraries, frameworks, databases, services and tools the architecture document names that no inventory skill covers. A skill covers a technology when §2's matching rule (case-insensitive, at word boundaries, each occurrence read as its longest term) finds one of the skill's terms (its name or an alias §2 passed to the mentions helper) inside the technology's name as the document writes it, so a `next` skill covers `Next.js`; or when a term equals that name once case, spaces, hyphens, dots and underscores are ignored, so a `react-router` skill covers `React Router` and a `tailwindcss` skill covers `Tailwind CSS`. Programming languages, protocols and data formats do not count, and neither does a technology the document marks as deprecated, removed or being replaced, since no skill should exist for it. Keep each name as the document writes it, in order of first mention. No step can check what the document says about these technologies: §6 names them, and Step 05 lists them in the Refinement Summary as not verified. The list depends on the inventory, not on the scope, so `--scope-skills` and the edits above leave it unchanged.

Store `{in_scope_skills}`, `{out_of_scope_skills}` and `{unverified_technologies}` as workflow state; §3 settles the two sets and splits the pairs by them. Step 03 (issue detection) and Step 04 (improvements) reuse the scope sets and the pair lists §3 builds, and Step 05 (compile) reuses `{unverified_technologies}`; §6 also records them all in the RA state file.

### 3. Split the Library Pairs by Scope

The pair set is `skill_inventory.pairs`, the enumerate helper's `--pairs` output cached in Step 01 §2: the complete, deterministic set of unique library pairs. Do not re-derive it in-context: a silently dropped or duplicated pair is a missed integration gap, this workflow's headline output. Now that §2b fixed the scope, split it once with the same helper (`{enumerateStackSkillsHelper}`, resolved from `{enumerateStackSkillsProbeOrder}`):

```bash
uv run {enumerateStackSkillsHelper} scope --skills "{inventory_names}" --in-scope "{in_scope_names}"
```

`{inventory_names}` is the `name` of every `skill_inventory.skills[]` entry and `{in_scope_names}` every name in `{in_scope_skills}`, each comma-separated. The helper builds the pairs exactly as `--pairs` did and splits them:

- Bind `{in_scope_skills}` ← `in_scope`, `{out_of_scope_skills}` ← `out_of_scope`, `{in_scope_pairs}` ← `in_scope_pairs` and `{out_of_scope_pairs}` ← `out_of_scope_pairs`. A pair is in scope when both of its libraries are, and each pair lands in exactly one list.
- When `unknown` is not empty, name those entries once: "Not an inventory skill, left out of the scope: {unknown}." They come from `--scope-skills`, since a derived scope and the §2b edits hold only inventory skills.
- When `--scope-skills` named no inventory skill at all (`in_scope` is empty), apply the §2b safe default: run the command again with `{inventory_names}` as `--in-scope` too.
- `pair_count` equals `skill_inventory.pair_count`. When it does not, a name was left out of `{inventory_names}`: run the command again with every name.

§5, Step 03 §4 and Step 04 §4 read these two pair lists instead of checking each pair's scope again.

If the helper is unavailable (the Step 01 §2 fallback path ran, so `skill_inventory.pairs` is absent too), derive the pairs from the inventory and split them by the same rule as a graceful-degradation fallback only.

### 4. Load Skill API Surfaces for Cross-Reference

<!-- Subagent delegation: read SKILL.md files in parallel, return compact JSON -->

For each library in the skill inventory, delegate reading to a parallel subagent. Launch up to **8 subagents concurrently** (batch larger inventories in rounds of 8).

**Each subagent receives one skill's SKILL.md path and:**
1. Reads the SKILL.md file
2. Extracts the API surface
3. Returns only this compact JSON — no prose or extra commentary:

```json
{
  "skill_name": "...",
  "exports": ["functionName(params): ReturnType", "..."],
  "protocols": ["HTTP", "gRPC", "WebSocket", "message queue", "file I/O", "IPC"],
  "data_formats": ["JSON", "protobuf", "CSV", "binary", "streaming"]
}
```

**Extraction rules for subagents:**
- `exports`: exported functions with signatures, exported types/interfaces/classes
- `protocols`: any protocol indicators found in the SKILL.md
- `data_formats`: any data format indicators found in the SKILL.md
- If a field has no matches, return an empty array `[]`

**Parent collects all subagent JSON summaries.** Do not load full SKILL.md content into parent context. Store the collected summaries as `{skill_api_surfaces}` workflow state — Step 03 (issue detection) and Step 04 (improvements) reuse them exactly like `{in_scope_skills}`, rather than re-reading each SKILL.md into the parent. This §4 delegate-the-read (compact-JSON return, no full-file load in parent) is the canonical API-surface read pattern for the workflow.

**From the skill inventory (Step 01 §2), also take** each skill's `language` (the enumerate helper reads it from `metadata.json`: a string, a list of strings for a stack, or null when none is recorded) and its `exports` count and names. Do not open `metadata.json` in the parent.

### 5. Cross-Reference: Identify Gaps

For each pair in `{in_scope_pairs}` or `{out_of_scope_pairs}` (from §3) not already documented in the architecture (§2):

**Check API compatibility:**
- Does Library A export types or data that Library B can consume?
- Do both libraries share a compatible protocol or data format?
- Are they in the same language or is there a bridge mechanism available?

**Scope routing (from §3):** Before classifying, check which list holds the pair. A pair in `{out_of_scope_pairs}` does not go to the gap list even when its APIs are compatible: record it in the informational **Out-of-Scope** bucket instead (a compatible pair that belongs to a different product surface than this architecture). Only pairs in `{in_scope_pairs}` proceed to gap classification below.

**If compatible APIs exist (in-scope pair) but NO architecture mention:**
- Classify the gap type (Missing Integration Path, Undocumented Data Flow, or Absent Bridge Layer)
- Document the connecting APIs from both skills
- Propose a brief architecture section describing the integration

**Cite each gap in this format:**
```
**[GAP]**: {description}

Evidence:
- {skill_a} exports: `{function}({params}) -> {return_type}`
- {skill_b} accepts: `{function}({params})`
- Compatibility: {explanation}

Suggestion: {proposed architecture section content}
```

**If no compatible APIs:** Skip this pair — not all pairs need to integrate.

### 6. Report Gaps & Store Findings

Report the in-scope gap count, then list each gap as a row of **# / Library A / Library B / Gap Type / Connecting APIs** followed by its full §5 citation. Three signals are not inferable from the counts and must survive regardless of format:

- **N == 1 (only one skill loaded):** gap analysis is skipped — pairwise integration analysis needs ≥2 skills, and libraries without a matching skill are invisible to it. Recommend generating skills for all architecture libraries with [CS] or [QS] before re-running [RA], and note issue detection still runs.
- **Out-of-scope compatible pairs exist (from §2b/§5):** list them separately for awareness only — they were not counted as gaps — and note that re-running with `--scope-skills` (naming the skills to include) pulls any that belong into scope.
- **The architecture names technologies with no skill (`{unverified_technologies}` from §2b is not empty):** name them. No skill backs what the document says about them, so no step checks it; recommend generating their skills with [CS] or [QS] before re-running [RA].

Store the **in-scope** gap findings per the Finding Storage rule (refinement rules), under a `<!-- [RA-GAPS] ... -->` block. Record out-of-scope pairs under a separate `<!-- [RA-OUT-OF-SCOPE] ... -->` marker so Step 05 leaves them out of the refined document — they are informational only.

Append the scope under a `<!-- [RA-SCOPE] ... -->` block too: `{in_scope_skills}`, `{out_of_scope_skills}`, how the scope was set (`--scope-skills`, derived, derived then edited at the §2b confirmation, or every skill by the safe default), any name §3 reported as not an inventory skill, `{in_scope_pairs}`, `{out_of_scope_pairs}` and `{unverified_technologies}`. Step 03, Step 04 and Step 05 read the block back if context degrades on a long run.

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

