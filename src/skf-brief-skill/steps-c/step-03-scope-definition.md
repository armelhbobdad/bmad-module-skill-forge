---
nextStepFile: './step-04-confirm-brief.md'
scopeTemplatesFile: 'assets/scope-templates.md'
advancedElicitationSkill: '/bmad-advanced-elicitation'
partyModeSkill: '/bmad-party-mode'
---

# Step 3: Scope Definition

## STEP GOAL:

To collaboratively define the skill's inclusion and exclusion boundaries using the analysis findings from step 02, scope templates, and the user's intent from step 01.

## Rules

- Focus only on defining scope boundaries — do not write the brief yet (Step 05)
- Do not make scope decisions unilaterally — user drives all scope choices
- Produce: scope type, include patterns, exclude patterns
- All user-facing output in `{communication_language}`
- **Re-entry from step-04 [R] revise:** prior selections (`scope.type`, `scope.include`, `scope.exclude`, `scope.notes`, `scripts_intent`, `assets_intent`, supplemental `doc_urls`) are preserved as the current state. Re-present them at each section as the existing answer; the user only re-confirms or overrides. Do not reset to the §2c template menu unless the user explicitly asks to start scope over.

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

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

HEAD-check the URLs in parallel — issue all N `curl -sI --max-time 5 {url}` calls in a **single message with N parallel Bash calls**, then process the responses together. On a 4xx/5xx, DNS failure, or timeout per URL, warn `"Could not reach {url} — {status or error}."` and offer the same correct/keep choice as step-01 §3. The check is best-effort — never HALT on a failed HEAD — but the failure must surface here so it is not discovered downstream during compilation.

**If no supplemental doc_urls were collected:** Skip this subsection.

**Scope guidance for first-time users:** A well-scoped skill covers one cohesive capability with 3-8 primary functions. If the scope includes unrelated concerns (e.g., authentication AND data visualization), suggest splitting into separate briefs. If the scope is too narrow (single utility function), suggest expanding to the surrounding capability surface.

### 2c. Offer Scope Templates

Load `{scopeTemplatesFile}` for the scope type options ([F], [M], [P], [C], [R]) and their descriptions.

**Recommend a scope type — don't present the five options as equal weight.** SKILL.md states this workflow "steers toward the smaller, sharper version when scope is unclear" — surface that opinion at decision time. Use the analysis from step-02 and the user's intent from step-01 to pick the best-fit recommendation, then present the menu with that option marked as the suggested default.

Heuristics for the recommendation (apply in order, pick the first that matches):

- **Component registry detected** (file matching `registry.ts` / `components.ts` with 10+ entries, or `Component[]` type annotation) → **[C] Component Library**
- **User intent mentions "wiring", "integration example", "starter", "lifecycle", "build config"** OR the analysis identified the source as an example/demo app → **[R] Reference App**
- **Intent names specific module(s)** (e.g. "just the auth module", "only the streaming part") OR the analysis surfaced a large library (≥6 top-level modules with weakly-related concerns) → **[M] Specific Modules**
- **Library has a clear, narrow public API** (≤8 named exports from the manifest, intent points at "the API" / "the SDK") → **[P] Public API Only**
- **Otherwise** (small focused library, intent says "everything", or no strong signal either way) → **[F] Full Library**

Present:

"**Recommended scope type: [{letter}] {Name}** — {one-sentence rationale tying the recommendation to a specific signal from step-01/02, e.g. 'because the analysis found a 47-entry component registry under src/components/registry.ts'}.

How broadly should this skill cover the library?

{full menu from `{scopeTemplatesFile}` with the recommended letter marked, e.g. '[F] Full Library', '[M] Specific Modules', '[P] Public API Only ← recommended', '[C] Component Library', '[R] Reference App'}

Press Enter to accept the recommendation, or pick a different letter."

Wait for user selection. Empty input or just Enter accepts the recommendation; any of the five letters overrides.

**Headless:** if `scope_type` was supplied, use it (consumed at the GATE in §6). If not supplied, run the same five heuristics above against the data already gathered (intent text + scope_hint from step-01, module count + exports + file paths from step-02) and use the first matching recommendation as the scope_type. Log `"headless: scope_type auto-selected as {value} from {heuristic-name}"` so the choice is debuggable.

For the **component-registry** heuristic, the entry-count threshold (`10+ entries`) and `Component[]` type-annotation check require file *contents* — those are only available when step-02 §4.1 included `registry.ts` / `components.ts` as an entry point in the script payload (rare for the public-API mode), or when the target is a local path. In headless mode without that visibility, treat **the presence of `registry.ts` or `components.ts` anywhere in the file tree** as a sufficient match for the component-library recommendation — content inspection is interactive-only.

The `docs-only` short-circuit still applies when `source_type=docs-only` (heuristic ranking is skipped — there is no source surface to scope). When no heuristic matches, fall back to `full-library` and log `"headless: scope_type defaulted to full-library — no signal matched"`.

### 3. Define Boundaries Based on Selection

Using the boundary definitions from `{scopeTemplatesFile}`, present the appropriate flow for the user's selected scope type ([F], [M], [P], [C], or [R]). Follow each type's prompts and wait for user input at each phase before proceeding.

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
- **GATE [default: C]** — If `{headless_mode}`: consume the headless inputs from step-01 in priority order:
  - If `scope_type` was supplied, use it (must match one of the six valid types) and skip the §2c template menu.
  - Otherwise auto-select: `source_type=docs-only` → `scope.type: "docs-only"`; `source_type=source` → run the §2c heuristic-driven recommendation (component-registry / reference-app keywords / specific-modules / public-api / full-library) against the step-01/02 signals and use the first match. Falls back to `full-library` only when no heuristic matches.
  - If `include`/`exclude` were supplied, use them verbatim (split on comma) instead of running the boundary prompts in §3.
  - If `scripts_intent`/`assets_intent` were supplied, record them and skip §5b; otherwise default to `detect`.
  - Log: `"headless: scope_type={value} include={n} exclude={n} scripts_intent={value} assets_intent={value}"`.
- ONLY proceed to next step when user selects 'C'
- After other menu items execution, return to this menu
- User can chat or ask questions — always respond and then redisplay menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and scope boundaries are confirmed will you load and read fully `./step-04-confirm-brief.md` to present the complete brief for confirmation.

