---
nextStepFile: 'analyze-target.md'
ratifyFile: 'references/gather-intent-ratify.md'
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
briefDraftsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-brief-drafts.py'
  - '{project-root}/src/shared/scripts/skf-brief-drafts.py'
checkUrlsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-urls.py'
  - '{project-root}/src/shared/scripts/skf-check-urls.py'
qmdPortfolioSimilarityProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-qmd-portfolio-similarity.py'
  - '{project-root}/src/shared/scripts/skf-qmd-portfolio-similarity.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Gather Intent

## Rules

- Focus only on gathering intent — do not analyze the repo yet (Step 02)
- Do not examine source code or list exports in this step
- Open-ended discovery facilitation — collect target repo, user intent, scope hints, skill name
- All user-facing output in `{communication_language}`

## Sequence

Step 0 (`references/preflight.md`) ran §1 and §1b, and it sends only an interactive run here.

### 2. Welcome and Explain

"**Welcome to Brief Skill — the skill scoping workflow.**

**Wanted something different?** This workflow *creates* a new brief — a YAML scoping document for a skill that doesn't yet exist. If you meant to compile an existing brief into a skill (`/skf-create-skill`), package one for distribution (`/skf-export-skill`), or just ask SKF a question, type `cancel` at any prompt and run that workflow instead.

I'll help you define exactly what to skill and produce a `skill-brief.yaml` that drives the create-skill compilation workflow.

{If tier override was applied:}
**Your forge tier:** {override tier} (overridden from {original tier}) — {tier_gloss}
{Else:}
**Your forge tier:** {detected tier} — {tier_gloss}

(Substitute `{tier_gloss}` with the matching one-liner so the user knows what the tier label means: `Quick` → "text-only extraction; AST and semantic discovery off"; `Forge` → "AST-grep on; semantic and re-ranking off"; `Forge+` → "AST-grep + ccc semantic discovery; re-ranking off"; `Deep` → "full pipeline: AST + ccc + qmd portfolio search + LLM re-ranking". The tier sets the ceiling for what the downstream create-skill workflow can do; you can re-run setup later to change it.)

Let's get started."

### 3. Gather Target Repository

This section has five sub-flows. Execute exactly one branch, 3.1a *or* 3.2 *or* 3.3, based on the user's response in 3.1 (3.1b first resolves a package name to the repository 3.3 takes), then end with the draft-resume check (3.1a leaves this file for the ratify flow). Do not mix branches.

#### 3.1 Collect target

**Invoking message.** When the message that invoked this skill names a target (a URL, a package, a local path, or a `skill-brief.yaml` or its folder), that message is the §3.1 answer: skip the prompt below and read it by the rules after the prompt, pre-fill included. It answers the first prompt only: when a branch below re-displays the prompt, show it.

**Open-floor opening.** Lead with an open invitation, so an expert can state everything in one answer; a bare URL is enough, and §4 then asks for the intent.

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

Wait for user response. **Parse the response for any of the fields the later sections use**: `target_version` (§3b), intent (§4), scope hints, supplemental doc URLs, source authority and a proposed name (§6), plus each out-of-scope aside as a `scope_note_candidates` line (§4); pre-fill every field the user covered, holding them in workflow context. §3b checks a pre-filled version, §4 asks only for a missing intent, and §7 shows the rest, so an expert who stated it all goes from the target branch straight to the §7 message. Then branch on the response for the target itself:

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
- Check the collected URLs with the one call below. A URL that is `ok` passes silently. For any other, warn `"Could not reach {url} ({status or error}). Confirm the URL is correct, or proceed anyway."`, with `{status or error}` from its entry, and re-prompt for a corrected URL, checked the same way, or `[K] Keep anyway`.
- Set `source_authority: "community"` (forced for docs-only: T3 external documentation)
- Note: `source_repo` becomes optional (can be set to the main doc site URL for reference)

Resolve `{checkUrlsHelper}` from `{checkUrlsProbeOrder}` (first existing path wins) and pass the URLs one per line, without their labels:

```bash
uv run {checkUrlsHelper} --timeout 5 --urls-file - <<'SKF_URLS'
<the URLs, one per line>
SKF_URLS
```

It prints `[{url, ok, status, error}]` in input order: each URL is asked with HEAD, redirects followed, and again with GET when the server answers 403, 405 or 501. When `{checkUrlsHelper}` has no path, run `curl -sIL --max-time 5 "{url}"` for each URL instead and take a 2xx or 3xx on its last status line as `ok`.

Skip §3.3 and continue at the draft-resume check below.

#### 3.3 Branch — Source (GitHub URL or local path)

- Set `source_type: "source"` (default)
- **Pre-validate the target before continuing.** An access problem caught at URL entry spares the user 5+ minutes of intent investment. Never HALT here: the canonical HALT stays in step 2 §1.
  - **GitHub URL:** resolve `{githubProbeHelper}` from `{githubProbeProbeOrder}` (first existing path wins) and run `uv run {githubProbeHelper} repo --repo "{url}" --timeout 20`. It prints one JSON line, and tells a missing or logged-out `gh`, a repository that does not exist and one the account cannot read apart:
    - `status: "ok"`: accept silently, a private repository that `gh` can read and a public one read without `gh` included.
    - `status: "unavailable"`: warn with its `message`, which names the cause (`cause`) and the fix, and offer `[K] Keep anyway` or a corrected URL, which is probed the same way. On `[K]`, keep the URL: step 2 §1 reports the cause again if it still holds.
    - No JSON (the helper is missing, or exits 1 or 2): continue silently; step 2 §1 checks the repository.
  - **Local path:** verify the directory exists (`test -d {path}`). If not, warn `"Local path {path} does not exist."` and re-prompt.

---

**Draft-resume check.** Right after the target is validated, before step 1 asks anything else, offer to resume an in-progress draft that already covers this exact target, so a returning user re-types nothing, and then a finished brief to revise. Keying on the target (not the not-yet-derived skill name) is what lets the offer fire this early. Resolve `{briefDraftsHelper}` from `{briefDraftsProbeOrder}` (first existing path wins). Both calls below read `{target}`, the target §3.2 or §3.3 took: the repo URL (for a package, §3.1b's `resolved_url`, not the name typed), the local path or the primary doc URL, written exactly as it is on the line between the markers, and the helper matches it however it is written: letter case, a trailing slash, `.git`, `owner/repo` or a relative path. When `{briefDraftsHelper}` has no path, or a call prints no JSON, offer nothing, warn nothing and continue at §3b: the check is a convenience, as the checkpoint write is.

**A draft.** Find the newest draft whose `target_repo` names the target, or a docs-only draft whose `doc_urls` do, in a folder that holds no finished `skill-brief.yaml`:

```bash
uv run {briefDraftsHelper} find --forge-data "{forge_data_folder}" <<'SKF_TARGET'
{target}
SKF_TARGET
```

It prints `{name, path, mtime, holds_scope}`, or `null`. On a draft, load `{draftCheckpointFile}` and follow Half 1 (Resume Check) with that result. On `[Y]` resume, Half 1 restores every answer the draft holds and jumps straight to §8, or to step 4 when the draft holds the scope too: **§3b, §4, §6, §7, and §7b are all skipped**. On `null`, or on `[N]`, look for a finished brief.

**A finished brief.** List the briefs whose `source_repo` names the target, and the docs-only briefs whose `doc_urls` do, newest first:

```bash
uv run {briefDraftsHelper} briefs --forge-data "{forge_data_folder}" <<'SKF_TARGET'
{target}
SKF_TARGET
```

It prints `[{name, path, mtime}]`, and `[]` continues at §3b. For one brief, present:

```
**A finished brief for this target exists:** `{name}` (last updated: {mtime}).
  [U] Revise `{name}`: review it at step 4 and write it back
  [N] New brief: keep gathering
```

For several, list them as `[U1]`, `[U2]` and so on in that order, each with its name and mtime, and end with `[N] New brief`. On a `[U]` pick, load `{ratifyFile}` with that brief's `path`: its §1 validates the brief in full, its §2 menu is skipped, since the user already chose to revise, and its §3 hands the run to step 4 as a ratify run. On `[N]`, continue at §3b.

### 3b. Gather Target Version

Ask nothing here when §3.1 pre-filled no version: §7 shows the default version, and the user gives one there.

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

**`first_brief`.** Bind it from this `find`: true when it prints nothing (no brief exists yet under `{forge_data_folder}/`), else false. §7b and step 3 §2c read it; a resumed draft or a ratify run never reaches this section, and an unset `first_brief` counts as false.

```bash
find "{forge_data_folder}" -maxdepth 2 -name "skill-brief.yaml" -print -quit
```

When §3.1 pre-filled the intent, skip the question: §7 shows it. Otherwise ask:

"**What's your intent for this skill?**

Help me understand:
- **What** specifically do you want to skill from this repo?
- **Why** — what's the use case? How will an AI agent use this skill?
- **Any initial thoughts** on scope? (Full library? Specific modules? Public API only?)

Take your time — the more context you share, the better the brief."

Wait for user response. Ask follow-up questions if intent is unclear.

**Capture, don't interrupt.** If the user volunteers an out-of-scope aside while answering ("the v3 API is totally different", "we're deprecating the auth module next quarter"), do not redirect the conversation to chase it. Add it as one line to `scope_note_candidates`, which §7 shows and step 3 seeds into `scope.notes` before its scope summary, and continue the current prompt. These unprompted asides are often the most useful scoping signal; the cost of losing them when the conversation moves on is higher than the cost of one stored line.

### 6. Derive Skill Name

Take the name §3.1 pre-filled, else derive one in kebab-case from the target repo and the intent: it names the output directory and files. Ask nothing here: §7 shows the name with what the two checks below found, and the user changes it there.

**Collision check.** If `{forge_data_folder}/{name}/skill-brief.yaml` already exists, §7 says so and lists up to three alternates that do not collide, numbered: `{name}-v{N}` with the smallest free `N`, `{name}-{target_version}` when `target_version` is set, and `{name}-{source_authority}` when the authority, settled at the top of §7 before the list is shown, is not `community`. At §8 a number takes that name, a typed name is checked the same way, and [C] keeps `{name}` and leaves the overwrite question to step 5 §2b.

**Portfolio-similarity check.** When forge tier is `Deep` AND `tools.qmd` is true in the `tools` step 0 §1 bound, load `{portfolioSimilarityCheckFile}` and follow the procedure there to catch semantic near-duplicates that exact-name collision misses; §7 shows its heads-up. Otherwise skip the load: the check does not run.

### 7. Summarize Gathered Intent

**Source authority.** When neither the §3.1 answer nor a resumed draft gave `source_authority` (§3.2 sets it for docs-only), set it first. For a GitHub target, compare `gh api user --jq .login` (5-second timeout) with the URL's owner, both lower-cased: a match is `official`. Another login, a local path or a failed call is `community`. Record no warning: the summary marks the value (default), and the user changes it there. An authority the user states, in the §3.1 answer or here, is `official` for a maintainer, `internal` for a private or company codebase and `community` otherwise.

Compose the §7b description first, then show this summary, the description and the §8 menu in one message, and wait once. "(default)" marks a value the user did not give: the run derived, detected or defaulted it, and the user can change it here or at step 4.

"**Here's what I've captured:**

- **Target:** {repo URL or path}
- **Intent:** {user's intent summary}
- **Scope hints:** {the hints from the §3.1 and §4 answers, or "None: we'll define scope after analysis"}
- **Skill name:** {name, with (default) when §6 derived it}
- **Source type:** {source or docs-only}
- **Source authority:** {official/community/internal, with (default) when this section set it, or (forced for docs-only) when §3.2 set it}
{If target_version set:}
- **Target version:** {target_version} (user-specified)
{Else, on a source target:}
- **Target version:** auto-detected in step 2 (default)
{Else, on a docs-only target:}
- **Target version:** 1.0.0 (default). With no source code to read it from, give the version the docs describe if you know it.
{If doc_urls collected:}
- **Doc URLs:** {count} supplemental documentation URLs
{Else:}
- **Doc URLs:** none (default)
- **Forge tier:** {tier}
{If scope_note_candidates is not empty:}
- **Noted for scope notes:** {the lines, joined with "; "}

{If §6 found a collision:}
**`{name}` already has a brief.** Pick an alternate by number, or type another name:
{the numbered alternates}

{If §6's portfolio-similarity check found close briefs:}
{its heads-up, its briefs as bullets, not numbers, so a number picks only an alternate}"

### 7b. Synthesize Skill Description

The schema's `description` field is 1-3 sentences and surfaces in skill registries, so compose it here, while the intent is fresh. Load `{descriptionVoiceExamplesPath}` and compose a candidate in that spirit from the target repo, the user's intent, the version if set and any scope hints, in `{document_output_language}`, the language of the text the brief persists.

**Whatever lead you choose, the description must contain a literal `Use when` clause somewhere** — validators test for that exact phrase, so alternatives like "Triggers on…" or "Reach for this when…" do not satisfy it on their own. The clause need not lead: a descriptive opener followed by `Use when …` is both good voice and validator-clean.

Present it under the §7 summary. When `first_brief` (§4) is true, show beside it one example from `{descriptionVoiceExamplesPath}` whose lead differs from the candidate's, so a new user sees another voice:

"**Proposed skill description:**

> {synthesized description}

{If first_brief is true:}
**Another voice, for comparison:**

> {that example}

This is the text agents read when deciding whether to route to your skill, in a registry row beside dozens of others: a specific 'Use when' trigger helps agents match real requests. Edit it, replace it, or accept it with [C]."

### 8. Present MENU OPTIONS

End the §7 message with: "**Select:** edit the description or any field above · [C] Continue to Target Analysis · [X] Cancel and exit"

#### Menu Handling Logic:

- IF C: when the description runs past three sentences, nudge once to tighten it (a long one crowds the trigger out of its registry row) and keep what the user settles on. Store it as the brief's `description`: step 4 §3 shows it again for a final pass. Load `{draftCheckpointFile}` (or reuse it from the §3 resume check) and follow Half 2 (Checkpoint Write), so the draft holds the gathered intent and the accepted description. Then load, read entire file, then execute {nextStepFile}
- IF X: Treat as user-cancellation. Remove the run folder (`case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac`), display `"Cancelled: no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). No brief was written; a draft saved earlier stays for a later resume.
- IF an edit to the description or another field, or the number of a §6 alternate: apply it (a new name runs the §6 collision check again, a new version the §3b check, and a new version or doc URL §3b's doc-URL question when both are set), show the summary and the description again, then [Redisplay Menu Options](#8-present-menu-options)
- IF Any other: Help user, then [Redisplay Menu Options](#8-present-menu-options)
