---
nextStepFile: './step-02-analyze-target.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
---

# Step 1: Gather Intent

## STEP GOAL:

To initialize the brief-skill workflow by discovering the forge tier configuration, then gathering the user's target repository, intent, and any upfront scope hints for skill creation.

## Rules

- Focus only on gathering intent — do not analyze the repo yet (Step 02)
- Do not examine source code or list exports in this step
- Open-ended discovery facilitation — collect target repo, user intent, scope hints, skill name

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Discover Forge Tier

Attempt to load `{forgeTierFile}`:

**If found:**
- Read the tier level (quick, forge, forge+, or deep)
- Note available tools for scoping guidance later

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

**If not found:**
- "**Cannot proceed.** forge-tier.yaml not found at `{forgeTierFile}`. Please run the **setup** workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."
- HALT — do not proceed.

### 2. Welcome and Explain

"**Welcome to Brief Skill — the skill scoping workflow.**

I'll help you define exactly what to skill and produce a `skill-brief.yaml` that drives the create-skill compilation workflow.

We'll work through this together:
1. **Now:** Understand what you want to skill and why
2. **Next:** Analyze the target repo structure
3. **Then:** Define scope boundaries
4. **Finally:** Confirm and write the brief

{If tier override was applied:}
**Your forge tier:** {override tier} (overridden from {original tier}) — this determines what compilation capabilities are available.
{Else:}
**Your forge tier:** {detected tier} — this determines what compilation capabilities are available.

Let's get started."

### 3. Gather Target Repository

"**What repository or documentation do you want to create a skill for?**

Provide one of:
- A **GitHub URL** (e.g., `https://github.com/org/repo`)
- A **local path** (e.g., `/path/to/project`)
- **Documentation URLs** for a docs-only skill (e.g., `https://docs.stripe.com/api`) — use this when no source code is available (SaaS, closed-source)

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

**Source authority (for all source-type skills):**
"**Are you the maintainer of this library, or creating a community skill?**"
- If maintainer: set `source_authority: "official"`
- If community user: set `source_authority: "community"` (default)
- If internal/proprietary: set `source_authority: "internal"`

Default to `"community"` if user does not specify or skips. For `docs-only` skills, `source_authority` is always forced to `"community"`.

Confirm the target.

### 3b. Gather Target Version

"**Are you targeting a specific version of this library?**
(Leave blank to auto-detect from source)"

{If source_type is "docs-only":}
"Since this is a docs-only skill with no source code, specifying the version is recommended — otherwise it defaults to 1.0.0."

Wait for user response.

**If user provides a version:** Store as `target_version`. Set `version` to this value.
**If blank:** Proceed without `target_version` — version will be auto-detected in step 02.

{If target_version was set AND doc_urls are being collected (either docs-only primary or supplemental):}

"**You're targeting version {target_version}. Do these documentation URLs correspond to that version?** [Y/N]"

- **If Y:** Proceed.
- **If N:** "Please provide the correct documentation URLs for version {target_version}." Re-collect doc_urls.

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
- **Source type:** {source or docs-only}
- **Source authority:** {official/community/internal}
{If target_version set:}
- **Target version:** {target_version} (user-specified)
{If doc_urls collected:}
- **Doc URLs:** {count} supplemental documentation URLs
- **Forge tier:** {tier}

Ready to analyze the target repository?"

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Target Analysis"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: Help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: use args]** — If `{headless_mode}`: consume pre-supplied arguments (target_repo, skill_name, scope_hint, language_hint) and auto-proceed. If required args missing, HALT: "headless mode requires target_repo and skill_name arguments."
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and target repository is confirmed will you load and read fully `./step-02-analyze-target.md` to execute target analysis.

