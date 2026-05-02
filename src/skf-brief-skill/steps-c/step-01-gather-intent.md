---
nextStepFile: './step-02-analyze-target.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
versionResolutionFile: 'references/version-resolution.md'
---

# Step 1: Gather Intent

## STEP GOAL:

To initialize the brief-skill workflow by discovering the forge tier configuration, then gathering the user's target repository, intent, and any upfront scope hints for skill creation.

## Rules

- Focus only on gathering intent — do not analyze the repo yet (Step 02)
- Do not examine source code or list exports in this step
- Open-ended discovery facilitation — collect target repo, user intent, scope hints, skill name
- All user-facing output in `{communication_language}`

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Discover Forge Tier

Attempt to load `{forgeTierFile}`:

**If found:**
- Read the tier level (quick, forge, forge+, or deep)
- Note available tools for scoping guidance later

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

**If found but the YAML cannot be parsed (corrupted or truncated):**
- Display: "**Cannot read forge-tier.yaml** at `{forgeTierFile}` — the file exists but failed to parse: `{parser error message}`. The setup workflow can rewrite it cleanly. Until then, the brief workflow falls back to **Quick** tier (no extra tools assumed)."
- Continue with `tier = "Quick"` and `tools = {}` — do not HALT. Record `tier_source: "fallback-corrupted-config"` for later diagnostics.

**If not found:**
- "**Cannot proceed.** forge-tier.yaml not found at `{forgeTierFile}`. Run the **setup** workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."
- HALT (exit code 3, `halt_reason: "forge-tier-missing"`) — do not proceed.

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

This section has three sub-flows. Execute exactly one branch — 3.2 *or* 3.3 — based on the user's response in 3.1, then end with the shared confirmation. Do not mix branches.

#### 3.1 Collect target

"**What repository or documentation do you want to create a skill for?**

Provide one of:
- A **GitHub URL** (e.g., `https://github.com/org/repo`)
- A **local path** (e.g., `/path/to/project`)
- **Documentation URLs** for a docs-only skill (e.g., `https://docs.stripe.com/api`) — use this when no source code is available (SaaS, closed-source)

**Target:**"

Wait for user response. Branch on the response:

- Documentation URLs only (no source location) → §3.2
- GitHub URL or local filesystem path → §3.3

#### 3.2 Branch — Documentation URLs (docs-only)

- Set `source_type: "docs-only"` in the brief data
- Collect one or more doc URLs with optional labels
- For each collected URL, perform a `HEAD` request (or `curl -sI`) to verify the URL resolves with a 2xx/3xx status:
  - On 2xx/3xx: silently accept.
  - On 4xx/5xx, DNS failure, or timeout: warn `"Could not reach {url} — {status or error}. Confirm the URL is correct, or proceed anyway."` Interactive: re-prompt for a corrected URL or `[K] Keep anyway`. Headless: keep the URL and log the warning — the brief still records it but the failure is now visible at brief-creation time instead of materializing hours later in skf-create-skill.
- Set `source_authority: "community"` (forced for docs-only — T3 external documentation; the §3.3 source-authority prompt is skipped)
- Note: `source_repo` becomes optional (can be set to the main doc site URL for reference)

Skip §3.3 and continue at "Confirm the target" below.

#### 3.3 Branch — Source (GitHub URL or local path)

- Set `source_type: "source"` (default)
- Optionally ask: "Are there any documentation URLs you'd like to include for supplemental context? (These will be fetched as T3 external references.)"
- If yes: collect doc URLs into `doc_urls`

**Source authority (this branch only — docs-only forces `community` in §3.2):**

"**Are you the maintainer of this library, or creating a community skill?**"
- If maintainer: set `source_authority: "official"`
- If community user: set `source_authority: "community"` (default)
- If internal/proprietary: set `source_authority: "internal"`

Default to `"community"` if user does not specify or skips.

---

Confirm the target.

### 3b. Gather Target Version

Load `{versionResolutionFile}` for the canonical precedence and invariant rules — this step only collects `target_version`; auto-detection runs in step 02 and resolution lands in step 05.

**Headless:** if `target_version` was supplied as an argument, store it and skip the interactive prompt below. If `doc_urls` were also supplied, treat the version-vs-doc-URL confirmation prompt as auto-confirmed (Y).

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
- **If N:** "Provide the correct documentation URLs for version {target_version}." Re-collect doc_urls.

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

**Collision check (interactive and headless):** before locking the name, check whether `{forge_data_folder}/{name}/skill-brief.yaml` already exists. If it does:

- Interactive: "**Heads up — a brief for `{name}` already exists at `{path}`.** Pick a different name to keep the new brief separate, or confirm to continue (the existing brief's overwrite prompt fires in step 05)."
- Headless: log `"warn: skill name '{name}' collides with existing brief at {path}"` and proceed; the existing-brief overwrite policy in step-05 §2b is the canonical gate (HALT with `overwrite-cancelled` unless `force` was supplied).

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

### 7b. Synthesize Skill Description

The schema's `description` field is 1-3 sentences and surfaces in skill registries — it must exist by the time step-04 presents the brief. Synthesize it explicitly here, while the user's intent is fresh, instead of letting it fall out implicitly later.

Compose a candidate 1-3 sentence description from the gathered material. Pattern (adjust naturally — do not template-stamp):

```
{What the skill enables an agent to do, in active voice}, drawn from {target}{ at version {target_version}, if set}{ for {scope hint summary}, if any scope hints were captured}. Use when {one-sentence trigger condition derived from intent — what task or question routes to this skill}.
```

Present:

"**Proposed skill description:**

> {synthesized description}

This is what shows up when agents discover the skill. Edit it, replace it, or accept as-is."

Wait for user confirmation or alternative. Store the accepted text as the brief's `description` field. The same field is re-presented in step-04 §4 for a final review pass — refinements there flow back to this value.

**Headless:** if the `intent` argument was supplied, run the same synthesis against it and store the result. If `intent` was not supplied, derive from `target_repo` + `skill_name` (`"Use the {skill_name} skill to work with code or content from {target_repo}."`) and log `"warn: description synthesized without intent — narrow registry text."`

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Target Analysis"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other: Help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: use args]** — If `{headless_mode}`, consume pre-supplied arguments per the table below and auto-proceed. Any missing required arg → HALT with exit code 2, `halt_reason: "input-missing"`, message: `"headless mode requires target_repo and skill_name arguments."` (Same HALT applies when `source_type=docs-only` and `doc_urls` is empty.)

  | Argument | Required | Default | Notes |
  |----------|----------|---------|-------|
  | `target_repo` | yes | — | HALT (exit 2) if absent |
  | `skill_name` | yes | — | HALT (exit 2) if absent |
  | `source_type` | no | `source` | If `docs-only`, `doc_urls` becomes required |
  | `doc_urls` | conditional | — | Required when `source_type=docs-only`. List of `url` or `url,label` |
  | `source_authority` | no | `community` | `official` / `community` / `internal`; forced to `community` when `source_type=docs-only` |
  | `target_version` | no | — | Auto-detected in step-02 if absent |
  | `scope_hint` | no | — | Free-text steering for §5 |
  | `language_hint` | no | — | Overrides language detection in step-02/03 |
  | `scope_type` | no | — | `full-library` / `specific-modules` / `public-api` / `component-library` / `reference-app` / `docs-only` |
  | `include` | no | — | Comma-separated globs (used by step-03 §3) |
  | `exclude` | no | — | Comma-separated globs (used by step-03 §3) |
  | `scripts_intent` | no | `detect` | `detect` / `none` / free-text |
  | `assets_intent` | no | `detect` | `detect` / `none` / free-text |
  | `intent` | no | — | Free-text used to derive `description` in §7b |
  | `force` | no | — | Overwrite existing brief without prompting (consumed in step-05 §2b) |
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and target repository is confirmed will you load and read fully `./step-02-analyze-target.md` to execute target analysis.

