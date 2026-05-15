---
nextStepFile: 'analyze-target.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
descriptionVoiceExamplesFile: 'assets/description-voice-examples.md'
headlessArgsFile: 'references/headless-args.md'
headlessSourceAuthorityDetectionFile: 'references/headless-source-authority-detection.md'
portfolioSimilarityCheckFile: 'references/portfolio-similarity-check.md'
draftCheckpointFile: 'references/draft-checkpoint.md'
validateBriefInputsScript: '{project-root}/src/shared/scripts/skf-validate-brief-inputs.py'
emitBriefEnvelopeScript: '{project-root}/src/shared/scripts/skf-emit-brief-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

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

**Pre-flight write probe.** Before any conversational state accumulates, verify `{forge_data_folder}` is writable. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at step 5's atomic write — by then the user has invested 5–15 minutes. Run a single-byte write-and-remove probe:

```bash
mkdir -p "{forge_data_folder}" && \
  printf 'probe' > "{forge_data_folder}/.skf-write-probe" && \
  rm "{forge_data_folder}/.skf-write-probe"
```

`mkdir -p` succeeds on a pre-existing read-only mount, but the `printf > file` redirect actually attempts a write — that catches read-only, disk-full, and permissions-denied uniformly. **On any non-zero exit:** HALT (exit code 4, `halt_reason: "write-failed"`) — `"**Error:** {forge_data_folder} is not writable: {captured stderr}. Verify the path exists, the mount is writable, and there is free disk space, then re-run."` In headless mode, emit the error envelope per **step 5 §4b** with `halt_reason: "write-failed"` (skill_name is not yet resolved here — use the placeholder convention documented in §4b). On success, continue silently to the forge-tier load below.

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

**Wanted something different?** This workflow *creates* a new brief — a YAML scoping document for a skill that doesn't yet exist. If you meant to compile an existing brief into a skill (`/skf-create-skill`), package one for distribution (`/skf-export-skill`), or just ask SKF a question, type `cancel` at any prompt and run that workflow instead.

I'll help you define exactly what to skill and produce a `skill-brief.yaml` that drives the create-skill compilation workflow.

We'll work through this together:
1. **Now:** Understand what you want to skill and why
2. **Next:** Analyze the target repo structure
3. **Then:** Define scope boundaries
4. **Finally:** Confirm and write the brief

{If tier override was applied:}
**Your forge tier:** {override tier} (overridden from {original tier}) — {tier_gloss}
{Else:}
**Your forge tier:** {detected tier} — {tier_gloss}

(Substitute `{tier_gloss}` with the matching one-liner so the user knows what the tier label means: `Quick` → "text-only extraction"; `Forge` → "AST-grep on, semantic discovery off"; `Forge+` → "AST-grep + ccc semantic discovery"; `Deep` → "full pipeline — AST + ccc + qmd portfolio search + LLM re-ranking". The tier sets the ceiling for what the downstream create-skill workflow can do; you can re-run setup later to change it.)

Let's get started."

### 3. Gather Target Repository

This section has three sub-flows. Execute exactly one branch — 3.2 *or* 3.3 — based on the user's response in 3.1, then end with the shared confirmation. Do not mix branches.

#### 3.1 Collect target

"**What repository or documentation do you want to create a skill for?**

Provide one of:
- A **GitHub URL** (e.g., `https://github.com/org/repo`)
- A **local path** (e.g., `/path/to/project`)
- **Documentation URLs** for a docs-only skill (e.g., `https://docs.stripe.com/api`) — use this when no source code is available (SaaS, closed-source)

Or type `cancel` / `exit` / `[X]` to leave without writing anything.

**Target:**"

Wait for user response. Branch on the response:

- Empty input, `cancel`, `exit`, `[X]`, `q`, or `:q` → Display `"Cancelled — no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). Cancellation here is non-destructive — no files have been written yet by step 1. Headless mode never reaches this branch (the GATE in §8 short-circuits the interactive sub-flows).
- Documentation URLs only (no source location) → §3.2
- GitHub URL or local filesystem path → §3.3
- Any other free-form question (e.g. "what is this?", "show me an example", "how does SKF work?") → answer briefly, re-display the prompt

#### 3.2 Branch — Documentation URLs (docs-only)

- Set `source_type: "docs-only"` in the brief data
- Collect one or more doc URLs with optional labels
- HEAD-check the collected URLs in parallel — do not loop sequentially. Issue all N `curl -sI {url}` (or equivalent) calls in a **single message with N parallel Bash calls**, then process the responses together. Each call must use a 5-second timeout (`curl -sI --max-time 5 {url}`) to bound worst-case wall-time on hung hosts. Per response:
  - On 2xx/3xx: silently accept.
  - On 4xx/5xx, DNS failure, or timeout: warn `"Could not reach {url} — {status or error}. Confirm the URL is correct, or proceed anyway."` Interactive: re-prompt for a corrected URL or `[K] Keep anyway`. Headless: keep the URL and log the warning — the brief still records it but the failure is now visible at brief-creation time instead of materializing hours later in skf-create-skill.
- Set `source_authority: "community"` (forced for docs-only — T3 external documentation; the §3.3 source-authority prompt is skipped)
- Note: `source_repo` becomes optional (can be set to the main doc site URL for reference)

Skip §3.3 and continue at "Confirm the target" below.

#### 3.3 Branch — Source (GitHub URL or local path)

- Set `source_type: "source"` (default)
- **Pre-validate the target before continuing.** Issue these probes in a single message with parallel Bash calls:
  - **GitHub URL:** `curl -sI --max-time 5 {url}`. On a 4xx (typically 404 for a typo'd repo or org), warn `"GitHub returned {status} for {url} — confirm the URL is correct."` and re-prompt. On 2xx, accept.
  - **GitHub URL, in parallel:** `gh api repos/{owner}/{repo} --jq .name` (5-second timeout via `gh api --hostname github.com --method GET ... ` or just rely on default). On 403/404, warn `"GitHub API returned {status} for {owner}/{repo} — the repo may be private or your token may not have access. Step-02 will HALT here if this is not resolved. Continue anyway, or fix and re-prompt?"` and offer `[K] Keep anyway` / re-prompt for a corrected URL. Do not HALT — the canonical HALT still happens in step 2 §1, but surfacing access failures at URL-entry time prevents 5+ minutes of intent investment getting lost. On any other error (network failure, missing binary), log silently and let `gh auth status` below catch it. On 2xx, accept silently.
  - **GitHub URL, in parallel:** `gh auth status` — if it reports unauthenticated or the binary is missing, warn `"GitHub CLI not authenticated; step 2 will HALT when it tries to fetch the tree. Run 'gh auth login' before continuing, or supply a local clone path instead."` (Do not HALT here — let the user choose to fix or proceed; the canonical HALT still happens in step 2 §1's failure-class triage.)
  - **Local path:** verify the directory exists (`test -d {path}`). If not, warn `"Local path {path} does not exist."` and re-prompt.
- Optionally ask: "Are there any documentation URLs you'd like to include for supplemental context? (These will be fetched as T3 external references.)"
- If yes: collect doc URLs into `doc_urls`

**Source authority (this branch only — docs-only forces `community` in §3.2):**

**Interactive only** — skip this prompt entirely when `{headless_mode}` is true; the GATE in §8 resolves source_authority headlessly via the detection branch documented there.

"**Are you the maintainer of this library, or creating a community skill?**"
- If maintainer: set `source_authority: "official"`
- If community user: set `source_authority: "community"` (default)
- If internal/proprietary: set `source_authority: "internal"`

Default to `"community"` if user does not specify or skips.

---

Confirm the target.

### 3b. Gather Target Version

This step only collects `target_version` and validates its shape with the regex below — auto-detection runs in step 2 and precedence/invariant resolution lands in step 5's writer script. The canonical precedence rules live in `references/version-resolution.md`; load it from step 2 / step 5 only when the relevant section needs it.

**Headless:** if `target_version` was supplied as an argument, store it and skip the interactive prompt below. If `doc_urls` were also supplied, treat the version-vs-doc-URL confirmation prompt as auto-confirmed (Y).

"**Are you targeting a specific version of this library?**
(Leave blank to auto-detect from source)"

{If source_type is "docs-only":}
"Since this is a docs-only skill with no source code, specifying the version is recommended — otherwise it defaults to 1.0.0."

Wait for user response.

**If user provides a version:** Validate the shape against `^v?\d+\.\d+\.\d+([.\-+][0-9A-Za-z][0-9A-Za-z.\-+]*)?$` (full X.Y.Z form, with optional `v` prefix and pre-release / build suffix; CalVer like `2024.04.01` accepted; partial forms like `1`, `1.2`, `v2`, `latest` rejected). On a match, store as `target_version` and set `version` to this value. On a non-match, warn `"'{value}' doesn't look like semver — write the explicit triple (e.g. 1.0.0). Fix it now or skip auto-detection?"` and re-prompt for a corrected value or blank to fall through to step 2 auto-detection.
**If blank:** Proceed without `target_version` — version will be auto-detected in step 02.

{If target_version was set AND doc_urls are being collected (either docs-only primary or supplemental):}

"**You're targeting version {target_version}. Do these documentation URLs correspond to that version?** [Y/N]"

- **If Y:** Proceed.
- **If N:** "Provide the correct documentation URLs for version {target_version}." Re-collect doc_urls.

### 4. Gather User Intent

**First-timer rail (interactive only).** Before the intent prompt, check whether `{forge_data_folder}/` contains any prior briefs:

```bash
find "{forge_data_folder}" -maxdepth 2 -name "skill-brief.yaml" -print -quit
```

If the command produces any output, skip this rail silently — repeat users don't need the warm-up. If it produces no output (the user has never produced a brief), ask:

"**Want to see a few example descriptions first?** [Y/N] (Helpful if this is your first time — I'll show the voices we use so you have an anchor for what 'good intent' produces.)"

On `[Y]`: load `{descriptionVoiceExamplesFile}` and present the five examples verbatim with a one-line preface (`"Each example shows a different voice — yours doesn't have to match any specific one."`). On `[N]` or empty: proceed silently.

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

- Interactive: generate 1–3 non-colliding candidate alternates by scanning sibling directories under `{forge_data_folder}/`. Apply each rule that fires; skip rules whose precondition isn't met:
  1. `{name}-v{N}` where `N` is the smallest positive integer that doesn't collide (e.g. `{name}-v2`, `{name}-v3`) — always applies
  2. `{name}-{target_version}` if `target_version` is set and the suffix wouldn't collide (e.g. `marked-1.2.3`)
  3. `{name}-{source_authority}` if `source_authority` is not `community` (e.g. `marked-internal` for an internal fork)

  Number the surviving alternates `[1] [2] [3]…` in the order produced (1 alternate for a community-authority brief with no `target_version`; 2–3 otherwise). Then present:

  ```
  **Heads up — a brief for `{name}` already exists at `{path}`.**

  Suggested alternates (none collide):
    [1] {alternate-1}
    {if a second alternate was produced:} [2] {alternate-2}
    {if a third alternate was produced:} [3] {alternate-3}

  Pick a number to use that name, type a different name, or press Enter to keep `{name}` and let step 5 §2b handle the overwrite prompt.
  ```

  On a numbered choice, replace `{name}` with the chosen alternate. On Enter, fall through to step 5's overwrite gate. On any other input, treat as a new candidate name and re-run the collision check against it.

- Headless: log `"warn: skill name '{name}' collides with existing brief at {path}"` and proceed; the existing-brief overwrite policy in step 5 §2b is the canonical gate (HALT with `overwrite-cancelled` unless `force` was supplied).

**Portfolio-similarity check.** When the flow is interactive AND forge tier is `Deep` AND `tools.qmd` is true in `forge-tier.yaml`, load `{portfolioSimilarityCheckFile}` and follow the procedure there to catch semantic near-duplicates that exact-name collision misses. Otherwise (headless, or tier below Deep, or qmd unavailable) skip the load — the check does not run.

**Draft-resume check.** When the flow is interactive AND `{forge_data_folder}/{name}/.brief-draft.json` exists AND no `skill-brief.yaml` sits beside it, load `{draftCheckpointFile}` and follow Half 1 (Resume Check). On `[Y]` resume, the procedure jumps directly to §8 with prior answers restored — **the rest of §6, all of §7, and all of §7b are skipped**. Otherwise (headless, or no draft file, or a finished brief sits beside the draft) skip the load and continue with §6 normally.

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

**Draft checkpoint.** When the flow is interactive, load `{draftCheckpointFile}` (or reuse it if already loaded for the §6 resume check) and follow Half 2 (Checkpoint Write) to persist the captured state atomically. Headless mode skips this — the run completes in a single invocation, no resume is meaningful.

### 7b. Synthesize Skill Description

The schema's `description` field is 1-3 sentences and surfaces in skill registries — it must exist by the time step 4 presents the brief. Synthesize it explicitly here, while the user's intent is fresh, instead of letting it fall out implicitly later.

Compose a candidate 1-3 sentence description from the gathered material. **Write like a human library maintainer would** — what does an agent get from this skill, and when should it route here? Two facts must come through (what the skill is, when to use it); everything else is voice. Resist filling in the same skeleton every time.

Load `{descriptionVoiceExamplesFile}` for the five voice examples (range of acceptable leads, structures, and trigger phrasings) and the "do not template-stamp" guidance, then compose in that spirit. The asset documents what "in that spirit" means; the gathered material to draw on is the target repo, the user's intent, the version if set, and any scope hints.

Present:

"**Proposed skill description:**

> {synthesized description}

This is the text agents read when deciding whether to route to your skill — it sits in the registry row alongside dozens of other skills. Specific triggers ('use when…', 'reach for this when…') help agents match real user requests; generic descriptions blend in and get skipped. Edit, replace, or accept as-is."

Wait for user confirmation or alternative.

**Soft sentence-count check (interactive only).** Before storing the accepted text, count terminal sentence punctuation (`.`, `!`, `?` followed by whitespace or end-of-string) — abbreviations like `e.g.` will inflate the count slightly but the check is a soft nudge, not a HALT. If the count exceeds 3, present:

"**Heads up — that description reads as ~{N} sentences.** The conventional norm is 1-3 (it surfaces in registry rows alongside other skills, where length crowds out the trigger phrase). Tighten now, or accept as-is?"

On `tighten` or a fresh edit: re-prompt for the description. On `accept` or any non-edit response: store the accepted text and proceed. Counts of 1-3 store silently.

Store the accepted text as the brief's `description` field. The same field is re-presented in step 4 §3 for a final review pass — refinements there flow back to this value.

**Headless:** if the `intent` argument was supplied, load `{descriptionVoiceExamplesFile}` and run the same synthesis against it (in `{document_output_language}`), then store the result. If `intent` was not supplied, fall back in priority order:

1. **GitHub repo description** — when `target_repo` is a GitHub URL, fetch `gh api repos/{owner}/{repo} --jq .description` (5-second timeout). If a non-empty description comes back, load `{descriptionVoiceExamplesFile}` and synthesize using the GitHub description as the seed in place of `intent`. Write the synthesized description in `{document_output_language}` regardless of the seed's language (the seed may be in any language; the output's language is dictated by the workflow's document-output configuration). Log `"info: description seeded from GitHub repo description"`. (The full `gh api repos` response is fetched again in step 2 §1; this lightweight `--jq .description` call only retrieves the one field.)
2. **Generic stub** — when no GitHub description is available (local-path target, GitHub repo with empty description, or `gh api` fails): derive from `target_repo` + `skill_name` (`"Use the {skill_name} skill to work with code or content from {target_repo}."`) — the generic fallback does not need the asset — and log `"warn: description synthesized without intent or repo description — narrow registry text."`

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Target Analysis · [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF X: Treat as user-cancellation. Display `"Cancelled — no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). When `{headless_mode}` is true the GATE auto-proceeds and never reaches this branch — `[X]` is interactive-only. Cancellation here is non-destructive: no files have been written yet by step 1.
- IF Any other: Help user, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: use args]** — If `{headless_mode}`, consume pre-supplied arguments and auto-proceed. The full argument set (required/optional, defaults, halt codes, enum values) is documented in `{headlessArgsFile}` — load it now if you need to look up a specific argument. Validation is delegated to `{validateBriefInputsScript}`; the table is the canonical operator-facing documentation, the script enforces it.

  **Preset merge (before validation).** If the headless args include a `preset` field, load `{sidecar_path}/brief-presets/{preset}.yaml` and merge its contents as defaults — explicit args override preset values, key by key. The preset file is YAML; if it does not exist, log `"warn: preset '{name}' not found at {path} — proceeding without preset"` and continue (do not HALT). If it parses but contains unknown fields, log per-field warnings and pass through unchanged (the validator's KNOWN_FIELDS check will catch any that survive). Drop the `preset` key itself from the merged dict before passing to the validator (it is consumed at this level and is not a brief field).

  **Delegate validation to `{validateBriefInputsScript}`** instead of reasoning through the table rules in prose:

  ```bash
  echo '<headless-args-as-json>' | uv run {validateBriefInputsScript}
  ```

  The script returns a JSON envelope: `{valid, errors[], warnings[], normalized, halt_reason}`. Apply the result deterministically:

  - **`valid: false`** — emit the error envelope per **step 5 §4b** with the script's `halt_reason` (`"input-missing"` for absent required args / docs-only without doc_urls; `"input-invalid"` for enum violations, malformed semver, malformed kebab-case skill_name). Surface `errors[]` to the operator log so the failure is debuggable. HALT.
  - **`valid: true`** — consume the `normalized` object as the source of truth (it has defaults applied per the table). Surface `warnings[]` to the operator log but do not HALT. Auto-proceed.

  The script's `KNOWN_FIELDS` set must stay in sync with the table in `{headlessArgsFile}`.

  **Headless source-authority detection.** After consuming `normalized`, if `source_authority` is absent AND `source_type=source` AND `target_repo` is a GitHub URL, load `{headlessSourceAuthorityDetectionFile}` and follow the procedure there. Otherwise (precondition unmet, value already supplied, docs-only, or local-path) skip the load — `community` is the implicit default for the unmet branches.

- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and target repository is confirmed will you load and read fully `analyze-target.md` to execute target analysis.

