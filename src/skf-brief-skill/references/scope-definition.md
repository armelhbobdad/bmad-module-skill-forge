---
nextStepFile: 'confirm-brief.md'
recommendScopeTypeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-recommend-scope-type.py'
  - '{project-root}/src/shared/scripts/skf-recommend-scope-type.py'
githubProbeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-probe.py'
  - '{project-root}/src/shared/scripts/skf-github-probe.py'
advancedElicitationSkill: '/bmad-advanced-elicitation'
partyModeSkill: '/bmad-party-mode'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Scope Definition

## Rules

- Do not make scope decisions unilaterally — user drives all scope choices
- Produce: scope type, include patterns, exclude patterns
- **Re-entry from step 4 [R] revise:** prior selections (`scope.type`, `scope.include`, `scope.exclude`, `scope.notes`, `scope.tier_a_include`, `scope.rationale`, `scripts_intent`, `assets_intent`, supplemental `doc_urls`) are preserved as the current state. Re-present them at each section as the existing answer; the user only re-confirms or overrides. Do not reset to the §2c template menu unless the user explicitly asks to start scope over. When `scope.rationale` is preserved and the user changes `chosen` (the scope type) on this pass, recompute `accepted_recommendation` (`chosen == recommended`) and refresh `reason` and `recorded` per the §2c capture rules — revise in place, do not append.
- **Ratify run (`ratify_mode: true`):** the hydrated brief's selections are the prior selections of the re-entry rule above, and the intent that §1 shows and §2c classifies is the change the user asked for when choosing [R], read with the hydrated `description`. For a source brief, step 2 has analyzed the brief's repository and §2c runs the recommender on that analysis: its `scope_type` and `matched_heuristic` replace the hydrated `recommended` and `heuristic`, and the §2c capture rules set the rest of `scope.rationale` from this pass (a brief without one gets one).

## Sequence

### 1. Present Scope Context

"**Let's define the scope for your skill.**

Based on the analysis, here's what we're working with:

- **Target:** {repo}
- **Language:** {detected language}
- **Modules found:** {count} — {list names}
- **Your intent:** {user intent from step 01}
{If scope hints from step 01:}
- **Your initial scope hints:** {hints}"

### 2. Handle Docs-Only Mode (if applicable)

**If `source_type: "docs-only"`:**

"**Docs-only mode — scope is defined by documentation pages.**

You've provided these documentation URLs:
{numbered list of doc_urls with labels}

Which pages should be included in the skill? (Enter numbers, or 'all')
Any additional documentation URLs to add?"

Wait for confirmation. Then skip to section 5 (Summarize Scope Decisions) with:
- `scope.type: "docs-only"`
- `scope.include`: confirmed doc URLs
- `scope.notes: "Generated from external documentation. All content is T3 confidence."`

**If `source_type: "source"` (default):** Continue to scope templates below.

### 2b. Confirm Supplemental Documentation (if doc_urls collected)

**If `source_type: "source"` AND supplemental `doc_urls` were collected in step 01:**

"**Supplemental documentation URLs:**
{numbered list of collected doc_urls with labels}

These will be included as T3 external references in the skill brief.
Add, remove, or confirm these URLs."

Wait for confirmation. Record any changes to `doc_urls`.

HEAD-check the URLs in parallel — issue all N `curl -sI --max-time 5 {url}` calls in a **single message with N parallel Bash calls**, then process the responses together. On a 4xx/5xx, DNS failure, or timeout per URL, warn `"Could not reach {url} — {status or error}."` and offer the same correct/keep choice as step 1 §3. The check is best-effort — never HALT on a failed HEAD — but the failure must surface here so it is not discovered downstream during compilation.

**On re-entry from step 4 [R]:** if `doc_urls` is byte-identical to the list that was probed on the previous pass through this subsection AND the prior per-URL probe results are still recoverable from conversation context, skip the parallel HEAD-check and reuse those results. Re-running the probes when the list has not changed wastes round-trips and can flap on transient failures. Any addition, removal, or edit to a URL invalidates the cache — re-probe the entire updated set. If the prior results are not recoverable (long session, compaction, etc.), re-probe — never cache-hit on a list whose results you cannot cite.

**If no supplemental doc_urls were collected:** Skip this subsection.

**Scope guidance for first-time users:** A well-scoped skill covers one cohesive capability with 3-8 primary functions. If the scope includes unrelated concerns (e.g., authentication AND data visualization), suggest splitting into separate briefs. If the scope is too narrow (single utility function), suggest expanding to the surrounding capability surface.

### 2c. Offer Scope Templates

Load `{scopeTemplatesPath}` for the scope type options ([F], [M], [P], [C], [R]) and their descriptions.

**Recommend a scope type — don't present the five options as equal weight.** SKILL.md states this workflow "steers toward the smaller, sharper version when scope is unclear" — surface that opinion at decision time. Use the analysis from step 2 and the user's intent from step 1 to pick the best-fit recommendation, then present the menu with that option marked as the suggested default.

**Resolve `{recommendScopeTypeHelper}`** from `{recommendScopeTypeProbeOrder}`; first existing path wins. HALT if no candidate exists. For a GitHub source, resolve `{githubProbeHelper}` from `{githubProbeProbeOrder}`; first existing path wins; with none, the call below runs on the `[]` listing of a failed call.

**Delegate the recommendation to `{recommendScopeTypeHelper}`**: it reads no free text, so what the intent asks for is your judgment, passed as three signals.

**Classify the intent into signals.** Read the user's intent and scope hints from step 1 and set each signal by what they mean:

| Signal | Set it when the user | Example |
|---|---|---|
| `wants_wiring_pattern` (`true`/`false`) | wants the skill to teach how an app, starter, template or example wires its parts together (IPC, build config, an integration), not a library's API | "skill the IPC wiring of this Electron starter" |
| `named_module_subset` (list) | limits the skill to named modules: list them as step 2 names them, `[]` when none | "just the auth module" → `["auth"]` |
| `wants_narrow_api` (`true`/`false`) | asks for the public API, the SDK or the client surface only | "the SDK only, not the internals" |

Judge the meaning, never a word: a negated or contrasted mention sets nothing ("the whole library, not just the parser" names no module; "the client library, not a demo app or starter template" wants no wiring pattern), and a word inside another word is not that word ("Kickstarter-style" says nothing about a starter). A signal the intent does not state stays `false` (or `[]`).

**Run the recommender in one Bash call**; it reads the file list through `--tree-file` and the registry files (`registry.ts`, `components.ts` and their `.tsx` forms) through `--entry-dir`, never a list or a file typed into the payload. For a GitHub source:

```bash
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
uv run {githubProbeHelper} tree --repo "{owner}/{repo}" --ref "{analysis_ref}" > "$work/tree.json"
uv run {recommendScopeTypeHelper} --tree-file "$work/tree.json" --registry-files | while IFS= read -r rel; do
  mkdir -p "$work/files/$(dirname "$rel")"
  gh api -H "Accept: application/vnd.github.raw" "repos/{owner}/{repo}/contents/$rel?ref={analysis_ref}" > "$work/files/$rel" || rm -f "$work/files/$rel"
done
uv run {recommendScopeTypeHelper} --tree-file "$work/tree.json" --entry-dir "$work/files" <<'SKF_SCOPE_PAYLOAD'
{
  "signals": {
    "wants_wiring_pattern": <true|false>,
    "named_module_subset": [<module names, or nothing>],
    "wants_narrow_api": <true|false>
  },
  "module_count": <count from step 2 §4.3>,
  "export_count": <count from step 2 §4.3>,
  "source_type": "source",
  "mode": "interactive"
}
SKF_SCOPE_PAYLOAD
```

- **A local source, or step 2's clone.** For a local path, or `{tmp_dir}` when step 2 cloned the repository on `[L]`, list that folder and read its registry files in place: replace the probe line with `git -C "<folder>" -c core.quotePath=false ls-files > "$work/tree.json"` (outside a git work tree: `(cd "<folder>" && find . -type f -not -path './.git/*' -not -path '*/node_modules/*') > "$work/tree.json"`), drop the fetch loop, and pass `--entry-dir "<folder>"`.
- **`mode`.** `"interactive"` lets a registry file's contents decide the component-registry rule (10+ entries or a `Component[]` annotation), so a file whose contents could not be read does not count; the §6 headless GATE passes `"headless"`, which counts such a file by its presence.
- **A failed call.** The call prints one JSON object, or exits 2 and names the problem on stderr. For a payload key or signal the script does not accept, fix the payload and run the call again. For a tree listing that failed (the stderr line carries the listing's own message), do not retry the network: run the call again with `printf '[]' > "$work/tree.json"` in place of the listing line, and log `"warn: scope-type recommendation ran without the file list ({message}); the component-registry check did not run"`. Interactively, show that warning with the recommendation, so the user can still pick [C].

The script returns `{scope_type, matched_heuristic, signals, rationale}`. Use `rationale` directly — it already names the specific signals that fired.

**Persist the rationale — do not discard it.** Hold `scope_type` as `rationale.recommended` and `matched_heuristic` as `rationale.heuristic` in conversation state. After the user's §2c selection: if they accept the recommendation, set `rationale.chosen = recommended`, `accepted_recommendation = true`, `reason = <script rationale verbatim>`. If they override, set `chosen = <selected type>`, `accepted_recommendation = false`, and ask one line — *"In a sentence, why {chosen} over the recommended {recommended}?"* — storing the answer as `reason` (or `"user overrode {recommended}->{chosen}; reason not stated"` if skipped). Set `recorded = {current ISO date}`. This object becomes `scope.rationale`.

Present:

"**Recommended scope type: [{letter}] {Name}** — {rationale from the script}.

How broadly should this skill cover the library?

{full menu from `{scopeTemplatesPath}` with the recommended letter marked, e.g. '[F] Full Library', '[M] Specific Modules', '[P] Public API Only ← recommended', '[C] Component Library', '[R] Reference App'}

Press Enter to accept the recommendation, or pick a different letter."

**First-timer reassurance (interactive only, never-briefed user — the §4 first-timer rail fired in step 01).** Append one line so the harder scope-type call doesn't stall a first-timer: "The recommended type is almost always right — accept it and re-scope from step 4 if the analysis surprises you." Repeat users and headless skip this line.

Wait for user selection. Empty input or just Enter accepts the recommendation; any of the five letters overrides.

### 3. Define Boundaries Based on Selection

Using the boundary definitions from `{scopeTemplatesPath}`, present the appropriate flow for the user's selected scope type ([F], [M], [P], [C], or [R]). Follow each type's prompts and wait for user input at each phase before proceeding.

### 3b. Monorepo Subpackage Convention

**Applies only when step 02 §1b selected a workspace (`monorepo_workspace` is set).** A subpackage skill documents one package inside a larger repository, so the source and scope fields follow a fixed convention. Express them wrong and `skf-create-skill` cannot resolve the scope globs against the cloned source:

- **`source_repo` stays the repository URL**, never the subpackage. `skf-create-skill` clones the whole repo at the pinned ref and then roots extraction at the subpackage, so the repo URL is what it clones.
- **`scope.include` / `scope.exclude` globs are repo-root-relative and subpackage-prefixed.** Step 02 rebased its analysis against `monorepo_workspace`, but the emitted globs must still carry the workspace prefix (e.g. `packages/sdk/src/**`, not `src/**`) because they resolve against the repo root, not the subpackage root.
- **Record the subpackage layout in `scope.notes`:** the subpackage root (the `monorepo_workspace` path), the published package name and version, the resolved git ref, and the local-clone directory. This is the only field that maps the repo-URL `source_repo` to the actual skilled subpackage — downstream workflows and re-forges read it to reconstruct the source layout.

Carry the `monorepo_workspace` path forward from step 02 §1b into the `scope.notes` you draft here rather than recomputing it.

### 3c. Tier-A Authoring Surface (coarse-glob monorepo subsets)

**Applies when a monorepo subpackage's `scope.include` uses coarse directory globs (`packages/foo/src/**`, `bin/**`) rather than an explicit file list.** Coarse globs also sweep in internal-only files (build scripts, state-store impls, generated config) that the package's public entry barrel never re-exports. `skf-create-skill` scores coverage against the *authoring* surface, and `skf-test-skill` re-derives that surface from the brief to guard against a deflated coverage denominator — so when the coarse-glob union is much larger than the documented export count and the brief names no narrower surface, the test gate inflates the denominator and an otherwise-complete skill scores as if it had large coverage gaps.

Head this off by capturing the authoring surface as **`scope.tier_a_include`**: the concrete source files whose named exports the package's public entry barrel (`index.ts`, `lib.rs`, `__init__.py`) actually re-exports. Derive the candidate list by tracing the entry barrel's re-export targets (the entry-point file was fetched in step 02), present it for the user to confirm or adjust, and store the confirmed list as `scope.tier_a_include`. List the definition files, not the umbrella barrel itself — a barrel re-exports the whole package, so including it widens the surface instead of narrowing it.

`scope.tier_a_include` does not change what gets extracted (that still follows `scope.include` / `scope.exclude`); it only pins the coverage denominator so the create-side and test-side counts agree without a mid-test hand-edit. Leave it unset when `scope.include` is already an explicit file list, or when the target is not a monorepo subset — there the coarse-glob union and the authoring surface coincide and no narrowing is needed.

### 4. Handle Language Override

{If language detection confidence was low from step 02:}

"**Language confirmation needed.**

The analysis detected **{language}** with low confidence. Is this correct, or should we set a different primary language?"

Wait for confirmation or override.

**Headless:** `language_hint`, when supplied, already set the language at step 02 §3; otherwise accept the detected language and continue. This confirmation prompt is interactive-only, so a headless run never stalls here.

### 5. Summarize Scope Decisions

"**Scope Summary:**

**Type:** {Full Library / Specific Modules / Public API / Component Library / Reference App}

**Include:**
{bulleted list of include patterns}

**Exclude:**
{bulleted list of exclude patterns}

**Language:** {confirmed language}

{If any scope notes:}
**Notes:** {scope notes}

Does this look right? You can adjust before we continue."

Wait for confirmation. Make adjustments if requested.

### 5b. Scripts & Assets Intent (Optional)

**Only ask when `scope.type` is `full-library`, `specific-modules`, `component-library`, or `reference-app` (skip for `public-api` and `docs-only`). Reference apps routinely ship wiring scripts and build-config assets — prompt for them.**

"Does this library include executable scripts (CLI tools, validation scripts, setup helpers) or static assets (config templates, JSON schemas, example configs) that should be packaged with the skill?"

- **[D] Auto-detect** from source (default) — SKF will scan for `scripts/`, `bin/`, `assets/`, `templates/`, `schemas/` directories
- **[N] None expected** — skip script/asset detection
- Or describe what you expect (free text)

Record the response as `scripts_intent` and `assets_intent` in the brief. Default to `detect` if user does not respond or skips.

### 6. Present MENU OPTIONS

Display: **Select an Option:** [A] Advanced Elicitation [P] Party Mode [C] Continue to Brief Confirmation [X] Cancel and exit

#### Menu Handling Logic:

- IF A: Invoke {advancedElicitationSkill}, and when finished redisplay the menu
- IF P: Invoke {partyModeSkill}, and when finished redisplay the menu
- IF C: Load, read entire file, then execute {nextStepFile}
- IF X: Treat as user-cancellation. Display `"Cancelled — no brief was written."` and HALT (exit code 6, `halt_reason: "user-cancelled"`). Cancellation here is non-destructive — no files have been written yet. `[X]` is interactive-only; the headless GATE never reaches this branch.
- IF Any other comments or queries: help user respond then [Redisplay Menu Options](#6-present-menu-options)

#### Execution rules:

- **GATE [default: C]** — If `{headless_mode}`: consume the headless inputs from step 1 in priority order:
  - If `scope_type` was supplied, use it (must match one of the six valid types) and skip the §2c template menu.
  - Otherwise auto-select via `{recommendScopeTypeHelper}`: classify the `intent` and `scope_hint` arguments into the three signals by the §2c rules (all `false` and `[]` when neither was supplied), log `"headless: scope signals wants_wiring_pattern={value} named_module_subset={list} wants_narrow_api={value} (from intent/scope_hint)"`, then run the §2c call with `"mode": "headless"`. Use the returned `scope_type` and log `"headless: scope_type={value} from heuristic={matched_heuristic}"`. For `source_type=docs-only`, run `uv run {recommendScopeTypeHelper} --json '{"source_type": "docs-only", "mode": "headless"}'` instead: it short-circuits to `docs-only` and needs no tree or signals.
  - If `include`/`exclude` were supplied, use them verbatim (split on comma) instead of running the boundary prompts in §3.
  - If `scripts_intent`/`assets_intent` were supplied, record them and skip §5b; otherwise default to `detect`.
  - Set `scope.rationale`: `recommended`/`heuristic` from the script (or `recommended = scope_type` arg, `heuristic = "user-supplied-arg"` when `scope_type` was passed); `chosen = <resolved type>`; `accepted_recommendation = (no scope_type arg)`; `reason = "<script rationale>"` (auto path) or `"headless: scope_type supplied as argument"` (arg path); `recorded = {date}`. No prompt — headless never asks "why".
  - Log: `"headless: scope_type={value} include={n} exclude={n} scripts_intent={value} assets_intent={value}"`.
- After other menu items execution, return to this menu
- User can chat or ask questions — always respond and then redisplay menu

