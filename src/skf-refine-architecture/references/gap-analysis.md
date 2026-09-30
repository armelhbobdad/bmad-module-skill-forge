---
nextStepFile: 'issue-detection.md'
refinementRulesData: '{refinementRulesPath}'
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

Parse the architecture document for statements describing two or more technologies working together.

**Detection method — prose-based co-mention analysis:** From prose text, find sentences or paragraphs where two or more technology names appear in an *integration relationship* — data flowing between them, one wrapping/bridging/extending/consuming another, or a layer boundary connecting them — not mere co-mention in the same document.

**Mermaid limitation:** Detect co-mentions from prose text only, not from Mermaid diagram syntax — an integration drawn only in a diagram would otherwise surface as a false-positive gap. If `` ```mermaid `` blocks are present in the architecture document, inform the user: "Integration paths documented exclusively in Mermaid diagrams are excluded from co-mention analysis and may appear as false-positive gaps. Consider adding prose descriptions for diagram-only integration paths." Display this warning informatively and immediately continue — this does not halt or modify the analysis sequence.

**Build documented pairs list:**
- Each pair: `{library_a, library_b, architectural_context}`
- `architectural_context`: the quoted text or paraphrased description of their relationship

### 2b. Establish Document Scope

The skill inventory (Step 01 §2) can span a wider product surface than the architecture document under refinement. Pairs drawn from a different surface are not actionable gaps for this document — surfacing them injects irrelevant integration recommendations (e.g. wiring real-time A/V libraries into an admin-dashboard architecture).

Resolve the in-scope skill set:

- **If `{scope_skills}` was provided** (via `--scope-skills`, resolved in Step 01 §1): use it verbatim as `{in_scope_skills}` — it is authoritative.
- **Otherwise derive:** `{in_scope_skills}` = every inventory skill whose name or primary technology is referenced anywhere in the architecture document (reuse the technology references parsed in §2; match on skill name and library/technology keywords, case-insensitive, word-boundary). Be conservative — when a skill's relevance is ambiguous, treat it as **in-scope**. Surfacing a borderline gap is safer than burying a real one.

`{out_of_scope_skills}` = inventory skills not in `{in_scope_skills}`. A library pair is **out-of-scope** when either of its libraries is in `{out_of_scope_skills}`.

**Safe default:** If scope cannot be derived (e.g. the architecture references no inventory skill by name) and no `{scope_skills}` was provided, treat all skills as in-scope and note: "Could not derive document scope — analyzing all skill pairs." This keeps borderline gaps visible rather than hiding them.

**Confirm a derived scope.** When the scope was derived (no `{scope_skills}`) and `{out_of_scope_skills}` is not empty, show the split once, before §4 loads the API surfaces, so the user can correct it without a re-run. A scope from `--scope-skills` is already the user's choice, and the safe default leaves no skill out, so neither shows this gate.

"**Document scope** (derived from the architecture document)

| Skill | Scope | Why |
|-------|-------|-----|
| {skill} | In scope | {named as `term`, or ambiguous and kept in scope} |
| {skill} | Out of scope | not named in the document |

Pairs, VS verdicts and improvement suggestions that involve an out-of-scope skill are listed for awareness only and stay out of the refined document.

- Type **C** to keep this scope
- Type skill names to bring them **into** scope
- Type **-skill_name** to take a skill **out** of scope"

Display: **Select:** [C] Continue with this scope | [X] Cancel

**GATE [default: C]**: present the menu and wait for the user's choice. If `{headless_mode}`: keep the derived sets and auto-proceed with [C], log: "headless: auto-confirm derived document scope (in scope: {in_scope_skills}; out of scope: {out_of_scope_skills})".

- IF C: keep the current sets and go on with the rest of this section.
- IF cancel / exit / [X] / q / :q: HALT (exit code 6, `halt_reason: "user-cancelled"`) and display "Cancelled: no refinement was performed." These global cancel tokens pre-empt the edit branch below.
- IF the input names skills: each skill name moves that skill into `{in_scope_skills}` and each `-skill_name` moves it out; recompute `{out_of_scope_skills}`. Name any entry that is not an inventory skill, and refuse an edit that would leave `{in_scope_skills}` empty. Then redisplay the table and the menu.
- IF anything else: answer it (a question about the split, say), then redisplay the menu.

**Technologies with no skill.** `{unverified_technologies}` = the libraries, frameworks, databases, services and tools the architecture document names that match no inventory skill under the rule above (skill name and library/technology keywords, case-insensitive, word-boundary). Programming languages, protocols and data formats do not count, and neither does a technology the document marks as deprecated, removed or being replaced, since no skill should exist for it. Keep each name as the document writes it, in order of first mention. No step can check what the document says about these technologies: §6 names them, and Step 05 lists them in the Refinement Summary as not verified. The list depends on the inventory, not on the scope, so `--scope-skills` and the edits above leave it unchanged.

Store `{in_scope_skills}`, `{out_of_scope_skills}` and `{unverified_technologies}` as workflow state. Step 03 (issue detection) and Step 04 (improvements) reuse the scope sets, and Step 05 (compile) reuses `{unverified_technologies}`; §6 also records all three in the RA state file.

### 3. Read the Pre-Computed Library Pairs

Read the pre-computed unique library pairs from `skill_inventory.pairs` (the enumerate helper's `--pairs` output cached in Step 01 §2 — the complete, deterministic pair set). Do not re-derive it in-context: a silently dropped or duplicated pair is a missed integration gap, this workflow's headline output.

If `skill_inventory.pairs` is absent (the helper was unavailable and the Step 01 §2 fallback path ran), derive the pairs from the inventory as a graceful-degradation fallback only.

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

**From metadata.json (read in parent — lightweight), also extract:**
- `language` — primary programming language
- `exports` — export count and names

### 5. Cross-Reference: Identify Gaps

For each library pair in `skill_inventory.pairs` (from §3) not already documented in the architecture:

**Check API compatibility:**
- Does Library A export types or data that Library B can consume?
- Do both libraries share a compatible protocol or data format?
- Are they in the same language or is there a bridge mechanism available?

**Scope routing (from §2b):** Before classifying, check the pair's scope. If the pair is **out-of-scope** (either library is in `{out_of_scope_skills}`), do not add it to the gap list even when its APIs are compatible — record it in the informational **Out-of-Scope** bucket instead (a compatible pair that belongs to a different product surface than this architecture). Only **in-scope** pairs proceed to gap classification below.

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

Append the scope under a `<!-- [RA-SCOPE] ... -->` block too: `{in_scope_skills}`, `{out_of_scope_skills}`, how the scope was set (`--scope-skills`, derived, derived then edited at the §2b confirmation, or every skill by the safe default) and `{unverified_technologies}`. Step 04 and Step 05 read the block back if context degrades on a long run.

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

