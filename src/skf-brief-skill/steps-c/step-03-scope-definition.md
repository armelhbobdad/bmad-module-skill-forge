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

**If no supplemental doc_urls were collected:** Skip this subsection.

**Scope guidance for first-time users:** A well-scoped skill covers one cohesive capability with 3-8 primary functions. If the scope includes unrelated concerns (e.g., authentication AND data visualization), suggest splitting into separate briefs. If the scope is too narrow (single utility function), suggest expanding to the surrounding capability surface.

### 2c. Offer Scope Templates

Load `{scopeTemplatesFile}` for the scope type options ([F], [M], [P], [C]) and their descriptions.

Present: "**How broadly should this skill cover the library?**" followed by the scope type options from the loaded reference.

Ask: "Which scope type fits your needs?"

Wait for user selection.

### 3. Define Boundaries Based on Selection

Using the boundary definitions from `{scopeTemplatesFile}`, present the appropriate flow for the user's selected scope type ([F], [M], [P], or [C]). Follow each type's prompts and wait for user input at each phase before proceeding.

### 4. Handle Language Override

{If language detection confidence was low from step 02:}

"**Language confirmation needed.**

The analysis detected **{language}** with low confidence. Is this correct, or should we set a different primary language?"

Wait for confirmation or override.

### 5. Summarize Scope Decisions

"**Scope Summary:**

**Type:** {Full Library / Specific Modules / Public API / Component Library}

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

**Only ask when `scope.type` is `full-library`, `specific-modules`, or `component-library` (skip for `public-api` and `docs-only`).**

"Does this library include executable scripts (CLI tools, validation scripts, setup helpers) or static assets (config templates, JSON schemas, example configs) that should be packaged with the skill?"

- **[D] Auto-detect** from source (default) — SKF will scan for `scripts/`, `bin/`, `assets/`, `templates/`, `schemas/` directories
- **[N] None expected** — skip script/asset detection
- Or describe what you expect (free text)

Record the response as `scripts_intent` and `assets_intent` in the brief. Default to `detect` if user does not respond or skips.

### 6. Present MENU OPTIONS

Display: **Select an Option:** [A] Advanced Elicitation [P] Party Mode [C] Continue to Brief Confirmation

#### Menu Handling Logic:

- IF A: Invoke {advancedElicitationSkill}, and when finished redisplay the menu
- IF P: Invoke {partyModeSkill}, and when finished redisplay the menu
- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other comments or queries: help user respond then [Redisplay Menu Options](#6-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: accept auto-detected scope (full-repo or manifest-based) and auto-proceed, log: "headless: using auto-detected scope"
- ONLY proceed to next step when user selects 'C'
- After other menu items execution, return to this menu
- User can chat or ask questions — always respond and then redisplay menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and scope boundaries are confirmed will you load and read fully `./step-04-confirm-brief.md` to present the complete brief for confirmation.

