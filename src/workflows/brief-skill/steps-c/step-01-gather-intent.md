---
name: 'step-01-gather-intent'
description: 'Initialize brief-skill workflow, discover forge tier, and gather user intent for skill creation'

nextStepFile: './step-02-analyze-target.md'
forgeTierFile: '{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml'
---

# Step 1: Gather Intent

## STEP GOAL:

To initialize the brief-skill workflow by discovering the forge tier configuration, then gathering the user's target repository, intent, and any upfront scope hints for skill creation.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a skill scoping architect in Ferris Architect mode (exploratory, collaborative)
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ We engage in collaborative dialogue, not command-response
- ✅ You bring source code analysis and skill design expertise, user brings their domain knowledge and use case
- ✅ Maintain a warm, guiding tone — this is a discovery conversation

### Step-Specific Rules:

- 🎯 Focus only on gathering intent — do not analyze the repo yet (that's step 02)
- 🚫 FORBIDDEN to examine source code or list exports in this step
- 💬 Approach: Open-ended discovery facilitation — "What interests you about this library?"
- 📋 Collect: target repo, user intent, scope hints, skill name

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Accumulate gathered information conversationally for use in subsequent steps
- 📖 This is the init step — sets up everything that follows
- 🚫 FORBIDDEN to proceed without a confirmed target repository

## CONTEXT BOUNDARIES:

- Available context: Module config (forge_data_folder, user_name), forge-tier.yaml (if available)
- Focus: Understanding WHAT the user wants to skill and WHY
- Limits: Do not analyze source code, detect language, or list exports — that's step 02
- Dependencies: None — this is the first step

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Discover Forge Tier

Attempt to load `{forgeTierFile}`:

**If found:**
- Read the tier level (quick, forge, or deep)
- Note available tools for scoping guidance later

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, or Deep), use it instead of the detected tier.

**If not found:**
- Display: "**Note:** No forge tier configuration found. Defaulting to Quick tier. Run **setup-forge** first for full capabilities."
- Default to: `forge_tier: quick`

### 2. Welcome and Explain

"**Welcome to Brief Skill — the skill scoping workflow.**

I'll help you define exactly what to skill and produce a `skill-brief.yaml` that drives the create-skill compilation workflow.

We'll work through this together:
1. **Now:** Understand what you want to skill and why
2. **Next:** Analyze the target repo structure
3. **Then:** Define scope boundaries
4. **Finally:** Confirm and write the brief

**Your forge tier:** {detected tier} — this determines what compilation capabilities are available.

Let's get started."

### 3. Gather Target Repository

"**What repository or documentation do you want to create a skill for?**

Provide one of:
- A **GitHub URL** (e.g., `https://github.com/org/repo`)
- A **local path** (e.g., `/path/to/project`)
- **Documentation URLs** for a docs-only skill (e.g., `https://docs.cognee.ai/`) — use this when no source code is available (SaaS, closed-source)

**Target:**"

Wait for user response.

**If user provides documentation URLs (not a repo):**
- Set `source_type: "docs-only"` in the brief data
- Collect one or more doc URLs with optional labels
- Note: `source_authority` will be forced to `community` (T3 external documentation)
- Note: `source_repo` becomes optional (can be set to the main doc site URL for reference)

**If user provides a GitHub URL or local path:**
- Set `source_type: "source"` (default)
- Optionally ask: "Are there any documentation URLs you'd like to include for supplemental context? (These will be fetched as T3 external references.)"
- If yes: collect doc URLs into `doc_urls`

Confirm the target.

### 4. Gather User Intent

"**What's your intent for this skill?**

Help me understand:
- **What** specifically do you want to skill from this repo?
- **Why** — what's the use case? How will an AI agent use this skill?
- **Any initial thoughts** on scope? (Full library? Specific modules? Public API only?)

Take your time — the more context you share, the better the brief."

Wait for user response. Ask follow-up questions if intent is unclear.

### 5. Capture Scope Hints

If the user mentioned scope preferences in their intent response, acknowledge them:

"**I noted these scope hints from your response:**
- {list any scope hints mentioned}

We'll refine these after analyzing the repo structure in the next step."

If no scope hints were mentioned, that's fine — skip this acknowledgment.

### 6. Derive Skill Name

Based on the target repo and intent, propose a skill name:

"**Suggested skill name:** `{derived-name}` (kebab-case)

This will be used for the output directory and file naming. Want to use this name or suggest something different?"

Wait for confirmation or alternative.

### 7. Summarize Gathered Intent

"**Here's what I've captured:**

- **Target:** {repo URL or path}
- **Intent:** {user's intent summary}
- **Scope hints:** {any hints, or "None — we'll define scope after analysis"}
- **Skill name:** {confirmed name}
- **Forge tier:** {tier}

Ready to analyze the target repository?"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Target Analysis"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: Help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and target repository is confirmed will you load and read fully `./step-02-analyze-target.md` to execute target analysis.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Forge tier discovered (or defaulted to Quick with warning), override applied if set in preferences.yaml
- Target repository confirmed (GitHub URL or local path)
- User intent captured with enough context for scoping
- Skill name derived and confirmed
- Scope hints noted (if provided)
- User ready to proceed to analysis

### ❌ SYSTEM FAILURE:

- Analyzing source code in this step (too early)
- Proceeding without a confirmed target repository
- Not attempting to discover forge tier
- Generating a skill name without user confirmation
- Skipping the intent gathering conversation

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
