---
nextStepFile: './step-03-quick-extract.md'
---

# Step 2: Ecosystem Check

## STEP GOAL:

To query the agentskills.io ecosystem for an existing official skill matching the resolved target, preventing unnecessary duplication. This is an advisory gate — it never blocks the workflow on failure.

## Rules

- This check is advisory — never block the workflow on failure
- 5-second timeout on ecosystem queries; tool unavailability is a silent skip, not an error
- Do not begin extraction or compilation

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Query Ecosystem

Search for an existing official skill matching `{repo_name}` in the agentskills.io ecosystem.

**Query methods (try in order):**
1. Search agentskills.io registry for `{repo_name}`
2. Web search: `"agentskills.io" "{repo_name}" skill`

**Apply 5-second timeout.** If query takes longer, treat as no-match.

### 2. Evaluate Result

**If tool unavailable or timeout:**
- Set `ecosystem_status: skip`
- Proceed silently to step 3 (auto-proceed, no message to user)

**If no match found:**
- Set `ecosystem_status: no-match`
- Auto-proceed silently to step 3. Do not display any message — absence of a match is the expected case.

**If match found:**
- Set `ecosystem_status: match`
- Display match details and present conditional menu:

"**Existing official skill found for {repo_name}.**

**Skill:** {matched_skill_name}
**Source:** agentskills.io
**Authority:** official

An official skill already exists. You can:

**[P] Proceed** — Compile a custom community skill anyway (different scope or customization)
**[I] Install** — Install the existing official skill instead (exits this workflow)
**[A] Abort** — Cancel compilation"

### 3. Handle Match Menu (ONLY if match found)

#### Menu Handling Logic:

- IF P: Set `ecosystem_status: match-proceed`, then load, read entire file, then execute {nextStepFile}
- IF I: Display install instructions for the official skill, then end workflow
- IF A: Display "Compilation cancelled." and end workflow
- IF Any other: help user, then redisplay the match menu

#### EXECUTION RULES:

- ONLY display this menu when ecosystem_status is match
- ALWAYS halt and wait for user input when match is found
- **GATE [default: P]** — If `{headless_mode}` and match found: auto-proceed with [P] Proceed (compile custom skill anyway), log: "headless: ecosystem match found, auto-proceeding with custom compilation"
- For no-match and skip cases, auto-proceed without menu

### 4. Auto-Proceed (No Match or Skip)

#### Menu Handling Logic:

- After no-match or skip determination, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed path — no user interaction needed
- Proceed directly to extraction step

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN ecosystem check completes (match with user choice, no-match, or skip) will you load and read fully `{nextStepFile}` to execute source extraction.

