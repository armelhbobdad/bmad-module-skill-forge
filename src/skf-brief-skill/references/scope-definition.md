---
nextStepFile: 'confirm-brief.md'
recommendScopeTypeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-recommend-scope-type.py'
  - '{project-root}/src/shared/scripts/skf-recommend-scope-type.py'
detectRegistryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-registry.py'
  - '{project-root}/src/shared/scripts/skf-detect-registry.py'
githubFetchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-fetch.py'
  - '{project-root}/src/shared/scripts/skf-github-fetch.py'
analyzeStepFile: 'analyze-target.md'
draftCheckpointFile: 'references/draft-checkpoint.md'
tierASurfaceFile: 'references/tier-a-surface.md'
headlessBoundaryDefaultsFile: 'references/headless-boundary-defaults.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Scope Definition

## Rules

- Do not make scope decisions unilaterally — user drives all scope choices
- Produce: scope type, include patterns, exclude patterns
- **Headless (`{headless_mode}` is true):** no section prompts. Each section's **Headless** line says what it takes instead, from the arguments step 1's input gate validated, so a headless run never waits here.
- **Re-entry from step 4 [R] revise:** prior selections (`scope.type`, `scope.include`, `scope.exclude`, `scope.notes`, `scope.tier_a_include`, `scope.rationale`, `scope.registry_path`, `scope.ui_variants`, `scope.demo_patterns`, supplemental `doc_urls`) are preserved as the current state; the three component-library fields are dropped only when this pass changes `scope.type` away from `component-library`. Re-present them at each section as the existing answer; the user only re-confirms or overrides. Do not reset to the §2c template menu unless the user explicitly asks to start scope over. When `scope.rationale` is preserved and the user changes `chosen` (the scope type) on this pass, recompute `accepted_recommendation` (`chosen == recommended`) and refresh `reason` and `recorded` per the §2c capture rules: revise in place, do not append.
- **Staged inputs.** Step 2 staged the repository in the run folder: its file list at `{run_dir}/tree.json`, the files it fetched under `{run_dir}/files/` and its exports in `{run_dir}/extract.json`. §2c and `{tierASurfaceFile}` read them there, and a GitHub file not fetched yet is fetched beside them with `{githubFetchHelper}`, resolved from `{githubFetchProbeOrder}` (first existing path wins; HALT if no candidate exists), as step 2 §1 describes.
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

These will be included as T3 external references in the skill brief: change them at step 4."

Show them in the §2c message, with no wait of their own: a URL the check below fails joins that message with its correct/keep choice, and an answer that does not take the choice up keeps the URL. **GATE [default: keep them]**: headless keeps them as given; step 1's input gate has HEAD-checked them, so skip the check below.

HEAD-check the URLs in parallel — issue all N `curl -sI --max-time 5 {url}` calls in a **single message with N parallel Bash calls**, then process the responses together. On a 4xx/5xx, DNS failure, or timeout per URL, warn `"Could not reach {url} — {status or error}."` and offer the same correct/keep choice as step 1 §3. The check is best-effort — never HALT on a failed HEAD — but the failure must surface here so it is not discovered downstream during compilation.

**If no supplemental doc_urls were collected:** Skip this subsection.

### 2c. Offer Scope Templates

Load `{scopeTemplatesPath}` for the scope type options ([F], [M], [P], [C], [R]) and their descriptions.

**Recommend a scope type.** Present the recommender's pick as the marked default, not five equal options.

**Resolve `{recommendScopeTypeHelper}`** from `{recommendScopeTypeProbeOrder}`; first existing path wins. HALT if no candidate exists.

**Delegate the recommendation to `{recommendScopeTypeHelper}`**: it reads no free text, so what the intent asks for is your judgment, passed as three signals.

**Classify the intent into signals.** Read the user's intent and scope hints from step 1 and set each signal by what they mean:

| Signal | Set it when the user | Example |
|---|---|---|
| `wants_wiring_pattern` (`true`/`false`) | wants the skill to teach how an app, starter, template or example wires its parts together (IPC, build config, an integration), not a library's API | "skill the IPC wiring of this Electron starter" |
| `named_module_subset` (list) | limits the skill to named modules: list them as step 2 names them, `[]` when none | "just the auth module" → `["auth"]` |
| `wants_narrow_api` (`true`/`false`) | asks for the public API, the SDK or the client surface only | "the SDK only, not the internals" |

Judge the meaning, never a word: a negated or contrasted mention sets nothing ("the whole library, not just the parser" names no module; "the client library, not a demo app or starter template" wants no wiring pattern), and a word inside another word is not that word ("Kickstarter-style" says nothing about a starter). A signal the intent does not state stays `false` (or `[]`).

**Run the recommender in one Bash call**; it reads step 2's file list through `--tree-file`, the registry files (`registry.ts`, `components.ts` and their `.tsx` forms) through `--entry-dir` and step 2's exports through `--extract-file`, never the file list, a registry file or the exports typed into the payload; `module_count` is the one count it carries, because which folders are modules is step 2 §4.3's judgment. For a GitHub source, the first two lines fetch the registry files the listing holds into `{run_dir}/files`:

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
- **`--extract-file`.** The script reads the `export_count` step 2 §4 wrote there (0 after §4.2, where the public-api rule does not fire).
- **`mode`.** `"interactive"` lets a registry file's contents decide the component-registry rule (10+ entries or a `Component[]` annotation), so a file whose contents could not be read does not count; a headless run passes `"headless"` (the §2c GATE), which counts such a file by its presence.
- **A failed call.** The call prints one JSON object, or exits 2 and names the problem on stderr. For a payload key or signal the script does not accept, fix the payload and run the call again. For a file list it cannot read (the stderr line names the listing's problem), run the call again with `--tree-file "{run_dir}/tree-empty.json"` after `printf '[]' > "{run_dir}/tree-empty.json"`, and log `"warn: scope-type recommendation ran without the file list ({message}); the component-registry check did not run"`: write it to `{run_dir}/warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. Interactively, show that warning with the recommendation, so the user can still pick [C].

The script returns `{scope_type, matched_heuristic, signals, rationale}`. Use `rationale` directly — it already names the specific signals that fired.

**Persist the rationale — do not discard it.** Hold `scope_type` as `rationale.recommended` and `matched_heuristic` as `rationale.heuristic` in conversation state. After the user's §2c selection: if they accept the recommendation, set `rationale.chosen = recommended`, `accepted_recommendation = true`, `reason = <script rationale verbatim>`. If they override, set `chosen = <selected type>`, `accepted_recommendation = false`, and ask one line — *"In a sentence, why {chosen} over the recommended {recommended}?"* — storing the answer as `reason` (or `"user overrode {recommended}->{chosen}; reason not stated"` if skipped). Set `recorded = {current ISO date}`. This object becomes `scope.rationale`.

Present:

"**Recommended scope type: [{letter}] {Name}** — {rationale from the script}.

How broadly should this skill cover the library?

{full menu from `{scopeTemplatesPath}` with the recommended letter marked, e.g. '[F] Full Library', '[M] Specific Modules', '[P] Public API Only ← recommended', '[C] Component Library', '[R] Reference App'}

Press Enter to accept the recommendation, or pick a different letter."

**First-brief reassurance (interactive only, when `first_brief` is true: step 1 §4 found no brief).** Append one line so the harder scope-type call doesn't stall a new user: "The recommended type is almost always right: accept it and re-scope from step 4 if the analysis surprises you." Skip it when `first_brief` is false or unset, and in a headless run.

Wait for user selection. Empty input or just Enter accepts the recommendation; any of the five letters overrides.

**GATE [default: the recommendation]**: **Headless:** classify the `intent` and `scope_hint` arguments into the three signals by the rules above (all `false` and `[]` when neither was supplied) and log `"headless: scope signals wants_wiring_pattern={value} named_module_subset={list} wants_narrow_api={value} (from intent/scope_hint)"`, whichever way the type is set: §3 builds a `specific-modules` boundary from `named_module_subset`. A `scope_type` argument is the type: skip the menu and the call, and set `scope.rationale` with `recommended` = that argument, `heuristic` = `"user-supplied-arg"`, `chosen` = the same type, `accepted_recommendation` false, `reason` = `"headless: scope_type supplied as argument"`, `recorded` = today's date. Otherwise run the call above with `"mode": "headless"`, accept its `scope_type` by the capture rules (no "why" question) and log `"headless: scope_type={value} from heuristic={matched_heuristic}"`.

### 3. Define Boundaries Based on Selection

Show the selected type's flow from `{scopeTemplatesPath}` in one message: its defaults, what detection found and each phase's question, and take the user's picks and adjustments from one answer. [F] asks nothing, so its defaults stand until step 4. For [C], run the component library detection below first: the flow's phases 1 and 2 present what it found.

**GATE [default: the scope type's boundary default]**: **Headless:** no boundary prompt runs. When an `include` argument was supplied, use `include` and `exclude` as given, split on commas (`exclude` empty when absent). Otherwise (`{headless_mode}` true and no `include` argument), load `{headlessBoundaryDefaultsFile}` and take the resolved scope type's default it gives, with the globs of an `exclude` argument, when one was supplied, added to its exclusions. Log what was chosen as `warn: headless boundary default <type>: <what was chosen>`, naming any `exclude` globs added, and record that line, so the envelope's `warnings` names the boundary nobody confirmed: write it to `{run_dir}/warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

- **Component library detection** (scope type `component-library`, interactive or headless). Resolve `{detectRegistryHelper}` from `{detectRegistryProbeOrder}` (first existing path wins) and, from `{project-root}`, list the demo files and score the registry candidates of step 2's file list. For a GitHub source, the second and third lines fetch the candidates into `{run_dir}/files` and `<source folder>` is `{run_dir}/files`; for a local source or step 2's clone, drop those two lines and pass `{source_path}`:

  ```bash
  uv run {detectRegistryHelper} demo --files-from "{run_dir}/tree.json"
  uv run {detectRegistryHelper} registry --files-from "{run_dir}/tree.json" --candidates-only > "{run_dir}/registry-candidates.txt"
  uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" --patterns-file "{run_dir}/registry-candidates.txt"
  uv run {detectRegistryHelper} registry --files-from "{run_dir}/tree.json" --source-root "<source folder>"
  ```

  `demo` prints `patterns[]` (each glob with its `files` count and a `sample`), `excluded` and `directories`; `registry` prints `selected`, `headless_accept` and `candidates[]`, each with its `score` out of 9 and its `entry_count` (`uv run {detectRegistryHelper} --help` gives the rules). **Headless:** `scope.registry_path` is the recommender's `signals.registry_path` when §2c's call returned one, else `selected` when `headless_accept` is true (create-skill asks about a lower score), else unset; `scope.demo_patterns` is every `patterns[]` glob. When a command exits non-zero, or no candidate path resolves, log `warn: component library detection skipped ({its stderr, or skf-detect-registry.py is missing})`, write it to `{run_dir}/warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, and go on without it: the [C] flow asks the user, and the headless default sets neither field.

### 3b. Monorepo Subpackage Convention

**Applies only when step 02 §1b selected a workspace (`monorepo_workspace` is set).** A subpackage skill documents one package inside a larger repository, so the source and scope fields follow a fixed convention. Express them wrong and `skf-create-skill` cannot resolve the scope globs against the cloned source:

- **`source_repo` stays the repository URL**, never the subpackage. `skf-create-skill` clones the whole repo at the pinned ref and then roots extraction at the subpackage, so the repo URL is what it clones.
- **`scope.include` / `scope.exclude` globs are repo-root-relative and subpackage-prefixed.** Step 02 rebased its analysis against `monorepo_workspace`, but the emitted globs must still carry the workspace prefix (e.g. `packages/sdk/src/**`, not `src/**`) because they resolve against the repo root, not the subpackage root.
- **Record the subpackage layout in `scope.notes`:** the subpackage root (the `monorepo_workspace` path), the published package name and version, the resolved git ref, and the local-clone directory. This is the only field that maps the repo-URL `source_repo` to the actual skilled subpackage — downstream workflows and re-forges read it to reconstruct the source layout.

Carry the `monorepo_workspace` path forward from step 02 §1b into the `scope.notes` you draft here rather than recomputing it.

**Tier-A surface.** When `monorepo_workspace` is set and `scope.include` uses coarse directory globs (`packages/foo/src/**`, `bin/**`) rather than an explicit file list, load `{tierASurfaceFile}` and follow it: it sets `scope.tier_a_include`. Otherwise leave `scope.tier_a_include` unset.

### 4. Handle Language Override

{If language detection confidence was low from step 02:}

"**Language confirmation needed.**

The analysis detected **{language}** with low confidence. Is this correct, or should we set a different primary language?"

Wait for confirmation or override.

**GATE [default: the detected language]**: headless, `language_hint`, when supplied, already set the language at step 02 §3; otherwise accept the detected language and continue.

### 5. Summarize Scope Decisions

**Noted asides.** When `scope_note_candidates` (step 1 §3.1 and §4) is not empty, append each of its lines that `scope.notes` does not already hold to `scope.notes`, each on a line of its own after the notes this step set, then clear the list, so a step 4 `[R]` pass does not add back a line the user dropped there.

Show this summary with no wait: step 4 shows the whole brief next and is the one scope confirmation, where the user changes any of it.

"**Scope Summary:**

**Type:** {Full Library / Specific Modules / Public API / Component Library / Reference App}

**Include:**
{bulleted list of include patterns}

**Exclude:**
{bulleted list of exclude patterns}

**Language:** {confirmed language}

{If any scope notes:}
**Notes:** {scope notes}

{If this section added lines from scope_note_candidates:}
**Noted in step 1:** {those lines} (drop any at step 4)"

### 5c. Draft Checkpoint (interactive only)

When the flow is interactive, load `{draftCheckpointFile}` and follow Half 2 (Checkpoint Write) again, now with this step's scope decisions, so a run interrupted between here and step 5 resumes at step 4 instead of redoing the analysis and the scope. A re-entry from step 4 `[R]` rewrites the draft with the revised scope. Headless runs and ratify runs skip this section.

### 6. Continue to Brief Confirmation

Load, read entire file, then execute {nextStepFile}. Step 4 shows the whole brief, with `[R]` back into this step and `[X]` to cancel.
