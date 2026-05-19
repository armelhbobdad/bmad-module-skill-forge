---
nextStepFile: 'confirm-brief.md'
scopeTemplatesFile: 'assets/scope-templates.md'
recommendScopeTypeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-recommend-scope-type.py'
  - '{project-root}/src/shared/scripts/skf-recommend-scope-type.py'
advancedElicitationSkill: '/bmad-advanced-elicitation'
partyModeSkill: '/bmad-party-mode'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Scope Definition

## STEP GOAL:

To collaboratively define the skill's inclusion and exclusion boundaries using the analysis findings from step 02, scope templates, and the user's intent from step 01.

## Rules

- Focus only on defining scope boundaries — do not write the brief yet (Step 05)
- Do not make scope decisions unilaterally — user drives all scope choices
- Produce: scope type, include patterns, exclude patterns
- All user-facing output in `{communication_language}`
- **Re-entry from step 4 [R] revise:** prior selections (`scope.type`, `scope.include`, `scope.exclude`, `scope.notes`, `scope.rationale`, `scripts_intent`, `assets_intent`, supplemental `doc_urls`) are preserved as the current state. Re-present them at each section as the existing answer; the user only re-confirms or overrides. Do not reset to the §2c template menu unless the user explicitly asks to start scope over. When `scope.rationale` is preserved and the user changes `chosen` (the scope type) on this pass, recompute `accepted_recommendation` (`chosen == recommended`) and refresh `reason` and `recorded` per the §2c capture rules — revise in place, do not append.

## MANDATORY SEQUENCE

### 1. Present Scope Context

"**Let's define the scope for your skill.**

Based on the analysis, here's what we're working with:

- **Target:** {repo}
- **Language:** {detected language}
- **Modules found:** {count} — {list names}
- **Your intent:** {user intent from step 01}
{If scope hints from step 01:}
- **Your initial scope hints:** {hints}"

### 2. Handle Docs-Only Mode (if applicable)

**If `source_type: "docs-only"`:**

"**Docs-only mode — scope is defined by documentation pages.**

You've provided these documentation URLs:
{numbered list of doc_urls with labels}

Which pages should be included in the skill? (Enter numbers, or 'all')
Any additional documentation URLs to add?"

Wait for confirmation. Then skip to section 5 (Summarize Scope Decisions) with:
- `scope.type: "docs-only"`
- `scope.include`: confirmed doc URLs
- `scope.notes: "Generated from external documentation. All content is T3 confidence."`

**If `source_type: "source"` (default):** Continue to scope templates below.

### 2b. Confirm Supplemental Documentation (if doc_urls collected)

**If `source_type: "source"` AND supplemental `doc_urls` were collected in step 01:**

"**Supplemental documentation URLs:**
{numbered list of collected doc_urls with labels}

These will be included as T3 external references in the skill brief.
Add, remove, or confirm these URLs."

Wait for confirmation. Record any changes to `doc_urls`.

HEAD-check the URLs in parallel — issue all N `curl -sI --max-time 5 {url}` calls in a **single message with N parallel Bash calls**, then process the responses together. On a 4xx/5xx, DNS failure, or timeout per URL, warn `"Could not reach {url} — {status or error}."` and offer the same correct/keep choice as step 1 §3. The check is best-effort — never HALT on a failed HEAD — but the failure must surface here so it is not discovered downstream during compilation.

**On re-entry from step 4 [R]:** if `doc_urls` is byte-identical to the list that was probed on the previous pass through this subsection AND the prior per-URL probe results are still recoverable from conversation context, skip the parallel HEAD-check and reuse those results. Re-running the probes when the list has not changed wastes round-trips and can flap on transient failures. Any addition, removal, or edit to a URL invalidates the cache — re-probe the entire updated set. If the prior results are not recoverable (long session, compaction, etc.), re-probe — never cache-hit on a list whose results you cannot cite.

**If no supplemental doc_urls were collected:** Skip this subsection.

**Scope guidance for first-time users:** A well-scoped skill covers one cohesive capability with 3-8 primary functions. If the scope includes unrelated concerns (e.g., authentication AND data visualization), suggest splitting into separate briefs. If the scope is too narrow (single utility function), suggest expanding to the surrounding capability surface.

### 2c. Offer Scope Templates

Load `{scopeTemplatesPath}` for the scope type options ([F], [M], [P], [C], [R]) and their descriptions.

**Recommend a scope type — don't present the five options as equal weight.** SKILL.md states this workflow "steers toward the smaller, sharper version when scope is unclear" — surface that opinion at decision time. Use the analysis from step 2 and the user's intent from step 1 to pick the best-fit recommendation, then present the menu with that option marked as the suggested default.

**Resolve `{recommendScopeTypeHelper}`** from `{recommendScopeTypeProbeOrder}`; first existing path wins. HALT if no candidate exists.

**Delegate the recommendation to `{recommendScopeTypeHelper}`** instead of walking the heuristic ladder in prose. The script is the single source of truth for the five-rule ladder (component-registry → reference-app keywords → specific-modules naming/count → narrow-public-api → default full-library) plus the docs-only short-circuit. Both the interactive recommendation and the §6 headless GATE invoke the same script — same inputs, same outputs, no drift.

**Fetch registry-file contents before building the payload.** Step-02 §4.1 fetches `package.json` plus the entry-point files but does not fetch `registry.ts` / `components.ts` — the deep-match branch of the component-registry rule needs those contents. Scan the tree for any of `registry.ts` / `registry.tsx` / `components.ts` / `components.tsx` (any depth). For each match, fetch its contents in **one message with N parallel Bash calls** (`gh api repos/{owner}/{repo}/contents/{path}` for GitHub, file reads for local), then base64-decode the responses together. Skip the fetch if the tree contains no registry files.

Build the payload and invoke:

```bash
echo '{
  "intent": "<combined intent + scope_hint text from step 1>",
  "module_count": <count from step 2 §4.3>,
  "export_count": <count from step 2 §4.3>,
  "tree": [<flat list of repo-relative file paths from step 2 §1>],
  "entry_files": [{"path": "<registry path>", "content": "<contents>"}, ...],
  "source_type": "source",
  "mode": "interactive"
}' | uv run {recommendScopeTypeHelper}
```

`entry_files` carries the registry contents fetched above; omit when no registry files exist in the tree. `mode: "interactive"` activates the content-inspection branch of the component-registry rule (10+ entries or `Component[]` annotation); the headless GATE in §6 uses `mode: "headless"` which falls back to presence-only matching. `source_type: "docs-only"` short-circuits to `docs-only` regardless of the other signals.

The script returns `{scope_type, matched_heuristic, signals, rationale}`. Use `rationale` directly — it already names the specific signals that fired.

**Persist the rationale — do not discard it.** Hold `scope_type` as `rationale.recommended` and `matched_heuristic` as `rationale.heuristic` in conversation state. After the user's §2c selection: if they accept the recommendation, set `rationale.chosen = recommended`, `accepted_recommendation = true`, `reason = <script rationale verbatim>`. If they override, set `chosen = <selected type>`, `accepted_recommendation = false`, and ask one line — *"In a sentence, why {chosen} over the recommended {recommended}?"* — storing the answer as `reason` (or `"user overrode {recommended}->{chosen}; reason not stated"` if skipped). Set `recorded = {current ISO date}`. This object becomes `scope.rationale`.

Present:

"**Recommended scope type: [{letter}] {Name}** — {rationale from the script}.

How broadly should this skill cover the library?

{full menu from `{scopeTemplatesPath}` with the recommended letter marked, e.g. '[F] Full Library', '[M] Specific Modules', '[P] Public API Only ← recommended', '[C] Component Library', '[R] Reference App'}

Press Enter to accept the recommendation, or pick a different letter."

Wait for user selection. Empty input or just Enter accepts the recommendation; any of the five letters overrides.

### 3. Define Boundaries Based on Selection

Using the boundary definitions from `{scopeTemplatesPath}`, present the appropriate flow for the user's selected scope type ([F], [M], [P], [C], or [R]). Follow each type's prompts and wait for user input at each phase before proceeding.

### 4. Handle Language Override

{If language detection confidence was low from step 02:}

"**Language confirmation needed.**

The analysis detected **{language}** with low confidence. Is this correct, or should we set a different primary language?"

Wait for confirmation or override.

### 5. Summarize Scope Decisions

"**Scope Summary:**

**Type:** {Full Library / Specific Modules / Public API / Component Library / Reference App}

**Include:**
{bulleted list of include patterns}

**Exclude:**
{bulleted list of exclude patterns}

**Language:** {confirmed language}

{If any scope notes:}
**Notes:** {scope notes}

Does this look right? You can adjust before we continue."

Wait for confirmation. Make adjustments if requested.

### 5b. Scripts & Assets Intent (Optional)

**Only ask when `scope.type` is `full-library`, `specific-modules`, `component-library`, or `reference-app` (skip for `public-api` and `docs-only`). Reference apps routinely ship wiring scripts and build-config assets — prompt for them.**

"Does this library include executable scripts (CLI tools, validation scripts, setup helpers) or static assets (config templates, JSON schemas, example configs) that should be packaged with the skill?"

- **[D] Auto-detect** from source (default) — SKF will scan for `scripts/`, `bin/`, `assets/`, `templates/`, `schemas/` directories
- **[N] None expected** — skip script/asset detection
- Or describe what you expect (free text)

Record the response as `scripts_intent` and `assets_intent` in the brief. Default to `detect` if user does not respond or skips.

### 6. Present MENU OPTIONS

Display: **Select an Option:** [A] Advanced Elicitation [P] Party Mode [C] Continue to Brief Confirmation [X] Cancel and exit

#### Menu Handling Logic:

- IF A: Invoke {advancedElicitationSkill}, and when finished redisplay the menu
- IF P: Invoke {partyModeSkill}, and when finished redisplay the menu
- IF C: Load, read entire file, then execute {nextStepFile}
- IF X: Treat as user-cancellation. Display `"Cancelled — no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). Cancellation here is non-destructive — no files have been written yet. `[X]` is interactive-only; the headless GATE never reaches this branch.
- IF Any other comments or queries: help user respond then [Redisplay Menu Options](#6-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: consume the headless inputs from step 1 in priority order:
  - If `scope_type` was supplied, use it (must match one of the six valid types) and skip the §2c template menu.
  - Otherwise auto-select via `{recommendScopeTypeHelper}` — invoke the script with the **same payload shape** documented in §2c but with `mode: "headless"` (presence-only matching for the component-registry rule, since `entry_files` may not be available without an interactive context). Use the returned `scope_type` and log `"headless: scope_type={value} from heuristic={matched_heuristic}"`. The script's docs-only short-circuit handles `source_type=docs-only` automatically.
  - If `include`/`exclude` were supplied, use them verbatim (split on comma) instead of running the boundary prompts in §3.
  - If `scripts_intent`/`assets_intent` were supplied, record them and skip §5b; otherwise default to `detect`.
  - Set `scope.rationale`: `recommended`/`heuristic` from the script (or `recommended = scope_type` arg, `heuristic = "user-supplied-arg"` when `scope_type` was passed); `chosen = <resolved type>`; `accepted_recommendation = (no scope_type arg)`; `reason = "<script rationale>"` (auto path) or `"headless: scope_type supplied as argument"` (arg path); `recorded = {date}`. No prompt — headless never asks "why".
  - Log: `"headless: scope_type={value} include={n} exclude={n} scripts_intent={value} assets_intent={value}"`.
- ONLY proceed to next step when user selects 'C'
- After other menu items execution, return to this menu
- User can chat or ask questions — always respond and then redisplay menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and scope boundaries are confirmed will you load and read fully `confirm-brief.md` to present the complete brief for confirmation.

