---
nextStepFile: './step-02b-ccc-discover.md'
---

# Step 2: Ecosystem Check

## STEP GOAL:

To search the agentskills.io ecosystem for an existing official skill matching the brief, advise the user if one is found, and allow them to decide whether to proceed with compilation or install the existing skill.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing ecosystem discovery
- ✅ This step is advisory — ecosystem check results never block compilation
- ✅ Tool unavailability is never an error — it's a graceful skip condition

### Step-Specific Rules:

- 🎯 Focus ONLY on ecosystem search and presenting findings
- 🚫 FORBIDDEN to begin any extraction or compilation work
- 🚫 FORBIDDEN to halt the workflow if the ecosystem check fails or times out
- 💬 If a match is found, present it factually — let the user decide
- ⏱️ Enforce 5-second timeout on ecosystem queries

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 All loaded data remains in context for subsequent steps
- 📖 Ecosystem check is advisory — never blocking
- 🚫 Do not modify any files — this step only queries and reports

## CONTEXT BOUNDARIES:

- Available: brief_data (name, version, source_repo, language, scope) and tier from step-01
- Focus: Searching for existing skills in the ecosystem
- Limits: Do NOT begin extraction, compilation, or file writing
- Dependencies: skill-brief.yaml must be loaded and validated from step-01

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Ecosystem check attempted via registry API (or gracefully skipped if API unavailable)
- 5-second timeout enforced on ecosystem queries
- Match presented factually with clear options if found
- No-match case auto-proceeds silently
- User decision respected (Proceed/Install/Abort)
- Auto-proceeded to step-02b (when no match or user chose Proceed)

### ❌ SYSTEM FAILURE:

- Halting the workflow because ecosystem check failed or timed out
- Treating API unavailability as an error
- Confusing `npx skill-check check` (local validation) with ecosystem lookup
- Displaying "no match found" messages (absence should be silent)
- Beginning extraction or compilation work in this step
- Proceeding without user decision when a match IS found
- Not enforcing the 5-second timeout

**Master Rule:** This step is advisory. API unavailability and timeouts are silent skips, not errors. Only a confirmed match requires user interaction.
