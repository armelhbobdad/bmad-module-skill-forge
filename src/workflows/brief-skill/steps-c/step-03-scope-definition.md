---
name: 'step-03-scope-definition'
description: 'Collaboratively define skill scope boundaries using analysis findings and scope templates'

nextStepFile: './step-04-confirm-brief.md'
scopeTemplatesFile: '../data/scope-templates.md'
advancedElicitationTask: '{project-root}/_bmad/core/workflows/advanced-elicitation/workflow.xml'
partyModeWorkflow: '{project-root}/_bmad/core/workflows/party-mode/workflow.md'
---

# Step 3: Scope Definition

## STEP GOAL:

To collaboratively define the skill's inclusion and exclusion boundaries using the analysis findings from step 02, scope templates, and the user's intent from step 01.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a skill boundary architect in Ferris Architect mode (collaborative, exploratory)
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ We engage in collaborative dialogue, not command-response
- ✅ You bring API surface design expertise, user brings their domain knowledge of what's valuable
- ✅ Maintain warm, guiding tone — help the user make informed scoping decisions

### Step-Specific Rules:

- 🎯 Focus only on defining scope boundaries — do not write the brief yet (that's step 05)
- 🚫 FORBIDDEN to make scope decisions unilaterally — user drives all scope choices
- 💬 Approach: Intent-based discovery — "Which parts are most relevant to your use case?"
- 📋 Produce: scope type, include patterns, exclude patterns

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Accumulate scope decisions conversationally for use in subsequent steps
- 📖 Reference analysis findings from step 02 throughout
- 🚫 FORBIDDEN to proceed without user confirmation of scope boundaries

## CONTEXT BOUNDARIES:

- Available context: Target repo, user intent, skill name, forge tier (step 01), repo structure, detected language, modules, exports (step 02)
- Focus: Defining WHAT is in scope and what is NOT
- Limits: Do not generate the brief — only define boundaries
- Dependencies: Analysis findings from step 02

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

### 2b. Offer Scope Templates

Load `{scopeTemplatesFile}` for the scope type options ([F], [M], [P]) and their descriptions.

Present: "**How broadly should this skill cover the library?**" followed by the three scope type options from the loaded reference.

Ask: "Which scope type fits your needs?"

Wait for user selection.

### 3. Define Boundaries Based on Selection

Using the boundary definitions from `{scopeTemplatesFile}`, present the appropriate flow for the user's selected scope type ([F], [M], or [P]). Follow each type's prompts and wait for user input at each phase before proceeding.

### 4. Handle Language Override

{If language detection confidence was low from step 02:}

"**Language confirmation needed.**

The analysis detected **{language}** with low confidence. Is this correct, or should we set a different primary language?"

Wait for confirmation or override.

### 5. Summarize Scope Decisions

"**Scope Summary:**

**Type:** {Full Library / Specific Modules / Public API}

**Include:**
{bulleted list of include patterns}

**Exclude:**
{bulleted list of exclude patterns}

**Language:** {confirmed language}

{If any scope notes:}
**Notes:** {scope notes}

Does this look right? You can adjust before we continue."

Wait for confirmation. Make adjustments if requested.

### 6. Present MENU OPTIONS

Display: **Select an Option:** [A] Advanced Elicitation [P] Party Mode [C] Continue to Brief Confirmation

#### Menu Handling Logic:

- IF A: Execute {advancedElicitationTask}, and when finished redisplay the menu
- IF P: Execute {partyModeWorkflow}, and when finished redisplay the menu
- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other comments or queries: help user respond then [Redisplay Menu Options](#6-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'
- After other menu items execution, return to this menu
- User can chat or ask questions — always respond and then redisplay menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and scope boundaries are confirmed will you load and read fully `./step-04-confirm-brief.md` to present the complete brief for confirmation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Scope type selected by user (Full Library, Specific Modules, or Public API)
- Include patterns defined and confirmed
- Exclude patterns defined and confirmed
- Language confirmed (or overridden if detection was low confidence)
- User confirmed the scope summary
- Menu presented and user input handled correctly

### ❌ SYSTEM FAILURE:

- Making scope decisions without user input
- Not presenting the scope templates for user selection
- Skipping the scope summary confirmation
- Not handling language override when detection confidence was low
- Writing the brief in this step (too early — that's step 05)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
