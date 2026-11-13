---
nextStepFile: 'write-brief.md'
reviseStepFile: 'scope-definition.md'
analyzeStepFile: 'analyze-target.md'
advancedElicitationSkill: '/bmad-advanced-elicitation'
partyModeSkill: '/bmad-party-mode'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Confirm Brief

## Rules

- Do not proceed without explicit user approval (P2 confirmation gate)

## Sequence

### 1. Assemble Complete Brief

Use the values steps 1 to 3 accepted, all in conversation, without loading `assets/skill-brief-schema.md` (§4 loads it only to cite a field's rule): §2 shows the fields the user reviews, and step 5 §3 names every key the writer takes. On a derive run, `forge_tier` is the `tier` step 0 §1 bound, `created` is today's date and `created_by` is `{user_name}`; an unset `scripts_intent` or `assets_intent` is `detect`.

**Ratify run (`ratify_mode: true`):** steps 2-3 were skipped (step 1 ratified a brief through `references/gather-intent-ratify.md`: a brief path at the first prompt, or a headless `from_brief`), so there is no fresh steps 01-03 output to compile. Use the brief context variables **hydrated from the parsed brief** at step 1 in place of that output: the hydrated variable names match the field references below one-for-one. `detected_version` is absent on this path; rely on the hydrated `version` (step 5 writes from the ratified file, which keeps it).

After a `[R]` pass on a ratify run, take `scope.*`, `scripts_intent`, `assets_intent` and `doc_urls` from step 3, except `scope.amendments`, which step 3 never writes; every other field, `scope.amendments` included, stays hydrated.

### 2. Present Brief for Review

Using the format below:

"**Review the complete skill brief before I write it.**

---

```
Skill Brief: {name}
====================

Target:      {source_repo}
Target ref:  {target_ref; omit this line entirely when target_ref is unset}
Language:    {language}
Forge Tier:  {forge_tier} — {tier_gloss}
Description: {description}

Scope: {scope.type}
  Include: {scope.include patterns, one per line}
  Exclude: {scope.exclude patterns, one per line}
  Notes:   {scope.notes}
  Tier-A:  {scope.tier_a_include patterns, one per line — omit this line entirely if scope.tier_a_include unset}
  Rationale: {chosen} chosen over {recommended} — {reason}
             {omit this line entirely if scope.rationale absent}

{If source_type is "docs-only":}
Source Type: docs-only
Doc URLs:
  {doc_urls, one per line with labels}

{If source_type is "source" AND supplemental doc_urls collected:}
Supplemental Docs:
  {doc_urls, one per line with labels}

Scripts:    {scripts_intent} — {scripts_gloss}
Assets:     {assets_intent} — {assets_gloss}

Source Authority: {source_authority}

{If target_version is set:}
Target Version: {target_version} (user-specified)
Detected Version: {detected_version or "N/A"}
{Else:}
Version:    {version; a derive run's is the detected version, else 1.0.0}

Created:    {created}
Created by: {created_by}
```

---

Glosses (substitute the matching one-liner for `{tier_gloss}`, `{scripts_gloss}`, `{assets_gloss}` above so the user can decode each value at a glance):

- **Forge tier glosses** —
  - `Quick`: text-only extraction; AST and semantic discovery off
  - `Forge`: AST-grep on; semantic and re-ranking off
  - `Forge+`: AST-grep + ccc semantic discovery; re-ranking off
  - `Deep`: full pipeline: AST + ccc + qmd portfolio search + LLM re-ranking

- **`scripts_intent` / `assets_intent` glosses** —
  - `detect`: SKF will scan source for the standard `scripts/`/`bin/`/`tools/`/`cli/` (or `assets/`/`templates/`/`schemas/`/`configs/`) directories during create-skill and decide automatically (when one of the four script folders is a Python package, holding `__init__.py`, only its `__main__.py` and the modules with a shebang or a `__main__` block count as scripts)
  - `none`: no script/asset packaging — create-skill will skip the detection pass
  - free-text (anything else): a description of what to package; create-skill treats it as the user's spec"

### 3. Highlight Items Needing Attention

Flag any fields that may need review:

{If language was overridden or low confidence:}
"**Note:** Language was {auto-detected / manually overridden}."

"**Description:** synthesized in step 1 and accepted there. This is the text agents read when deciding whether to route to your skill: refine it here if you want to tighten it now that the full brief is visible."

{If `tier_source` is `fallback-corrupted-config`:}
"**Note:** Forge tier defaulted to Quick (forge-tier.yaml could not be read)."

{If any scope patterns seem broad or narrow:}
"**Note:** {specific observation about scope breadth}."

{If target_version is set AND detected_version exists AND they differ:}
"**Note:** Target version ({target_version}) differs from detected source version ({detected_version}). The target version will be used for compilation."

"**This is your last chance to make changes before writing the file.**

You can:
- Adjust any field by telling me what to change
- Revise scope boundaries by selecting [R]
- Proceed to write by selecting [C]"

### 4. Handle Inline Adjustments

If the user requests changes to specific fields (name, description, version, etc.):
- If the adjustment requires explaining a field's validation rule or allowed values, load `assets/skill-brief-schema.md` now (otherwise skip the read: the common path does not need it)
- Make the adjustment
- Re-present the updated brief
- Return to the menu

### 5. Present MENU OPTIONS

Display: **Select an Option:** [R] Revise Scope [A] Advanced Elicitation [P] Party Mode [C] Approve and Write [X] Cancel and exit

#### Menu Handling Logic:

- IF R: When `ratify_mode` is true, `source_type` is not `docs-only` and `ratify_analyzed` is not set, load, read entire file, then execute {analyzeStepFile}, which chains to scope definition. Otherwise load, read entire file, then execute {reviseStepFile} to re-enter scope definition
- IF A: Invoke {advancedElicitationSkill}, and when finished redisplay the menu
- IF P: Invoke {partyModeSkill}, and when finished redisplay the menu
- IF C: Load, read entire file, then execute {nextStepFile}
- IF X: Treat as user-cancellation. Remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). Step 5 has not run, so no brief was written; a saved draft stays for a later resume. `[X]` is interactive-only; the headless GATE never reaches this branch.
- IF Any other comments or queries: help user respond, apply any field adjustments, re-present brief if changed, then [Redisplay Menu Options](#5-present-menu-options)

#### Execution rules:

- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Confirm, log: "headless: auto-confirm brief"

