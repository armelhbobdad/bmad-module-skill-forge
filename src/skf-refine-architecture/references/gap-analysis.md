---
nextStepFile: 'issue-detection.md'
refinementRulesData: '{refinementRulesPath}'
findingStorageData: 'references/finding-storage.md'
comentionProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'
  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. Append gap-analysis findings to the RA state file in {document_output_language}. -->

# Step 2: Gap Analysis

## STEP GOAL:

Find undocumented integration paths — library pairs that have compatible APIs (from the generated skills) but are not described in the architecture document. For each gap, document what APIs connect and propose an architecture section describing the integration.

## Rules

- Focus only on undocumented integration paths (gaps) — do not detect contradictions (Step 03) or suggest expansions (Step 04)
- Every gap must include evidence citations from actual skill content

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` or `{run_dir}` is no longer bound, read it from the `<!-- [RA-RUN] ... -->` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`). In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound (first existing path wins), then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-refine-architecture --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/exit-codes.md` describes the envelope). If no candidate exists, or the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 2. Extract Integration Claims from Architecture

**Run the mentions helper once.** Resolve `{comentionHelper}` from `{comentionProbeOrder}`; first existing path wins. If no candidate exists, `uv` cannot start it, or the command below exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `gap-analysis:comention`: "Refine Architecture cannot find the skills the document names: {its first stderr line, or with no candidate: `skf-comention-pairs.py` is not installed. Re-install SKF (`npx bmad-module-skill-forge install`).}" On exit 1 (its stderr names a staged input it refuses), fix that file and run the command once more before halting; a refused `{run_dir}/skill-terms.json` is not edited but written again with the enumerate helper (`{enumerateStackSkillsHelper}`, resolved from `{enumerateStackSkillsProbeOrder}`), as Step 01 §2 did: `uv run {enumerateStackSkillsHelper} terms --inventory "{run_dir}/skill-inventory.json" -o "{run_dir}/skill-terms.json"`. No step finds the mentions by hand. It reads the skill names and aliases Step 01 §2 wrote to `{run_dir}/skill-terms.json`, and one input this step stages first:

- `{run_dir}/technologies.json`: a JSON array of the libraries, frameworks, databases, services and tools the document names, each as the document writes it, in order of first mention. Programming languages, protocols and data formats do not count, and neither does a technology the document marks as deprecated, removed or being replaced, since no skill should exist for it.

If `{run_dir}` is no longer bound (a long run's context degraded), read it from the `<!-- [RA-RUN] ... -->` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`), as Step 01 §3c maps its keys. The technology list and the helper both read the document as `{analysis_doc}` (`{run_dir}/analysis-doc.md`), the architecture document with any earlier Refine Architecture pass set aside (Step 01 §1b), so RA's own old annotations never count as documented pairs, mentions or technologies:

```bash
uv run {comentionHelper} mentions --doc "{analysis_doc}" --skills "{run_dir}/skill-terms.json" --technologies "{run_dir}/technologies.json"
```

Its module docstring gives the contract. Cache its JSON as `{doc_mentions}`: §2b builds the document scope and the technologies with no skill from it too.

**Documented pairs.** `{doc_mentions}.candidates[]` holds each pair of skills that a body paragraph names in one unit (a run of prose, a list item, a table row) or through a lead-in (prose that names one skill, with a list item under it that names the other), each with those paragraphs as `evidence[]`. Judge every candidate, a lead-in one included, from its evidence (`unit_excerpt`, with its `header` and `unit_line`): it is a documented pair when an entry describes an *integration relationship* (data flowing between the two, one wrapping, bridging, extending or consuming the other, or a layer boundary connecting them), not mere co-mention in the same text. Record each documented pair as `{library_a, library_b, architectural_context}`, its context the quoted `unit_excerpt` of the entry that shows the relationship. A pair outside `candidates[]` is not documented: no paragraph names both, or they are only ever listed together (`list_only_pair_count` counts those pairs).

**Mermaid limitation:** the helper skips fenced code, so an integration drawn only in a diagram is never a candidate and may surface as a false-positive gap. When an entry of `{doc_mentions}.fenced_blocks[]` has the info string `mermaid`, inform the user: "Integration paths documented exclusively in Mermaid diagrams are excluded from co-mention analysis and may appear as false-positive gaps. Consider adding prose descriptions for diagram-only integration paths." When `{doc_mentions}.fenced_only` is not empty, add: "Named only inside fenced blocks: {fenced_only}." Display this warning informatively and immediately continue: it does not halt or modify the analysis sequence.

### 2b. Establish Document Scope

The skill inventory (Step 01 §2) can span a wider product surface than the architecture document under refinement, and pairs drawn from a different surface are not actionable gaps for this document (real-time A/V libraries wired into an admin-dashboard architecture, say).

Resolve the in-scope skill set:

- **If `{scope_skills}` was provided** (via `--scope-skills`, resolved in Step 01 §1): take it as `{in_scope_skills}`: it is authoritative. §3 checks each name against the inventory and names any that is not an inventory skill, so a mistyped name is reported instead of used.
- **Otherwise derive:** `{in_scope_skills}` = `{doc_mentions}.mentioned` plus `{doc_mentions}.fenced_only`: every inventory skill whose name or alias a body paragraph or a heading of the architecture document names, and every skill it names only inside fenced blocks, such as a diagram (the document still names it). Add an unmentioned skill only when its relevance is ambiguous (the document describes its technology without naming it, say): be conservative and treat it as **in-scope**. Surfacing a borderline gap is safer than burying a real one. A skill the document names only through a repository or folder alias that is also a common word (its `terms[]` holds only `alias` entries, such as `core`, `ai`, `sdk` or `src`, matched in "core services" or "AI features") is ambiguous too: it stays in scope, but the confirmation below lists it as ambiguous, not as named.

`{out_of_scope_skills}` = inventory skills not in `{in_scope_skills}`. A library pair is **out-of-scope** when either of its libraries is in `{out_of_scope_skills}`.

**Safe default:** If scope cannot be derived (`mentioned` and `fenced_only` are both empty: the architecture names no inventory skill) and no `{scope_skills}` was provided, treat all skills as in-scope (leave `{in_scope_skills}` empty: §3 then puts every skill in scope) and note: "Could not derive document scope: analyzing all skill pairs." The confirmation below then asks the user to check the document. When the confirmation ends with every skill still in scope, as a headless run's does at once, record the warning `scope_fallback_all_skills: the document names no inventory skill, so every skill is in scope` with §3's command; an edit that takes a skill out records none, since §3's `out_of_scope_skills` warning names those skills.

**Confirm a derived scope.** When the scope was derived (no `{scope_skills}`) and `{out_of_scope_skills}` is not empty or an in-scope skill is ambiguous, or the safe default applies, show the split once, before §4 loads the API surfaces, so the user can correct it without a re-run. A scope from `--scope-skills` is already the user's choice, so it shows no gate. In the Why column, `{term}` is the skill's name or the alias that names it in the document, one row of its `{doc_mentions}.skills[].terms[]` with that row's counts, so a surprising match shows.

"**Document scope** (derived from the architecture document)

| Skill | Scope | Why |
|-------|-------|-----|
| {skill} | In scope | {named as `{term}` in {paragraph_count} paragraph(s) and {heading_count} heading(s), or only in a fenced block; or ambiguous and kept in scope: named only as the common word `{term}`, or not named} |
| {skill} | Out of scope | not named in the document |

No gap, issue or improvement is looked for with an out-of-scope skill: the VS verdicts and the document's claims that involve one are listed for awareness only and stay out of the refined document.

- Type **C** to keep this scope
- Type skill names to bring them **into** scope
- Type **-skill_name** to take a skill **out** of scope"

**Under the safe default**, show "Check that `{architecture_doc}` is the document you meant: it names none of these skills." in place of the title line, and one row `| {skill} | In scope | the document names no inventory skill |` for each skill of `{doc_mentions}.skills[]` (a skill an edit takes out moves to the Out of scope row), with the rest of the message and the same menu. An edit starts from every one of those skills in `{in_scope_skills}`, and §3's `[RA-SCOPE]` block then says the scope was derived then edited at the §2b confirmation; unedited, `{in_scope_skills}` stays empty, as §3 expects. When `{architecture_doc}` is no longer bound, read it from the `<!-- [RA-RUN] ... -->` block of the RA state file.

Display: **Select:** [C] Continue with this scope | [X] Cancel

**GATE [default: C]**: present the menu and wait for the user's choice. When `{headless_mode}` is no longer bound, read it from the `<!-- [RA-RUN] ... -->` block of the RA state file. If `{headless_mode}`: keep the derived sets and auto-proceed with [C], log: "headless: auto-confirm derived document scope (in scope: {in_scope_skills}; out of scope: {out_of_scope_skills})", giving each in-scope skill its Why from the table (the term that named it, or why it is ambiguous). Under the safe default, keep every skill in scope: the log and `in_scope` name each skill of `{doc_mentions}.skills[]`, and `out_of_scope` is `[]`. Record that decision in the run sink the moment it is taken: stage `{run_dir}/decision.json` as `{"gate": "gap-analysis.scope", "default_action": "C", "taken_action": "C", "reason": "<the line logged>", "evidence": {"in_scope": [<the in-scope skills>], "out_of_scope": [<the out-of-scope skills>]}}`, then run:

```bash
uv run {emitEnvelopeHelper} record --workflow skf-refine-architecture --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

- IF C: keep the current sets and go on with the rest of this section.
- IF cancel / exit / [X] / q / :q: HALT (exit code 6, `halt_reason: "user-cancelled"`) at phase `gap-analysis:scope` and display "Cancelled: no refinement was performed." These global cancel tokens pre-empt the edit branch below.
- IF the input names skills: each skill name moves that skill into `{in_scope_skills}` and each `-skill_name` moves it out; recompute `{out_of_scope_skills}`. Name any entry that is not an inventory skill, and refuse an edit that would leave `{in_scope_skills}` empty. Then redisplay the table and the menu.
- IF anything else: answer it (a question about the split, say), then redisplay the menu.

**Technologies with no skill.** `{unverified_technologies}` = `{doc_mentions}.unverified_technologies`: the technologies §2 listed that no inventory skill covers, read in `{analysis_doc}` so an earlier Refine Architecture pass never adds a name. The helper decides what a skill covers (its `technologies[]` names, for each technology, the skill, term and `kind` of each match), so no step compares a technology with a skill by hand. A `covered_by` entry of kind `alias-contained` or `name-contained` (an alias such as `ai` or `core`, or a skill name such as `react`, found only inside a longer name) does not cover the technology, which stays in `{unverified_technologies}` unless the document shows that term is that technology (`next` for Next.js, `vue` for "Vue 3"; React Native and React Query are not `react`), as the derived scope above judges common-word aliases. No step can check what the document says about these technologies: §6 names them, and Step 05 lists them in the Refinement Summary as not verified. The list depends on the inventory, not on the scope, so `--scope-skills` and the edits above leave it unchanged.

Store `{in_scope_skills}`, `{out_of_scope_skills}` and `{unverified_technologies}` as workflow state; §3 settles the two sets and splits the pairs by them. Step 03 (issue detection) and Step 04 (improvements) reuse the scope sets and the pair lists §3 builds, and Step 05 (compile) reuses `{unverified_technologies}`; §3 also records them all in the RA state file, once it settles them.

### 3. Split the Library Pairs by Scope

Now that §2b fixed the scope, split the library pairs once with the enumerate helper (`{enumerateStackSkillsHelper}`, resolved from `{enumerateStackSkillsProbeOrder}`). It reads every skill name from the inventory Step 01 §2 saved, builds every unique pair of those skills and splits the pairs by the scope:

```bash
uv run {enumerateStackSkillsHelper} scope --inventory "{run_dir}/skill-inventory.json" --in-scope "{in_scope_names}"
```

`{in_scope_names}` is every name in `{in_scope_skills}`, comma-separated, and empty under the §2b safe default. If no candidate exists, `uv` cannot start it, or the command exits non-zero, HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `gap-analysis:split`: "Refine Architecture cannot split the skill pairs by scope: {its first stderr line, or with no candidate: `skf-enumerate-stack-skills.py` is not installed. Re-install SKF (`npx bmad-module-skill-forge install`).}" No step lists the skill names or builds a pair by hand. Act on its JSON:

- Bind `{in_scope_skills}` ← `in_scope`, `{out_of_scope_skills}` ← `out_of_scope`, `{in_scope_pairs}` ← `in_scope_pairs` and `{out_of_scope_pairs}` ← `out_of_scope_pairs`. A pair is in scope when both of its libraries are, and each pair lands in exactly one list.
- When `unknown` is not empty, name those entries once: "Not an inventory skill, left out of the scope: {unknown}." They come from `--scope-skills`, since a derived scope and the §2b edits hold only inventory skills. Record the warning `unknown_scope_skills: <the unknown names, comma-separated>`.
- When `in_scope` is empty (the §2b safe default, or `--scope-skills` named no inventory skill at all), every skill is in scope: run the command again with the first result's `out_of_scope` names, comma-separated, as `--in-scope`. That second result's `out_of_scope` is empty; when it is not, a name was left out: run the command again with its `out_of_scope` names added. When `--scope-skills` named no inventory skill, record the warning `scope_fallback_all_skills: --scope-skills named no inventory skill, so every skill is in scope` (the safe default recorded its own in §2b).
- `pair_count` equals `{skill_count}*({skill_count}-1)/2`, the number of unique pairs of the `{skill_count}` skills Step 01 §2 counted. When it does not, `{skill_count}` was lost: bind it again from `skill_count` in `{run_dir}/skill-inventory.json`.
- Once these bindings are final, when `{out_of_scope_skills}` is not empty, record the warning `out_of_scope_skills: <n> skills left out of the scope of this run: <the names, comma-separated>`, so every headless envelope names what this run did not check, a scope from `--scope-skills` included.

Each warning goes into the run sink as it is raised, so the envelope and the result file report it (the command single-quotes it, so no warning holds a `'`):

```bash
uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning>'
```

Append the scope under a `<!-- [RA-SCOPE] ... -->` block of the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`) once these bindings are final, before §4 reads a surface: `{in_scope_skills}`, `{out_of_scope_skills}`, how the scope was set (`--scope-skills`, derived, derived then edited at the §2b confirmation, or every skill by the safe default), any name this section reported as not an inventory skill, `{in_scope_pairs}`, `{out_of_scope_pairs}` and `{unverified_technologies}`. A run appends it once: §4, Step 03, Step 04 and Step 05 read the block back if context degrades on a long run.

§4 reads the surfaces of `{in_scope_skills}` only, and §5 and Step 04 §4 read `{in_scope_pairs}` only, instead of checking each pair's scope again; Step 03 §3 sets aside a claim that names a skill of `{out_of_scope_skills}`, and Step 03 §4 passes `{in_scope_skills}` to the `verdicts` join.

### 4. Load Skill API Surfaces for Cross-Reference

Once §3's bindings are final, for each skill in `{in_scope_skills}`, delegate reading to a parallel subagent. Launch up to **8 subagents concurrently** (batch larger inventories in rounds of 8). Hand each its skill's name. Each reads that skill's `exports[]` from the `skills[]` entry of that name in `{run_dir}/skill-inventory.json` (Step 01 §2), then its SKILL.md, and its `references/*.md` for the signatures SKILL.md lacks (a split-body skill keeps its full API there), and returns only this compact JSON, with no prose:

```json
{
  "skill_name": "...",
  "exports": ["functionName(params): ReturnType", "..."],
  "protocols": ["HTTP", "gRPC", "WebSocket", "message queue", "file I/O", "IPC"],
  "data_formats": ["JSON", "protobuf", "CSV", "binary", "streaming"],
  "capabilities": ["offline sync", "conflict-free merges", "..."]
}
```

**Extraction rules for subagents:**
- `exports`: the signature of each name of that `exports[]` that SKILL.md or `references/` shows, and no name the list lacks (Step 03 reads which names exist from the file itself). Only when the list is empty (a stack skill, or `exports_source` `unknown`), extract the exported functions with signatures and the exported types, interfaces and classes from SKILL.md
- `protocols`: any protocol indicators found in the files read
- `data_formats`: any data format indicators found in the files read
- `capabilities`: the capabilities and features the SKILL.md documents beyond its exports, one short phrase each
- If a field has no matches, return an empty array `[]`

**When subagents are unavailable**, read the in-scope skills yourself, one at a time, in the order of the `skills[]` of `{run_dir}/skill-inventory.json`: for each, read what a subagent would (its `exports[]`, its SKILL.md and its `references/*.md`), write its compact JSON by the rules above, and append it to the RA state file as its own `<!-- [RA-SURFACES] ... -->` block before going on to the next. Each summary is in the state file as its read ends, so a context compaction loses none.

**Parent collects all subagent JSON summaries.** Apart from the fallback's reads, do not load full SKILL.md content into parent context. Store the collected summaries as `{skill_api_surfaces}` workflow state, which Step 03 (issue detection) and Step 04 (improvements) reuse. As each round returns, append its summaries to the RA state file (`{forge_data_folder}/ra-state-{project_name}.md`) as a `<!-- [RA-SURFACES] ... -->` block, before the next round starts: Steps 03 and 04 read the blocks back from it if context degrades on a long run, and after a context loss in the middle of this section the blocks already appended name the skills read, so only the others are read. If `{run_dir}` or `{in_scope_skills}` is no longer bound, read `{run_dir}` from the `<!-- [RA-RUN] ... -->` block of the same file and `{in_scope_skills}` from its `<!-- [RA-SCOPE] ... -->` block (§3).

**From the skill inventory (Step 01 §2), also take** each skill's `language` (the enumerate helper reads it from `metadata.json`: a string, a list of strings for a stack, or null when none is recorded). Do not open `metadata.json` in the parent.

### 5. Cross-Reference: Identify Gaps

For each pair in `{in_scope_pairs}` (from §3) not already documented in the architecture (§2):

**Check API compatibility:**
- Does Library A export types or data that Library B can consume?
- Do both libraries share a compatible protocol or data format?
- Are they in the same language or is there a bridge mechanism available?

**If compatible APIs exist (in-scope pair) but NO architecture mention:**
- Type the gap by the Gap Classification of `{refinementRulesData}`. If `{refinementRulesPath}`, which `{refinementRulesData}` names, is no longer bound, read it from the `<!-- [RA-RUN] ... -->` block of the RA state file
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

**If no compatible APIs:** skip the pair, since not every pair integrates.

### 6. Report Gaps & Store Findings

Report the in-scope gap count, then list each gap as a row of **# / Library A / Library B / Gap Type / Connecting APIs** followed by its full §5 citation. Three signals are not inferable from the counts and must survive regardless of format:

- **N == 1 (`{skill_count}` is 1: the inventory holds one skill):** gap analysis is skipped, since pairwise integration analysis needs ≥2 skills, and libraries without a matching skill are invisible to it. Recommend generating skills for all architecture libraries with [CS] or [QS] before re-running [RA], and note issue detection still runs.
- **Skills were left out of the scope (`{out_of_scope_skills}` from §3 is not empty):** name them in one line, since no gap was looked for with them: "Not analyzed, outside this document's scope: {out_of_scope_skills}. Re-run with `--scope-skills` naming the skills to include to pull any that belong into scope."
- **The architecture names technologies with no skill (`{unverified_technologies}` from §2b is not empty):** name them. No skill backs what the document says about them, so no step checks it; recommend generating their skills with [CS] or [QS] before re-running [RA].

Store the gap findings under a `<!-- [RA-GAPS] ... -->` block and the names of `{out_of_scope_skills}` under the shared `<!-- [RA-OUT-OF-SCOPE] ... -->` marker, as `{findingStorageData}` says (a gap that matches one a review dropped goes under `[RA-DISMISSED]` instead). §3 already appended the scope's `<!-- [RA-SCOPE] ... -->` block.

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

