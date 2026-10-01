---
nextStepFile: 'analyze-target.md'
ratifyTargetFile: 'confirm-brief.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
headlessArgsFile: 'references/headless-args.md'
headlessSourceAuthorityDetectionFile: 'references/headless-source-authority-detection.md'
portfolioSimilarityCheckFile: 'references/portfolio-similarity-check.md'
draftCheckpointFile: 'references/draft-checkpoint.md'
validateBriefInputsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-inputs.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-inputs.py'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
githubProbeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-probe.py'
  - '{project-root}/src/shared/scripts/skf-github-probe.py'
resolvePackageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-package.py'
  - '{project-root}/src/shared/scripts/skf-resolve-package.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Gather Intent

## Rules

- Focus only on gathering intent — do not analyze the repo yet (Step 02)
- Do not examine source code or list exports in this step
- Open-ended discovery facilitation — collect target repo, user intent, scope hints, skill name
- All user-facing output in `{communication_language}`

## Sequence

### 1. Discover Forge Tier

**Pre-flight write probe and run folder.** Before any conversational state accumulates, verify `{forge_data_folder}` is writable, and create the run folder, where later steps stage what they hand to a helper (the repository's file list, fetched files, JSON payloads) instead of typing it into a command. A read-only mount, full disk, or permissions-denied path otherwise only surfaces at step 5's atomic write, after the user has invested 5–15 minutes. Run a single-byte write-and-remove probe, then create the folder:

```bash
mkdir -p "{forge_data_folder}" && \
  printf 'probe' > "{forge_data_folder}/.skf-write-probe" && \
  rm "{forge_data_folder}/.skf-write-probe" && \
  mkdir -p "{project-root}/_bmad-output/.skf-run" && \
  mktemp -d "{project-root}/_bmad-output/.skf-run/skf-brief-skill-XXXXXXXX"
```

Bind `{run_dir}` ← the path the last command prints. Step 5, or step-auto-validate.md on an `[auto]` approval, removes the folder once the brief is written, and an `[X]` cancel removes it before it stops; any other halt leaves it in place with what the run staged. A step stages a payload there through a quoted heredoc (`<<'SKF_JSON'`), so a quote or an apostrophe in it needs no escaping.

`mkdir -p` succeeds on a pre-existing read-only mount, but the `printf > file` redirect actually attempts a write, which catches read-only, disk-full, and permissions-denied uniformly. **On any non-zero exit:** emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "write-failed"` (SKILL.md Halt Contract), then HALT (exit code 4): `"**Error:** {forge_data_folder} or the run folder under {project-root}/_bmad-output/.skf-run/ is not writable: {captured stderr}. Verify the path exists, the mount is writable, and there is free disk space, then re-run."` On success, continue silently to the forge-tier load below.

Attempt to load `{forgeTierFile}`:

**If found:**
- Read the tier level (quick, forge, forge+, or deep)
- Note available tools for scoping guidance later

**Apply tier override:** Read `{sidecar_path}/preferences.yaml`. If `tier_override` is set and is a valid tier value (Quick, Forge, Forge+, or Deep), use it instead of the detected tier.

**If found but the YAML cannot be parsed (corrupted or truncated):**
- Display: "**Cannot read forge-tier.yaml** at `{forgeTierFile}` — the file exists but failed to parse: `{parser error message}`. The setup workflow can rewrite it cleanly. Until then, the brief workflow falls back to **Quick** tier (no extra tools assumed)."
- Continue with `tier = "Quick"` and `tools = {}` — do not HALT. Record `tier_source: "fallback-corrupted-config"` for later diagnostics.

**If not found:** emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "forge-tier-missing"` (SKILL.md Halt Contract), then HALT (exit code 3): "**Cannot proceed.** forge-tier.yaml not found at `{forgeTierFile}`. Run the **setup** workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."

### 1b. Auto Mode Check

`{auto_mode}` is true when the invocation carried the `[auto]` flag (a pipeline's `BS[auto]`): SKILL.md On Activation step 2 resolved it.

**IF `{auto_mode}` is true:**

1. **Load upstream brief path:** Read `brief_path` from the pipeline data context (passed by the forger from AN's `SKF_ANALYZE_RESULT_JSON` `brief_paths[]`). If `brief_path` is not available, emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-missing"` and `mode` `"auto"` (SKILL.md Halt Contract), then HARD HALT (exit code 2): "**Auto mode requires `brief_path` in pipeline context: AN must run before BS[auto].**"
2. **Load source repo:** Read `source_repo` from the pipeline data context (the target repo URL or path, forwarded by the forger). If not available, attempt to extract it from the upstream brief at `brief_path`.
3. "**Auto mode activated — bypassing interactive brief workflow.**"
4. **Route to auto-brief:** Load, read fully, then execute `references/step-auto-brief.md`, and hand off there — do not fall through to §2 or any subsequent section of this file.

**IF `{auto_mode}` is NOT true:**
Continue to §2 as normal — the entire interactive flow below is unchanged.

### 2. Welcome and Explain

"**Welcome to Brief Skill — the skill scoping workflow.**

**Wanted something different?** This workflow *creates* a new brief — a YAML scoping document for a skill that doesn't yet exist. If you meant to compile an existing brief into a skill (`/skf-create-skill`), package one for distribution (`/skf-export-skill`), or just ask SKF a question, type `cancel` at any prompt and run that workflow instead.

I'll help you define exactly what to skill and produce a `skill-brief.yaml` that drives the create-skill compilation workflow.

{If tier override was applied:}
**Your forge tier:** {override tier} (overridden from {original tier}) — {tier_gloss}
{Else:}
**Your forge tier:** {detected tier} — {tier_gloss}

(Substitute `{tier_gloss}` with the matching one-liner so the user knows what the tier label means: `Quick` → "text-only extraction"; `Forge` → "AST-grep on, semantic discovery off"; `Forge+` → "AST-grep + ccc semantic discovery"; `Deep` → "full pipeline — AST + ccc + qmd portfolio search + LLM re-ranking". The tier sets the ceiling for what the downstream create-skill workflow can do; you can re-run setup later to change it.)

Let's get started."

### 3. Gather Target Repository

This section has five sub-flows. Execute exactly one branch, 3.1a *or* 3.2 *or* 3.3, based on the user's response in 3.1 (3.1b first resolves a package name to the repository 3.3 takes), then end with the shared confirmation (3.1a is terminal for §3 and jumps directly to confirm-brief.md). Do not mix branches.

#### 3.1 Collect target

**Open-floor opening.** Lead with an open invitation so an expert can state everything in one breath rather than being walked through seven discrete prompts — costs almost nothing token-wise and sharply improves the conversational feel of this, the most question-heavy mode. A first-timer who pastes only a bare URL still gets the full guided sequence below, unchanged.

"**What repository or documentation do you want to create a skill for?**

Tell me everything you have — the repo or docs, what you want to skill and why, any scope or version thoughts. Or just paste a URL and we'll go from there.

Provide one of:
- A **GitHub URL** (e.g., `https://github.com/org/repo`)
- A **package name or registry page** (e.g., `zod`, `requests==2.31.0`, `https://www.npmjs.com/package/zod`), which I resolve to its GitHub repository
- A **local path** (e.g., `/path/to/project`)
- **Documentation URLs** for a docs-only skill (e.g., `https://docs.stripe.com/api`) — use this when no source code is available (SaaS, closed-source)
- A **path to an existing `skill-brief.yaml`** (file path or a directory containing one) — use this to ratify a brief produced by another workflow (e.g. `skf-analyze-source`) without re-deriving fields

Or type `cancel` / `exit` / `[X]` to leave without writing anything.

**Target:**"

Wait for user response. **Parse the response for any of the fields the later sections collect** — `target_version` (§3b), intent (§4), scope hints (§5), source authority (§3.3), a proposed name (§6) — and pre-fill every field the user covered, holding them in workflow context. Sections §3b/§4/§5/§6/§7b then **acknowledge a pre-filled field instead of re-asking** ("I noted you're targeting v4.0.0"), and prompt only for the gaps. An expert who stated it all collapses to the §3.1 target branch plus the §7b description confirmation; a bare URL falls through to the full sequence. Then branch on the response for the target itself:

- Empty input, `cancel`, `exit`, `[X]`, `q`, or `:q` → Remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). Headless mode never reaches this branch (the GATE in §8 short-circuits the interactive sub-flows).
- Any other free-form question (e.g. "what is this?", "show me an example", "how does SKF work?") → answer briefly, re-display the prompt
- Otherwise read the target the response names (the URL, path or package name, without the sentence around it) with `{resolvePackageHelper}`, resolved from `{resolvePackageProbeOrder}` (first existing path wins). Write the target exactly as given on the line between the markers, quotes, backticks and `$` included. `--local-first` reads a target that names an existing file or folder (relative to the working folder, `~` expanded) as a `local-path`, whatever its shape: `skill-brief.yaml`, `briefs/skill-brief.yaml`, `libs/mylib` or a path with a space.

```bash
uv run {resolvePackageHelper} parse-target --local-first <<'SKF_TARGET'
{target}
SKF_TARGET
```

  Route on the `kind` it returns:
  - `local-path`: a `skill-brief.yaml` file, or a folder that holds one → §3.1a; any other path → §3.3.
  - `github` → §3.3, with its `url` as the target. A pinned version (`target_version` not null, as in `owner/repo@1.2.0`) pre-fills `target_version`; a `/tree/<ref>/<folder>` URL pre-fills `target_ref` ← `ref` and adds `subdir` to the scope hints.
  - `package` or `registry-page` (`lodash`, `@scope/name@2.1.0`, `requests==2.31.0`, an npmjs.com, pypi.org or crates.io page) → §3.1b, which finds its repository; its `target_version`, when not null, pre-fills `target_version`.
  - `other-host`: documentation pages (a docs site, an API reference) → §3.2; a repository on another git host (GitLab, Bitbucket, Codeberg, a self-hosted forge) → display "**Brief Skill reads GitHub repositories and local folders.** `{url}` is on `{host}`: clone it and give me the local path, or paste its GitHub URL if it has one." and re-display the prompt.
  - `unparsed`: several documentation URLs → §3.2; anything else → answer briefly and re-display the prompt.

  When `{resolvePackageHelper}` has no path, or the call prints no JSON, route the target by reading it yourself, by the same kinds (a path that exists is a `local-path`).

#### 3.1a Branch — Ratify existing brief

This branch handles the AN→BS handoff: another workflow (typically `skf-analyze-source`) has already produced a `skill-brief.yaml`, and the user wants to review and confirm it without re-running gather-intent / analyze-target / scope-definition. **This §3.1a path is reached only interactively** — it is entered by typing a brief path at the §3.1 prompt, which headless mode never does. The headless equivalent is the §8 GATE `from_brief` route: it consumes a `from_brief` argument, runs the same schema validation, sets the same `ratify_mode`, hydrates from the same parsed payload, and jumps to step 4 exactly as `[R]` does below — see §8. Keep the two paths' hydration in sync.

Resolve the path:

- If the user's input ends in `skill-brief.yaml` and points at an existing file → that is the brief path.
- Otherwise (input was a directory) → the brief path is `<input>/skill-brief.yaml`.

**Validate the brief against the schema** before presenting it. Resolve `{validateBriefSchemaHelper}` from `{validateBriefSchemaProbeOrder}` (first existing path wins; HALT if no candidate exists), then:

```bash
uv run {validateBriefSchemaHelper} <resolved-brief-path>
```

The script returns JSON `{valid, errors[], warnings[], halt_reason, brief}`. Apply the result:

- **`valid: false`** — surface the `errors[]` messages and the `halt_reason` to the user, then re-display the §3.1 prompt for a corrected path (or another target altogether). Do not HALT — the user may simply have pointed at the wrong file. Example: `"**Brief at `{path}` is invalid:** {first error message}. Pick a different brief, or supply a repo / docs URL instead."`
- **`valid: true`** — proceed with the parsed `brief` payload.

Surface any non-empty `warnings[]` as a single grouped line (`"**Brief validation warnings:** {joined warnings}"`), then present the ratify menu:

```
**Existing brief detected at `{path}`.**

- **Name:** {brief.name}
- **Target:** {brief.source_repo}
- **Description:** "{brief.description}"
- **Created:** {brief.created} by {brief.created_by}
- **Scope:** {brief.scope.type}

Pick one:
  [R] Ratify — review in step 4 and write (overwriting this file once approved)
  [F] Start fresh — discard this brief and re-prompt for a target
  [X] Cancel and exit
```

Wait for user response. Branch:

- **[R] Ratify** — Confirm overwrite up front: store `ratify_mode: true` and `ratify_source_path: <resolved-brief-path>` in workflow context. Hydrate the brief context variables from the parsed `brief` payload so step 4 has the same field set it normally derives from steps 1-3:
  - `name` ← `brief.name`; `version` ← `brief.version`; `target_version` ← `brief.target_version`
  - `target_ref` ← `brief.target_ref`; `source_ref` ← `brief.source_ref` (optional git refs; preserve when present)
  - `source_repo` ← `brief.source_repo`; `source_type` ← `brief.source_type` (`source` when absent, the schema default); `source_authority` ← `brief.source_authority`; `doc_urls` ← `brief.doc_urls`
  - `language` ← `brief.language`; `description` ← `brief.description`; `forge_tier` ← `brief.forge_tier`
  - `created` ← `brief.created`; `created_by` ← `brief.created_by`
  - `scope.type` / `scope.include` / `scope.exclude` / `scope.tier_a_include` / `scope.notes` / `scope.rationale` / `scope.amendments` ← `brief.scope.*` (preserve `tier_a_include` and the `amendments` log verbatim: do not re-derive or drop them)
  - `scope.registry_path` / `scope.ui_variants` / `scope.demo_patterns` ← `brief.scope.*` (a component library's registry file, design system variants and demo globs; skf-create-skill writes the registry file and the demo globs back once the user confirms them: preserve all three verbatim)
  - `scripts_intent` ← `brief.scripts_intent`; `assets_intent` ← `brief.assets_intent`

  Then load, read entirely, and execute `{ratifyTargetFile}` — bypassing §3.1b/§3.2/§3.3, §3b, §4, §5, §6, §7, §7b, and §8 entirely. Skip step 2 (analyze-target) and step 3 (scope-definition) — both would re-derive fields already on disk. The forward chain resumes at step 4 (confirm-brief) where the user gets the standard review pass and can still adjust fields inline via §4.

- **[F] Start fresh** — discard the loaded brief and re-display §3.1 above (the user is now at the same point as if they had typed nothing).
- **[X] Cancel**: remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). The brief at `{path}` is left as it is.
- **Any other input** — treat as a fresh §3.1 response and re-evaluate the routing branches above (a typed GitHub URL after seeing the menu means "I changed my mind, brief this repo instead").

#### 3.1b Branch: Resolve a Package Name

The target names a package (or its registry page), not a repository. Ask the registries for the repository it is published from, with the same helper:

```bash
uv run {resolvePackageHelper} resolve "{package_name}" --timeout 10 [--registry {registry}]
```

Pass `--registry` when parse-target set `registry` (a registry page's, PyPI for a `==` pin, npm for a scoped name). The JSON's `status` is `ok`, `ambiguous` or `fallthrough` (exit 0, 3 or 1):

- **`ok`**: show "`{package_name}` is published from {resolved_url} ({registry_used})." and continue at §3.3 with `resolved_url` as the target. When `source_subdir` is set (the package's folder in a monorepo), add it to the scope hints.
- **`ambiguous`**: the name may belong to more than one project. Offer every candidate, numbered: `resolved_url` from `registry_used` first, then each `also_found_in` entry that has a `resolved_url`. Let the user pick one by number or paste the GitHub URL they mean, and continue at §3.3 with the pick; its `source_subdir`, when set, joins the scope hints.
- **`fallthrough`** (no registry gave a GitHub repository), or no JSON: display "**`{package_name}` did not resolve to a GitHub repository** on npm, PyPI or crates.io. Paste its GitHub URL or a local path." and re-display the §3.1 prompt.

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
- **Pre-validate the target before continuing.** An access problem caught at URL entry spares the user 5+ minutes of intent investment. Never HALT here: the canonical HALT stays in step 2 §1.
  - **GitHub URL:** resolve `{githubProbeHelper}` from `{githubProbeProbeOrder}` (first existing path wins) and run `uv run {githubProbeHelper} repo --repo "{url}" --timeout 20`. It prints one JSON line, and tells a missing or logged-out `gh`, a repository that does not exist and one the account cannot read apart:
    - `status: "ok"`: accept silently, a private repository that `gh` can read included. When `gh` is `"missing"` or `"unauthenticated"` (the repository was read without it), warn `"The GitHub CLI (gh) is not installed or not logged in: step 2 reads the repository through gh and will HALT until you install it or run 'gh auth login'. Fix it now, or supply a local clone path instead."` and continue.
    - `status: "unavailable"`: warn with its `message`, which names the cause (`cause`) and the fix, and offer `[K] Keep anyway` or a corrected URL, which is probed the same way. On `[K]`, keep the URL: step 2 §1 reports the cause again if it still holds. Headless: keep the URL and log `"warn: {message}"`; step 2 §1 halts with its classified reason if the cause still holds.
    - No JSON (the helper is missing, or exits 1 or 2): continue silently; step 2 §1 checks the repository.
  - **Local path:** verify the directory exists (`test -d {path}`). If not, warn `"Local path {path} does not exist."` and re-prompt. Headless: keep the path and log the warning; step 2 §1 halts with `target-inaccessible`.
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

**Draft-resume check (interactive only).** Now that the target is confirmed — and *before* the version prompt (§3b), intent (§4), or scope (§5) spend the user's time — offer to resume an in-progress draft that already covers this exact target, so a returning user re-types nothing. Keying on the target (not the not-yet-derived skill name) is what lets the offer fire this early. When the flow is interactive:

1. **Cheap pre-filter** — list any draft file that mentions the confirmed target at all:

   ```bash
   grep -lF "{target}" "{forge_data_folder}"/*/.brief-draft.json 2>/dev/null
   ```

   `{target}` is the repo URL, local path, or primary doc URL just entered. No output → no draft; skip straight to §3b.

2. **Confirm each candidate on the target *field*, not free text.** Read the candidate draft's JSON and keep it only if its `target_repo` equals the confirmed target (source targets) or the target appears in its `doc_urls` (docs-only) — this rejects a draft that merely mentions the URL in its `intent` or `description`. Drop any candidate that has a finished `skill-brief.yaml` in the same directory (that brief is done; step 5's overwrite gate owns it).

3. If one or more live drafts survive, load `{draftCheckpointFile}` and follow Half 1 (Resume Check) against the most-recently-modified survivor; its directory basename is the candidate skill name. On `[Y]` resume, Half 1 restores every answer the draft holds and jumps straight to §8, or to step 4 when the draft holds the scope too: **§3b, §4, §5, §6, §7, and §7b are all skipped**. Otherwise (headless, no surviving draft, or every match already has a finished brief beside it) skip the load and continue to §3b.

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

On `[Y]`: load `{descriptionVoiceExamplesPath}` and present the five examples verbatim with a one-line preface (`"Each example shows a different voice — yours doesn't have to match any specific one."`). On `[N]` or empty: proceed silently.

"**What's your intent for this skill?**

Help me understand:
- **What** specifically do you want to skill from this repo?
- **Why** — what's the use case? How will an AI agent use this skill?
- **Any initial thoughts** on scope? (Full library? Specific modules? Public API only?)

Take your time — the more context you share, the better the brief."

Wait for user response. Ask follow-up questions if intent is unclear.

**Capture, don't interrupt.** If the user volunteers an out-of-scope aside while answering — "the v3 API is totally different", "we're deprecating the auth module next quarter" — do not redirect the conversation to chase it. Silently note it as a candidate `scope.notes` line (carried forward into the brief's `scope.notes` at step 3) and continue the current prompt. These unprompted asides are often the most useful scoping signal; the cost of losing them when the conversation moves on is higher than the cost of one stored line.

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

(The resume-a-draft offer for a returning user fires earlier, right after the target is confirmed in §3 — see the §3 "Draft-resume check" — so the intent, scope, and description a draft holds are spared *before* they get re-gathered here.)

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

The schema's `description` field is 1-3 sentences and surfaces in skill registries — it must exist by the time step 4 presents the brief. Synthesize it explicitly here, while the user's intent is fresh, instead of letting it fall out implicitly later.

Compose a candidate 1-3 sentence description from the gathered material. **Write like a human library maintainer would** — what does an agent get from this skill, and when should it route here? Two facts must come through (what the skill is, when to use it); everything else is voice. Resist filling in the same skeleton every time.

Load `{descriptionVoiceExamplesPath}` for the five voice examples (range of acceptable leads and structures) and the "do not template-stamp" guidance, then compose in that spirit. The asset documents what "in that spirit" means; the gathered material to draw on is the target repo, the user's intent, the version if set, and any scope hints. Write it in `{document_output_language}`, the language of the text the brief persists.

**Whatever lead you choose, the description must contain a literal `Use when` clause somewhere** — validators test for that exact phrase, so alternatives like "Triggers on…" or "Reach for this when…" do not satisfy it on their own. The clause need not lead: a descriptive opener followed by `Use when …` is both good voice and validator-clean.

Present:

"**Proposed skill description:**

> {synthesized description}

This is the text agents read when deciding whether to route to your skill — it sits in the registry row alongside dozens of other skills. A specific 'use when…' trigger helps agents match real user requests; generic descriptions blend in and get skipped. Edit, replace, or accept as-is."

Wait for user confirmation or alternative.

**Soft sentence-count check (interactive only).** Before storing the accepted text, count terminal sentence punctuation (`.`, `!`, `?` followed by whitespace or end-of-string) — abbreviations like `e.g.` will inflate the count slightly but the check is a soft nudge, not a HALT. If the count exceeds 3, present:

"**Heads up — that description reads as ~{N} sentences.** The conventional norm is 1-3 (it surfaces in registry rows alongside other skills, where length crowds out the trigger phrase). Tighten now, or accept as-is?"

On `tighten` or a fresh edit: re-prompt for the description. On `accept` or any non-edit response: store the accepted text and proceed. Counts of 1-3 store silently.

Store the accepted text as the brief's `description` field. The same field is re-presented in step 4 §3 for a final review pass — refinements there flow back to this value.

**Draft checkpoint (interactive only).** Once the description is accepted, load `{draftCheckpointFile}` (or reuse it if already loaded for the §3 resume check) and follow Half 2 (Checkpoint Write), so the draft holds the gathered intent and the accepted description. Headless mode skips this: the run completes in a single invocation, so no resume is meaningful.

**Headless:** if the `intent` argument was supplied, load `{descriptionVoiceExamplesPath}` and run the same synthesis against it (in `{document_output_language}`), then store the result. If `intent` was not supplied, fall back in priority order:

1. **GitHub repo description**: when `target_repo` is a GitHub URL, fetch `gh api repos/{owner}/{repo} --jq .description` (5-second timeout). If a non-empty description comes back, load `{descriptionVoiceExamplesPath}` and synthesize using the GitHub description as the seed in place of `intent`. Write the synthesized description in `{document_output_language}` regardless of the seed's language (the seed may be in any language; the output's language is dictated by the workflow's document-output configuration). Log `"info: description seeded from GitHub repo description"`.
2. **Generic stub** — when no GitHub description is available (local-path target, GitHub repo with empty description, or `gh api` fails): derive from `target_repo` + `skill_name` (`"Use the {skill_name} skill to work with code or content from {target_repo}."`) — the generic fallback does not need the asset — and log `"warn: description synthesized without intent or repo description — narrow registry text."`

### 8. Present MENU OPTIONS

Display: "**Select:** [C] Continue to Target Analysis · [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF X: Treat as user-cancellation. Remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). When `{headless_mode}` is true the GATE auto-proceeds and never reaches this branch: `[X]` is interactive-only. No brief was written; the draft §7b saved stays for a later resume.
- IF Any other: Help user, then [Redisplay Menu Options](#8-present-menu-options)

#### Execution rules:

- **Resolve `{validateBriefInputsHelper}`** from `{validateBriefInputsProbeOrder}`; first existing path wins. HALT if no candidate exists.

- **GATE [default: use args]** — If `{headless_mode}`, consume pre-supplied arguments and auto-proceed. The full argument set (required/optional, defaults, halt codes, enum values) is documented in `{headlessArgsFile}` — load it now if you need to look up a specific argument. Validation is delegated to `{validateBriefInputsHelper}`; the table is the canonical operator-facing documentation, the script enforces it.

  **Preset merge (before validation).** Skip this merge entirely when a `from_brief` argument is present — presets seed a *derived* brief and have no meaning on the ratify route below. Otherwise: if the headless args include a `preset` field, load `{sidecar_path}/brief-presets/{preset}.yaml` and merge its contents as defaults — explicit args override preset values, key by key. The preset file is YAML; if it does not exist, log `"warn: preset '{name}' not found at {path} — proceeding without preset"` and continue (do not HALT). If it parses but contains unknown fields, log per-field warnings and pass through unchanged (the validator's KNOWN_FIELDS check will catch any that survive). Drop the `preset` key itself from the merged dict before passing to the validator (it is consumed at this level and is not a brief field).

  **Delegate validation to `{validateBriefInputsHelper}`** instead of reasoning through the table rules in prose. Stage the merged arguments as one JSON object in the run folder, then run the script on the file:

```bash
cat > "{run_dir}/headless-args.json" <<'SKF_JSON'
<the merged headless arguments, as one JSON object>
SKF_JSON
uv run {validateBriefInputsHelper} < "{run_dir}/headless-args.json"
```

  The script returns a JSON envelope: `{valid, errors[], warnings[], normalized, halt_reason}`. Apply the result deterministically:

  - **`valid: false`**: emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with the script's `halt_reason` (`input-missing` for absent required args or docs-only without doc_urls; `input-invalid` for enum violations, malformed semver, malformed kebab-case skill_name) (SKILL.md Halt Contract), surface `errors[]` to the operator log so the failure is debuggable, then HALT (exit code 2).
  - **`valid: true`**: consume the `normalized` object as the source of truth (it has defaults applied per the table). Log each `warnings[]` entry and add it to `workflow_warnings[]` as `<field>: <message>`, but do not HALT. Auto-proceed.

  The script's `KNOWN_FIELDS` set must stay in sync with the table in `{headlessArgsFile}`.

  **Ratify route — `from_brief` present.** After a `valid: true` result, branch on `normalized.from_brief`. When it is set, this run ratifies a pre-authored brief instead of deriving one — the headless mirror of the interactive §3.1a `[R]` branch. Take this route *before* the source-authority detection and analyze-target routing below (both belong to the derive path and do not apply here):

  1. **Resolve the brief path.** If `normalized.from_brief` ends in `skill-brief.yaml`, that is the path; otherwise treat it as a directory and use `<from_brief>/skill-brief.yaml`.
  2. **Schema-validate.** Resolve `{validateBriefSchemaHelper}` from `{validateBriefSchemaProbeOrder}` (first existing path wins; HALT if no candidate exists), then run `uv run {validateBriefSchemaHelper} <resolved-brief-path>`. The script returns `{valid, errors[], warnings[], halt_reason, brief}`. Apply it — and note that, unlike the interactive §3.1a branch (which re-prompts because the operator might have a corrected path to offer), headless has no second chance, so an unusable brief is terminal:
     - **`valid: false`** with the script's `halt_reason` `brief-missing` (path absent or unreadable): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-missing"` (SKILL.md Halt Contract), surface `errors[]` to the operator log, then HALT (exit code 2).
     - **`valid: false`** with any other `halt_reason` (`brief-malformed` or `brief-invalid`): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-invalid"` (SKILL.md Halt Contract), surface `errors[]`, then HALT (exit code 2).
     - **`valid: true`**: log any non-empty `warnings[]`, add each to `workflow_warnings[]` as `<field>: <message>`, and proceed with the parsed `brief` payload.
  3. **Hydrate and route.** Store `ratify_mode: true` and `ratify_source_path: <resolved-brief-path>` in workflow context, then hydrate the brief context variables from the parsed `brief` payload exactly as the §3.1a `[R]` branch does: every field of its mapping list, each kept verbatim where that list says so (one list, so the two routes never drift apart). Load, read entirely, and execute `{ratifyTargetFile}`, bypassing step 2 (analyze-target) and step 3 (scope-definition), both of which would re-derive fields already on disk. The forward chain resumes at step 4 (confirm-brief), which auto-confirms `[C]` under headless and proceeds to step 5's write (the step 5 §2b ratify branch auto-overwrites in place). Do **not** run the source-authority detection or the `[C] → {nextStepFile}` routing below: they belong to the derive path.

  **Headless source-authority detection (derive route only — no `from_brief`).** After consuming `normalized`, if `source_authority` is absent AND `source_type=source` AND `target_repo` is a GitHub URL, load `{headlessSourceAuthorityDetectionFile}` and follow the procedure there. Otherwise (precondition unmet, value already supplied, docs-only, or local-path) skip the load — `community` is the implicit default for the unmet branches.

