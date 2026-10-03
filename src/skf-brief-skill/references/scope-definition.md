---
nextStepFile: 'confirm-brief.md'
recommendScopeTypeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-recommend-scope-type.py'
  - '{project-root}/src/shared/scripts/skf-recommend-scope-type.py'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
detectRegistryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-registry.py'
  - '{project-root}/src/shared/scripts/skf-detect-registry.py'
githubFetchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-fetch.py'
  - '{project-root}/src/shared/scripts/skf-github-fetch.py'
analyzeStepFile: 'analyze-target.md'
draftCheckpointFile: 'references/draft-checkpoint.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Scope Definition

## Rules

- Do not make scope decisions unilaterally — user drives all scope choices
- Produce: scope type, include patterns, exclude patterns
- **Headless (`{headless_mode}` is true):** no section prompts. Each section's **Headless** line says what it takes instead, from the arguments step 1's input gate validated, so a headless run never waits here.
- **Re-entry from step 4 [R] revise:** prior selections (`scope.type`, `scope.include`, `scope.exclude`, `scope.notes`, `scope.tier_a_include`, `scope.rationale`, `scope.registry_path`, `scope.ui_variants`, `scope.demo_patterns`, `scripts_intent`, `assets_intent`, supplemental `doc_urls`) are preserved as the current state; the three component-library fields are dropped only when this pass changes `scope.type` away from `component-library`. Re-present them at each section as the existing answer; the user only re-confirms or overrides. Do not reset to the §2c template menu unless the user explicitly asks to start scope over. When `scope.rationale` is preserved and the user changes `chosen` (the scope type) on this pass, recompute `accepted_recommendation` (`chosen == recommended`) and refresh `reason` and `recorded` per the §2c capture rules: revise in place, do not append.
- **Staged inputs.** Step 2 staged the repository in the run folder: its file list at `{run_dir}/tree.json`, the files it fetched under `{run_dir}/files/` and its exports in `{run_dir}/extract.json`. §2c and §3c read them there, and a GitHub file not fetched yet is fetched beside them with `{githubFetchHelper}`, resolved from `{githubFetchProbeOrder}` (first existing path wins; HALT if no candidate exists), as step 2 §1 describes.
- **Resumed draft:** a run that resumed a draft at step 4 (draft-checkpoint.md Half 1) and came here through step 4's `[R]` has not run step 2 in this session. When `source_type` is `source` and `{run_dir}/tree.json` does not exist, load, read entire file, then execute {analyzeStepFile} first: it stages the analysis again at `{analysis_ref}` and chains back here.
- **Ratify run (`ratify_mode: true`):** the hydrated brief's selections are the prior selections of the re-entry rule above, and the intent that §1 shows and §2c classifies is the change the user asked for when choosing [R], read with the hydrated `description`. For a source brief, step 2 has analyzed the brief's repository and §2c runs the recommender on that analysis: its `scope_type` and `matched_heuristic` replace the hydrated `recommended` and `heuristic`, and the §2c capture rules set the rest of `scope.rationale` from this pass (a brief without one gets one).

## Sequence

### 1. Present Scope Context

In the same turn as step 2's §5 summary (or its §0 note on a docs-only target), the user has just read the analysis: leave out the recap lines below and show only the intent lines and the question. Show the recap when step 4's `[R]` came here without step 2 running in this turn: a plain revise, a later `[R]` on a ratify run (`ratify_analyzed`), or a docs-only ratify run or resumed draft.

"**Let's define the scope for your skill.**

{Recap:}
Based on the analysis, here's what we're working with:

- **Target:** {repo}
- **Language:** {language from step 2: the detected or confirmed one, or `documentation` for a docs-only target}
- **Modules found:** {module_count from step 2 §4.3} ({list names}; none for a docs-only target)
{End of recap.}
- **Your intent:** {user intent from step 01}
{If scope hints from step 01:}
- **Your initial scope hints:** {hints}

Anything wrong in the analysis? Say so with your answer below."

The user's next answer may carry corrections to step 2's analysis: apply them, and show the changed findings again, before a scope decision relies on them.

### 2. Handle Docs-Only Mode (if applicable)

**If `source_type: "docs-only"`:**

"**Docs-only mode — scope is defined by documentation pages.**

You've provided these documentation URLs:
{numbered list of doc_urls with labels}

Which pages should be included in the skill? (Enter numbers, or 'all')
Any additional documentation URLs to add?"

Wait for confirmation. Then skip to section 5 (Summarize Scope Decisions) with:
- `language`: step 2 §0's `{language}` (`documentation`, unless a `language_hint` was supplied), shown again in the §5 summary and written by step 5
- `scope.type: "docs-only"`
- `scope.include`: confirmed doc URLs
- `scope.notes: "Generated from external documentation. All content is T3 confidence."`

**GATE [default: every collected doc URL]**: headless, no prompt: include every collected doc URL and skip to section 5 with the fields above. Take `scope.rationale` from `uv run {recommendScopeTypeHelper} --json '{"source_type": "docs-only", "mode": "headless"}'` (the helper resolved from `{recommendScopeTypeProbeOrder}` as §2c says), which short-circuits to `docs-only` with no tree or signals, by the §2c capture rules.

**If `source_type: "source"` (default):** Continue to scope templates below.

### 2b. Confirm Supplemental Documentation (if doc_urls collected)

**If `source_type: "source"` AND supplemental `doc_urls` were collected in step 01:**

"**Supplemental documentation URLs:**
{numbered list of collected doc_urls with labels}

These will be included as T3 external references in the skill brief.
Add, remove, or confirm these URLs."

Wait for confirmation. Record any changes to `doc_urls`. **GATE [default: keep them]**: headless keeps them as given; step 1's input gate has HEAD-checked them, so skip the check below.

HEAD-check the URLs in parallel — issue all N `curl -sI --max-time 5 {url}` calls in a **single message with N parallel Bash calls**, then process the responses together. On a 4xx/5xx, DNS failure, or timeout per URL, warn `"Could not reach {url} — {status or error}."` and offer the same correct/keep choice as step 1 §3. The check is best-effort — never HALT on a failed HEAD — but the failure must surface here so it is not discovered downstream during compilation.

**If no supplemental doc_urls were collected:** Skip this subsection.

**Scope guidance for first-time users:** A well-scoped skill covers one cohesive capability with 3-8 primary functions. If the scope includes unrelated concerns (e.g., authentication AND data visualization), suggest splitting into separate briefs. If the scope is too narrow (single utility function), suggest expanding to the surrounding capability surface.

### 2c. Offer Scope Templates

Load `{scopeTemplatesPath}` for the scope type options ([F], [M], [P], [C], [R]) and their descriptions.

**Recommend a scope type — don't present the five options as equal weight.** SKILL.md states this workflow "steers toward the smaller, sharper version when scope is unclear" — surface that opinion at decision time. Use the analysis from step 2 and the user's intent from step 1 to pick the best-fit recommendation, then present the menu with that option marked as the suggested default.

**Resolve `{recommendScopeTypeHelper}`** from `{recommendScopeTypeProbeOrder}`; first existing path wins. HALT if no candidate exists.

**Delegate the recommendation to `{recommendScopeTypeHelper}`**: it reads no free text, so what the intent asks for is your judgment, passed as three signals.

**Classify the intent into signals.** Read the user's intent and scope hints from step 1 and set each signal by what they mean:

| Signal | Set it when the user | Example |
|---|---|---|
| `wants_wiring_pattern` (`true`/`false`) | wants the skill to teach how an app, starter, template or example wires its parts together (IPC, build config, an integration), not a library's API | "skill the IPC wiring of this Electron starter" |
| `named_module_subset` (list) | limits the skill to named modules: list them as step 2 names them, `[]` when none | "just the auth module" → `["auth"]` |
| `wants_narrow_api` (`true`/`false`) | asks for the public API, the SDK or the client surface only | "the SDK only, not the internals" |

Judge the meaning, never a word: a negated or contrasted mention sets nothing ("the whole library, not just the parser" names no module; "the client library, not a demo app or starter template" wants no wiring pattern), and a word inside another word is not that word ("Kickstarter-style" says nothing about a starter). A signal the intent does not state stays `false` (or `[]`).

**Run the recommender in one Bash call**; it reads step 2's file list through `--tree-file`, the registry files (`registry.ts`, `components.ts` and their `.tsx` forms) through `--entry-dir` and step 2's exports through `--extract-file`, never a list, a count or a file typed into the payload. For a GitHub source, the first two lines fetch the registry files the listing holds into `{run_dir}/files`:

```bash
uv run {recommendScopeTypeHelper} --tree-file "{run_dir}/tree.json" --registry-files > "{run_dir}/registry-files.txt"
uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" --patterns-file "{run_dir}/registry-files.txt"
uv run {recommendScopeTypeHelper} --tree-file "{run_dir}/tree.json" --entry-dir "{run_dir}/files" --extract-file "{run_dir}/extract.json" <<'SKF_SCOPE_PAYLOAD'
{
  "signals": {
    "wants_wiring_pattern": <true|false>,
    "named_module_subset": [<module names, or nothing>],
    "wants_narrow_api": <true|false>
  },
  "module_count": <module_count from step 2 §4.3>,
  "source_type": "source",
  "mode": "interactive"
}
SKF_SCOPE_PAYLOAD
```

- **A local source, or step 2's clone.** For a local path, or `{run_dir}/clone` when step 2 cloned the repository on `[L]`, drop the first two lines and pass the folder itself, `--entry-dir "{source_path}"`: its registry files are read in place.
- **`--extract-file`.** The script counts the distinct export names step 2 §4 wrote there: none after §4.2, where the public-api rule does not fire.
- **`mode`.** `"interactive"` lets a registry file's contents decide the component-registry rule (10+ entries or a `Component[]` annotation), so a file whose contents could not be read does not count; a headless run passes `"headless"` (the §2c GATE), which counts such a file by its presence.
- **A failed call.** The call prints one JSON object, or exits 2 and names the problem on stderr. For a payload key or signal the script does not accept, fix the payload and run the call again. For a file list it cannot read (the stderr line names the listing's problem), run the call again with `--tree-file "{run_dir}/tree-empty.json"` after `printf '[]' > "{run_dir}/tree-empty.json"`, and log `"warn: scope-type recommendation ran without the file list ({message}); the component-registry check did not run"`, adding it to `workflow_warnings[]`. Interactively, show that warning with the recommendation, so the user can still pick [C].

The script returns `{scope_type, matched_heuristic, signals, rationale}`. Use `rationale` directly — it already names the specific signals that fired.

**Persist the rationale — do not discard it.** Hold `scope_type` as `rationale.recommended` and `matched_heuristic` as `rationale.heuristic` in conversation state. After the user's §2c selection: if they accept the recommendation, set `rationale.chosen = recommended`, `accepted_recommendation = true`, `reason = <script rationale verbatim>`. If they override, set `chosen = <selected type>`, `accepted_recommendation = false`, and ask one line — *"In a sentence, why {chosen} over the recommended {recommended}?"* — storing the answer as `reason` (or `"user overrode {recommended}->{chosen}; reason not stated"` if skipped). Set `recorded = {current ISO date}`. This object becomes `scope.rationale`.

Present:

"**Recommended scope type: [{letter}] {Name}** — {rationale from the script}.

How broadly should this skill cover the library?

{full menu from `{scopeTemplatesPath}` with the recommended letter marked, e.g. '[F] Full Library', '[M] Specific Modules', '[P] Public API Only ← recommended', '[C] Component Library', '[R] Reference App'}

Press Enter to accept the recommendation, or pick a different letter."

**First-timer reassurance (interactive only, never-briefed user — the §4 first-timer rail fired in step 01).** Append one line so the harder scope-type call doesn't stall a first-timer: "The recommended type is almost always right — accept it and re-scope from step 4 if the analysis surprises you." Repeat users and headless skip this line.

Wait for user selection. Empty input or just Enter accepts the recommendation; any of the five letters overrides.

**GATE [default: the recommendation]**: **Headless:** classify the `intent` and `scope_hint` arguments into the three signals by the rules above (all `false` and `[]` when neither was supplied) and log `"headless: scope signals wants_wiring_pattern={value} named_module_subset={list} wants_narrow_api={value} (from intent/scope_hint)"`, whichever way the type is set: §3 builds a `specific-modules` boundary from `named_module_subset`. A `scope_type` argument is the type: skip the menu and the call, and set `scope.rationale` with `recommended` = that argument, `heuristic` = `"user-supplied-arg"`, `chosen` = the same type, `accepted_recommendation` false, `reason` = `"headless: scope_type supplied as argument"`, `recorded` = today's date. Otherwise run the call above with `"mode": "headless"`, accept its `scope_type` by the capture rules (no "why" question) and log `"headless: scope_type={value} from heuristic={matched_heuristic}"`.

### 3. Define Boundaries Based on Selection

Using the boundary definitions from `{scopeTemplatesPath}`, present the appropriate flow for the user's selected scope type ([F], [M], [P], [C], or [R]). Follow each type's prompts and wait for user input at each phase before proceeding. For [C], run the component library detection below first: the flow's phases 1 and 2 present what it found.

**GATE [default: the scope type's boundary default]**: **Headless:** no boundary prompt runs. When an `include` argument was supplied, use `include` and `exclude` as given, split on commas (`exclude` empty when absent). Otherwise take the resolved scope type's default below, with the globs of an `exclude` argument, when one was supplied, added to its exclusions. Log what was chosen as `warn: headless boundary default <type>: <what was chosen>`, naming any `exclude` globs added, and add that line to `workflow_warnings[]`, so the envelope's `warnings` names the boundary nobody confirmed.

| Scope type | Headless default when `include` is absent |
|---|---|
| `full-library` | One module include per module step 2 §4.3 picked, and the default exclusions |
| `public-api` | One include per public API file (below), and the default exclusions |
| `component-library` | The `full-library` default; `scope.registry_path` and `scope.demo_patterns` from the component library detection below, each demo pattern also added to the exclusions; every design system variant kept in `scope.ui_variants` |
| `specific-modules` | One module include per module `named_module_subset` names, and the default exclusions. When it names none and the recommender matched `specific-modules-count` (the module count alone), switch to `full-library` and its default, and record the switch in `scope.rationale`: `chosen` `full-library`, `accepted_recommendation` false, `reason` `"headless: specific-modules came from the module count alone and no module was named; full-library boundaries used"`. When it names none and the type came from a `scope_type` argument, halt as below |
| `reference-app` | None: only the caller knows the pattern surface. Halt as below (step 1's input gate already halted a `scope_type=reference-app` argument with no `include`, so this is a type the recommender picked) |

- **A module include** is `<path>/**`, where `<path>` is the module's `path` in `{run_dir}/snapshot.json` (its `workspaces` or `module_candidates` entry, or the entry of `{run_dir}/package-snapshot.json` when §4.3 picked from it): repo-relative, with any workspace prefix already in it. For Maven and Gradle it is the §4.1 `modules` entry, prefixed with `{monorepo_workspace}/` when step 2 picked a workspace. A `named_module_subset` name maps to the §4.3 module it names. With no module picked, the include is `{monorepo_workspace}/**` when step 2 picked a workspace (§3b), else `**`.
- **The default exclusions** are the Full Library template's test globs (`**/*.test.*`, `**/*.spec.*`, `**/test/**`, `**/tests/**`) and build globs (`**/dist/**`, `**/build/**`, `**/target/**`). The template's configuration and documentation exclusions name no glob, and the module includes already leave the root configuration files and the docs folders out.
- **The public API files** are the files that define the names the package's entry points export. Run §3c's recipe runner (its helper, source folder, clone and clone removal) with the `full-library` default as its globs and `-o "{run_dir}/public-api.json"`, then print the file of each public name, an entry point's own definitions and the files its re-exports lead to:

  ```bash
  uv run python -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); print("\n".join(sorted({p["file"] for p in d["entry_point_diff"]["public"] if p.get("file")})))' "{run_dir}/public-api.json"
  ```

  At Quick tier, when the runner exits 1 to 3 or the clone fails, or when it prints no file, take the `full-library` default instead and give the reason in the warn line: `warn: headless boundary default public-api: full-library boundaries ({the reason})`.
- **Component library detection** (scope type `component-library`, interactive or headless). Resolve `{detectRegistryHelper}` from `{detectRegistryProbeOrder}` (first existing path wins) and, from `{project-root}`, list the demo files and score the registry candidates of step 2's file list. For a GitHub source, the second and third lines fetch the candidates into `{run_dir}/files` and `<source folder>` is `{run_dir}/files`; for a local source or step 2's clone, drop those two lines and pass `{source_path}`:

  ```bash
  uv run {detectRegistryHelper} demo --files-from "{run_dir}/tree.json"
  uv run {detectRegistryHelper} registry --files-from "{run_dir}/tree.json" --candidates-only > "{run_dir}/registry-candidates.txt"
  uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" --patterns-file "{run_dir}/registry-candidates.txt"
  uv run {detectRegistryHelper} registry --files-from "{run_dir}/tree.json" --source-root "<source folder>"
  ```

  `demo` prints `patterns[]` (each glob with its `files` count and a `sample`), `excluded` and `directories`; `registry` prints `selected`, `headless_accept` and `candidates[]`, each with its `score` out of 9 and its `entry_count` (`uv run {detectRegistryHelper} --help` gives the rules). **Headless:** `scope.registry_path` is the recommender's `signals.registry_path` when §2c's call returned one, else `selected` when `headless_accept` is true (create-skill asks about a lower score), else unset; `scope.demo_patterns` is every `patterns[]` glob. When a command exits non-zero, or no candidate path resolves, add `warn: component library detection skipped ({its stderr, or skf-detect-registry.py is missing})` to `workflow_warnings[]` and go on without it: the [C] flow asks the user, and the headless default sets neither field.

A scope with no default emits the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-missing"` (SKILL.md Halt Contract), then HALT (exit code 2): "**A headless `{scope_type}` scope needs an `include` argument:** pass the files or folders the skill covers as comma-separated globs, or, for `specific-modules`, name the modules in `intent` or `scope_hint`."

### 3b. Monorepo Subpackage Convention

**Applies only when step 02 §1b selected a workspace (`monorepo_workspace` is set).** A subpackage skill documents one package inside a larger repository, so the source and scope fields follow a fixed convention. Express them wrong and `skf-create-skill` cannot resolve the scope globs against the cloned source:

- **`source_repo` stays the repository URL**, never the subpackage. `skf-create-skill` clones the whole repo at the pinned ref and then roots extraction at the subpackage, so the repo URL is what it clones.
- **`scope.include` / `scope.exclude` globs are repo-root-relative and subpackage-prefixed.** Step 02 rebased its analysis against `monorepo_workspace`, but the emitted globs must still carry the workspace prefix (e.g. `packages/sdk/src/**`, not `src/**`) because they resolve against the repo root, not the subpackage root.
- **Record the subpackage layout in `scope.notes`:** the subpackage root (the `monorepo_workspace` path), the published package name and version, the resolved git ref, and the local-clone directory. This is the only field that maps the repo-URL `source_repo` to the actual skilled subpackage — downstream workflows and re-forges read it to reconstruct the source layout.

Carry the `monorepo_workspace` path forward from step 02 §1b into the `scope.notes` you draft here rather than recomputing it.

### 3c. Tier-A Authoring Surface (coarse-glob monorepo subsets)

**Applies when a monorepo subpackage's `scope.include` uses coarse directory globs (`packages/foo/src/**`, `bin/**`) rather than an explicit file list.** Coarse globs also sweep in internal-only files (build scripts, state-store impls, generated config) that the package's public entry barrel never re-exports. `skf-create-skill` scores coverage against the *authoring* surface, and `skf-test-skill` re-derives that surface from the brief to guard against a deflated coverage denominator — so when the coarse-glob union is much larger than the documented export count and the brief names no narrower surface, the test gate inflates the denominator and an otherwise-complete skill scores as if it had large coverage gaps.

Head this off by capturing the authoring surface as **`scope.tier_a_include`**: the concrete source files whose named exports the package's public entry barrel (`index.ts`, `lib.rs`, `__init__.py`) actually re-exports. List the definition files, not the umbrella barrel itself: a barrel re-exports the whole package, so including it widens the surface instead of narrowing it.

- **Forge tier and above: the recipe runner traces the barrel.** It follows every re-export, `export *` and star import from the package's entry points to the file that defines each name. Resolve `{extractPublicApiHelper}` from `{extractPublicApiProbeOrder}` (first existing path wins). It reads the source on disk, at `{source_path}`: a local source, or step 2's `[L]` clone. For a GitHub source step 2 did not clone, the source folder is `{run_dir}/clone`, a clone of only the folders the globs name: step 2 §1's `[L]` clone command with `--sparse` added (and `--filter=blob:none`, which its commit-SHA form already carries), then, right after it (for a commit SHA, before its checkout), `git -C "{run_dir}/clone" sparse-checkout set "<folder>"`, one folder per `scope.include` glob (the part before its first wildcard). From `{project-root}`, run the runner over the confirmed globs, one `--include` per `scope.include` glob and one `--exclude` per `scope.exclude` glob:

  ```bash
  uv run {extractPublicApiHelper} --mode full --source-root "<source folder>" --include "<include glob>" --exclude "<exclude glob>" --language "{language}" -o "{run_dir}/tier-a.json"
  ```

  The candidates are the files that define a name an entry point passes on (`reexport_targets`), less the entry points themselves (`entry_points.files[].file`). Print them, one per line:

  ```bash
  uv run python -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); entries = {f["file"] for f in d["entry_points"]["files"]}; print("\n".join(sorted({t["file"] for t in d["reexport_targets"] if t["file"]} - entries)))' "{run_dir}/tier-a.json"
  ```

  Once the runner has run, whatever its exit, remove a clone this section made (`rm -rf "{run_dir}/clone"`).
- **Quick tier, or a runner that cannot trace** (it exits 3 when no ast-grep is installed, 1 or 2 when the scan fails), or a clone that fails (remove what it left, `rm -rf "{run_dir}/clone"`): read the entry barrel step 2 fetched and list its re-export targets by eye, and add `warn: tier-A surface listed by hand ({the reason})` to `workflow_warnings[]`.

Present the candidate list for the user to confirm or adjust (headless: keep it as it is), and store the confirmed list as `scope.tier_a_include`.

`scope.tier_a_include` does not change what gets extracted (that still follows `scope.include` / `scope.exclude`); it only pins the coverage denominator so the create-side and test-side counts agree without a mid-test hand-edit. Leave it unset when `scope.include` is already an explicit file list, or when the target is not a monorepo subset — there the coarse-glob union and the authoring surface coincide and no narrowing is needed.

### 4. Handle Language Override

{If language detection confidence was low from step 02:}

"**Language confirmation needed.**

The analysis detected **{language}** with low confidence. Is this correct, or should we set a different primary language?"

Wait for confirmation or override.

**GATE [default: the detected language]**: headless, `language_hint`, when supplied, already set the language at step 02 §3; otherwise accept the detected language and continue.

### 5. Summarize Scope Decisions

Show this summary and, when §5b applies, its question in one message, and wait once:

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

Wait for confirmation, which also answers §5b. Make adjustments if requested, and show the summary again when they change it.

**GATE [default: C]**: **Headless:** display the summary, log `"headless: scope_type={value} include={n} exclude={n} scripts_intent={value} assets_intent={value}"` and continue with no wait.

### 5b. Scripts & Assets Intent (Optional)

Asked in the §5 message. **Only ask when `scope.type` is `full-library`, `specific-modules`, `component-library`, or `reference-app` (skip for `public-api` and `docs-only`). Reference apps routinely ship wiring scripts and build-config assets: prompt for them.**

"Does this library include executable scripts (CLI tools, validation scripts, setup helpers) or static assets (config templates, JSON schemas, example configs) that should be packaged with the skill?"

- **[D] Auto-detect** from source (default) — SKF will scan for `scripts/`, `bin/`, `assets/`, `templates/`, `schemas/` directories
- **[N] None expected** — skip script/asset detection
- Or describe what you expect (free text)

Record the response as `scripts_intent` and `assets_intent` in the brief. Default to `detect` if user does not respond or skips. **GATE [default: D]**: headless takes the `scripts_intent` and `assets_intent` arguments, `detect` for either one absent.

### 5c. Draft Checkpoint (interactive only)

When the flow is interactive, load `{draftCheckpointFile}` and follow Half 2 (Checkpoint Write) again, now with this step's scope decisions, so a run interrupted between here and step 5 resumes at step 4 instead of redoing the analysis and the scope. A re-entry from step 4 `[R]` rewrites the draft with the revised scope. Headless runs and ratify runs skip this section.

### 6. Continue to Brief Confirmation

Load, read entire file, then execute {nextStepFile}. Step 4 shows the whole brief, with `[R]` back into this step and `[X]` to cancel.
