---
nextStepFile: './step-02b-ccc-discover.md'
---

# Step 2: Ecosystem Check

## STEP GOAL:

To search the agentskills.io ecosystem for an existing official skill matching the brief, advise the user if one is found, and allow them to decide whether to proceed with compilation or install the existing skill.

## Rules

- Focus only on ecosystem search and presenting findings — do not begin extraction
- Do not halt the workflow if the ecosystem check fails or times out (5-second timeout)
- If a match is found, present it factually — let the user decide

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Ecosystem for Existing Skill

**Note:** Ecosystem lookup requires the agentskills.io registry API, which is not yet available. The `skill-check` CLI validates local skills but does not query a remote registry.

**If agentskills.io registry API is available:**

Query the ecosystem using the skill name from the brief:
- Call the registry API with brief.name — check if an official skill already exists
- Enforce 5-second timeout — if the query does not return within 5 seconds, treat as no match
- Cache results for 24 hours (if re-running same skill)

**If registry API is NOT available (current default):**

Skip completely and silently. Do not output any message about API unavailability or the ecosystem check being skipped. Emit zero text to the console. Proceed exactly as if no match was found.

### 2. Evaluate Results

**If match found (official skill exists):**

Present the finding to the user:

"**Ecosystem match found.**

**Existing skill:** {matched_skill_name} v{matched_version}
**Source:** {matched_source}
**Authority:** {official/community}
**Compatibility:** {compatibility_notes}

An existing skill already covers this source. You can:
- **[P] Proceed** — compile your own version anyway (useful for customization or different scope)
- **[I] Install** — install the existing skill instead of compiling
- **[A] Abort** — cancel this compilation"

**If no match found:**

Auto-proceed silently to next step. Do not display any message about the ecosystem check — absence of a match is the expected case.

**If timeout or error:**

Auto-proceed silently. Log a note in context: "Ecosystem check skipped (timeout/error) — proceeding with compilation."

### 3. Menu Handling Logic

**Conditional menu — only displayed if a match was found.**

#### If Match Found — Present MENU OPTIONS:

Display: "**Ecosystem match found — Select an Option:** [P] Proceed with compilation [I] Install existing [A] Abort"

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: P]** — If `{headless_mode}` and match found: auto-proceed with [P] Proceed, log: "headless: ecosystem match found, auto-proceeding"
- This menu ONLY appears when an ecosystem match is found
- If no match, timeout, or tool unavailable — auto-proceed with no menu

#### Menu Handling Logic:

- IF P: Note user's decision to proceed despite existing skill. Immediately load, read entire file, then execute `{nextStepFile}`
- IF I: Display: "Install the existing skill using: `[SF] Setup Forge → install {matched_skill_name}`" then halt workflow. Do not proceed to extraction.
- IF A: Display: "Compilation aborted. Return to Ferris menu to select another action." then halt workflow.
- IF no match/timeout/error: Auto-proceed — immediately load, read entire file, then execute `{nextStepFile}`
- IF Any other comments or queries: help user respond then redisplay the menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the ecosystem check is complete (match evaluated, user decision made if applicable) will you proceed to load `{nextStepFile}` for source extraction.

If no match is found, this step auto-proceeds with no user interaction.

