---
nextStepFile: 'analyze-target.md'
autoBriefFile: 'references/step-auto-brief.md'
headlessArgsFile: 'references/headless-args.md'
ratifyFile: 'references/gather-intent-ratify.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
portfolioSimilarityCheckFile: 'references/portfolio-similarity-check.md'
draftCheckpointFile: 'references/draft-checkpoint.md'
githubProbeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-probe.py'
  - '{project-root}/src/shared/scripts/skf-github-probe.py'
resolvePackageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-package.py'
  - '{project-root}/src/shared/scripts/skf-resolve-package.py'
validateBriefInputsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-inputs.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-inputs.py'
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

Bind `{run_dir}` ← the path the last command prints. Step 5, or step-auto-validate.md at the end of an `[auto]` run, removes the folder once the brief is written, and an `[X]` cancel removes it before it stops; any other halt leaves it in place with what the run staged. A step stages a payload there through a heredoc whose delimiter is quoted (`'SKF_JSON'`), so a quote or an apostrophe in it needs no escaping.

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

### 1b. Route by Mode

The first route that applies runs, and it leaves this file:

- **`{auto_mode}` is true** (a pipeline's `BS[auto]`): read `brief_path` from the pipeline data context (the forger passes it from AN's `SKF_ANALYZE_RESULT_JSON` `brief_paths[]`). If `brief_path` is not available, emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-missing"` and `mode` `"auto"` (SKILL.md Halt Contract), then HARD HALT (exit code 2): "**Auto mode requires `brief_path` in pipeline context: AN must run before BS[auto].**"
  Read `source_repo` from the pipeline data context too (the target the forger forwards), else from the upstream brief. Display "**Auto mode activated: bypassing the interactive brief workflow.**", then load, read fully, and execute `{autoBriefFile}`.
- **`{headless_mode}` is true:** load, read fully, and execute `{headlessArgsFile}`. Its input gate validates the arguments before any later section uses them, then continues at step 2, or ratifies the brief a `from_brief` argument names.
- **Otherwise** the run is interactive: continue at §2.

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

This section has five sub-flows. Execute exactly one branch, 3.1a *or* 3.2 *or* 3.3, based on the user's response in 3.1 (3.1b first resolves a package name to the repository 3.3 takes), then end with the shared confirmation (3.1a leaves this file for the ratify flow). Do not mix branches.

#### 3.1 Collect target

**Open-floor opening.** Lead with an open invitation, so an expert can state everything in one answer; a first-timer who pastes only a bare URL still gets the guided sequence below.

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

- Empty input, `cancel`, `exit`, `[X]`, `q`, or `:q` → Remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`).
- Any other free-form question (e.g. "what is this?", "show me an example", "how does SKF work?") → answer briefly, re-display the prompt
- Otherwise read the target the response names (the URL, path or package name, without the sentence around it) with `{resolvePackageHelper}`, resolved from `{resolvePackageProbeOrder}` (first existing path wins). Write the target exactly as given on the line between the markers, quotes, backticks and `$` included. `--local-first` reads a target that names an existing file or folder (relative to the working folder, `~` expanded) as a `local-path`, whatever its shape: `skill-brief.yaml`, `briefs/skill-brief.yaml`, `libs/mylib` or a path with a space.

```bash
uv run {resolvePackageHelper} parse-target --local-first <<'SKF_TARGET'
{target}
SKF_TARGET
```

  Route on the `kind` it returns:
  - `local-path`: a `skill-brief.yaml` file, or a folder that holds one → §3.1a; any other path → §3.3.
  - `github` → §3.3, with its `url` as the target. A pinned version (`target_version` not null, as in `owner/repo@1.2.0`) pre-fills `target_version`, which §3b checks before it keeps it: a full X.Y.Z is acknowledged, and a partial pin (`owner/repo@1.2`) is only a hint that §3b names when it asks again; a `/tree/<ref>/<folder>` URL pre-fills `target_ref` ← `ref` and adds `subdir` to the scope hints.
  - `package` or `registry-page` (`lodash`, `@scope/name@2.1.0`, `requests==2.31.0`, an npmjs.com, pypi.org or crates.io page) → §3.1b, which finds its repository; its `target_version`, when not null, pre-fills `target_version` the same way (`react@18` is a partial pin).
  - `other-host`: documentation pages (a docs site, an API reference) → §3.2; a repository on another git host (GitLab, Bitbucket, Codeberg, a self-hosted forge) → display "**Brief Skill reads GitHub repositories and local folders.** `{url}` is on `{host}`: clone it and give me the local path, or paste its GitHub URL if it has one." and re-display the prompt.
  - `unparsed`: several documentation URLs → §3.2; anything else → answer briefly and re-display the prompt.

  When `{resolvePackageHelper}` has no path, or the call prints no JSON, route the target by reading it yourself, by the same kinds (a path that exists is a `local-path`).

#### 3.1a Branch: Ratify an Existing Brief

The target is a `skill-brief.yaml`, or a folder holding one, that another workflow (typically `skf-analyze-source`) produced, to review and confirm instead of re-deriving. Load, read entirely, and execute `{ratifyFile}` with that path: it validates the brief, offers `[R]` Ratify, `[F]` Start fresh and `[X]` Cancel, and on `[R]` hands the run to step 4, past every later section of this file and steps 2 and 3.

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
  - On 4xx/5xx, DNS failure, or timeout: warn `"Could not reach {url} ({status or error}). Confirm the URL is correct, or proceed anyway."` and re-prompt for a corrected URL or `[K] Keep anyway`.
- Set `source_authority: "community"` (forced for docs-only — T3 external documentation; the §3.3 source-authority prompt is skipped)
- Note: `source_repo` becomes optional (can be set to the main doc site URL for reference)

Skip §3.3 and continue at "Confirm the target" below.

#### 3.3 Branch — Source (GitHub URL or local path)

- Set `source_type: "source"` (default)
- **Pre-validate the target before continuing.** An access problem caught at URL entry spares the user 5+ minutes of intent investment. Never HALT here: the canonical HALT stays in step 2 §1.
  - **GitHub URL:** resolve `{githubProbeHelper}` from `{githubProbeProbeOrder}` (first existing path wins) and run `uv run {githubProbeHelper} repo --repo "{url}" --timeout 20`. It prints one JSON line, and tells a missing or logged-out `gh`, a repository that does not exist and one the account cannot read apart:
    - `status: "ok"`: accept silently, a private repository that `gh` can read included. When `gh` is `"missing"` or `"unauthenticated"` (the repository was read without it), warn `"The GitHub CLI (gh) is not installed or not logged in: step 2 reads the repository through gh and will HALT until you install it or run 'gh auth login'. Fix it now, or supply a local clone path instead."` and continue.
    - `status: "unavailable"`: warn with its `message`, which names the cause (`cause`) and the fix, and offer `[K] Keep anyway` or a corrected URL, which is probed the same way. On `[K]`, keep the URL: step 2 §1 reports the cause again if it still holds.
    - No JSON (the helper is missing, or exits 1 or 2): continue silently; step 2 §1 checks the repository.
  - **Local path:** verify the directory exists (`test -d {path}`). If not, warn `"Local path {path} does not exist."` and re-prompt.
- Optionally ask: "Are there any documentation URLs you'd like to include for supplemental context? (These will be fetched as T3 external references.)"
- If yes: collect doc URLs into `doc_urls`

**Source authority (this branch only: docs-only forces `community` in §3.2):**

"**Are you the maintainer of this library, or creating a community skill?**"
- If maintainer: set `source_authority: "official"`
- If community user: set `source_authority: "community"` (default)
- If internal/proprietary: set `source_authority: "internal"`

Default to `"community"` if user does not specify or skips.

---

Confirm the target.

**Draft-resume check.** Now that the target is confirmed, and *before* the version prompt (§3b), intent (§4), or scope (§5) spend the user's time, offer to resume an in-progress draft that already covers this exact target, so a returning user re-types nothing. Keying on the target (not the not-yet-derived skill name) is what lets the offer fire this early:

1. **Cheap pre-filter** — list any draft file that mentions the confirmed target at all:

   ```bash
   grep -lF "{target}" "{forge_data_folder}"/*/.brief-draft.json 2>/dev/null
   ```

   `{target}` is the repo URL, local path, or primary doc URL just entered. No output → no draft; skip straight to §3b.

2. **Confirm each candidate on the target *field*, not free text.** Read the candidate draft's JSON and keep it only if its `target_repo` equals the confirmed target (source targets) or the target appears in its `doc_urls` (docs-only) — this rejects a draft that merely mentions the URL in its `intent` or `description`. Drop any candidate that has a finished `skill-brief.yaml` in the same directory (that brief is done; step 5's overwrite gate owns it).

3. If one or more live drafts survive, load `{draftCheckpointFile}` and follow Half 1 (Resume Check) against the most-recently-modified survivor; its directory basename is the candidate skill name. On `[Y]` resume, Half 1 restores every answer the draft holds and jumps straight to §8, or to step 4 when the draft holds the scope too: **§3b, §4, §5, §6, §7, and §7b are all skipped**. Otherwise (no surviving draft, or every match already has a finished brief beside it) skip the load and continue to §3b.

### 3b. Gather Target Version

This step only collects `target_version` and checks its shape: auto-detection runs in step 2 and precedence/invariant resolution lands in step 5's writer script. The canonical precedence rules live in `references/version-resolution.md`; load it from step 2 / step 5 only when the relevant section needs it.

When §3.1 pre-filled no version, ask:

"**Are you targeting a specific version of this library?**
(Leave blank to auto-detect from source)"

{If source_type is "docs-only":}
"Since this is a docs-only skill with no source code, specifying the version is recommended: otherwise it defaults to 1.0.0."

Wait for user response. **If blank:** proceed without `target_version`: version will be auto-detected in step 02.

**Check the version before you keep it.** For a version typed here, or one §3.1 pre-filled (from parse-target or from the free-form answer), resolve `{validateBriefInputsHelper}` from `{validateBriefInputsProbeOrder}` (first existing path wins; HALT if no candidate exists) and run its field-only check, with the version written as a JSON string:

```bash
uv run {validateBriefInputsHelper} --only target_version <<'SKF_JSON'
{"target_version": "<the version>"}
SKF_JSON
```

- **Exit 0** (`valid: true`): store it as `target_version` and set `version` to it. Acknowledge a pre-filled one ("I noted you're targeting v4.0.0") instead of asking.
- **Exit 1** (`valid: false`): keep nothing. Ask again, naming the value with its first error's `message`: `"{message}, or leave blank to auto-detect."` (for `react@18`, `'18' is a major version only`). Check the answer the same way; blank proceeds without `target_version`.
- **Exit 2** (the payload is not valid JSON, such as a quote left unescaped): write it again and re-run the check.

{If target_version was set AND doc_urls are being collected (either docs-only primary or supplemental):}

"**You're targeting version {target_version}. Do these documentation URLs correspond to that version?** [Y/N]"

- **If Y:** Proceed.
- **If N:** "Provide the correct documentation URLs for version {target_version}." Re-collect doc_urls.

### 4. Gather User Intent

**First-timer rail.** Before the intent prompt, check whether `{forge_data_folder}/` contains any prior briefs:

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

**Collision check.** If `{forge_data_folder}/{name}/skill-brief.yaml` already exists, say so and offer up to three alternates that do not collide, numbered: `{name}-v{N}` with the smallest free `N`, `{name}-{target_version}` when `target_version` is set, and `{name}-{source_authority}` when the authority is not `community`. A number takes that name; a typed name is checked the same way; Enter keeps `{name}` and leaves the overwrite question to step 5 §2b.

**Portfolio-similarity check.** When forge tier is `Deep` AND `tools.qmd` is true in `forge-tier.yaml`, load `{portfolioSimilarityCheckFile}` and follow the procedure there to catch semantic near-duplicates that exact-name collision misses. Otherwise skip the load: the check does not run.

### 7. Summarize Gathered Intent

Compose the §7b description first, then show this summary, the description and the §8 menu in one message, and wait once:

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
- **Forge tier:** {tier}"

### 7b. Synthesize Skill Description

The schema's `description` field is 1-3 sentences and surfaces in skill registries, so compose it here, while the intent is fresh. Load `{descriptionVoiceExamplesPath}` and compose a candidate in that spirit from the target repo, the user's intent, the version if set and any scope hints, in `{document_output_language}`, the language of the text the brief persists.

**Whatever lead you choose, the description must contain a literal `Use when` clause somewhere** — validators test for that exact phrase, so alternatives like "Triggers on…" or "Reach for this when…" do not satisfy it on their own. The clause need not lead: a descriptive opener followed by `Use when …` is both good voice and validator-clean.

Present it under the §7 summary:

"**Proposed skill description:**

> {synthesized description}

This is the text agents read when deciding whether to route to your skill, in a registry row beside dozens of others: a specific 'Use when' trigger helps agents match real requests. Edit it, replace it, or accept it with [C]."

### 8. Present MENU OPTIONS

End the §7 message with: "**Select:** edit the description or any field above · [C] Continue to Target Analysis · [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: when the description runs past three sentences, nudge once to tighten it (a long one crowds the trigger out of its registry row) and keep what the user settles on. Store it as the brief's `description`: step 4 §3 shows it again for a final pass. Load `{draftCheckpointFile}` (or reuse it from the §3 resume check) and follow Half 2 (Checkpoint Write), so the draft holds the gathered intent and the accepted description. Then load, read entire file, then execute {nextStepFile}
- IF X: Treat as user-cancellation. Remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). No brief was written; a draft saved earlier stays for a later resume.
- IF an edit to the description or another field: apply it (a new name runs the §6 collision check again), show the summary and the description again, then [Redisplay Menu Options](#8-present-menu-options)
- IF Any other: Help user, then [Redisplay Menu Options](#8-present-menu-options)
