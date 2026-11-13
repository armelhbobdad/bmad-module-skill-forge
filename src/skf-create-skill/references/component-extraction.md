---
returnToStep: 'extract.md'
extractionPatternsData: 'references/extraction-patterns.md'
detectRegistryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-registry.py'
  - '{project-root}/src/shared/scripts/skf-detect-registry.py'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3d: Component Library Extraction

## STEP GOAL:

When `scope.type: "component-library"`, perform specialized extraction that treats the component registry as the primary API surface and props interfaces as API contracts. This step replaces the standard AST extraction flow (step 3 sections 4-4c) and returns control to step 3 section 5 (Build Extraction Inventory).

## Rules

- Focus only on extracting component catalog, props interfaces, and shared types
- Do not compile SKILL.md content (Step 05). Write only the scratch files under `{component_scan}`, Phase 4's runner JSON at `{extraction_json}`, its by-eye exports at `{read_by_eye_json}` and its sort at `{components_json}` and, in Phase 2b, the brief
- Every extracted item must have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

## MANDATORY SEQUENCE

**Prerequisite: §2b already ran.** Step-03 executes `§2b Discovered Authoritative Files Protocol` before delegating to this file. Any promoted authoritative files (`llms.txt`, `AGENTS.md`, etc.) are tracked in the `promoted_docs[]` context list and will be written to `file_entries[]` with `file_type: "doc"` by step 5 §6. Phase 1 lists them with the brief's other files (a promotion adds each to `scope.include`), and no Phase 4 recipe reads a doc, so this file needs no special handling for them. See step 3 §2b for the full flow.

### Phase 1: Demo/Example Exclusion

Before extraction, identify and exclude demo/example files to avoid inflating export counts.

Bind `{brief_file}` ← the brief file step 1 loaded: `{brief_path}`, `{forge_data_folder}/{skill-name}/skill-brief.yaml` for a skill name, or the current brief of a `--batch` run. Make a scratch folder for this step's files, from `{project-root}`, and bind `{component_scan}` ← the path it prints:

```bash
mkdir -p "{project-root}/_bmad-output/.skf-run" && mktemp -d "{project-root}/_bmad-output/.skf-run/skf-create-skill-3d-XXXXXXXX"
```

Resolve `{detectRegistryHelper}` from `{detectRegistryProbeOrder}`. It lists the files of the brief's scope under `{source_root}`, the tree extraction reads, and counts the demo files among them. From `{project-root}`, run it with one `--pattern` for each glob of the brief's `scope.demo_patterns` when it sets them:

```bash
uv run {detectRegistryHelper} demo --source-root "{source_root}" --brief "{brief_file}" [--pattern "{glob}"] --files-to "{component_scan}/files.txt" --kept-to "{component_scan}/kept.txt"
```

With no local tree (`{source_root}` is not a folder: a Quick-tier remote source, or one step 3 §2a could not read into a tree), pipe it the repository's file list, `gh api "repos/{owner}/{repo}/git/trees/{source_ref}?recursive=1" --jq '.tree[] | select(.type == "blob") | .path'`, with `--files-from -` in place of `--source-root`.

It writes the brief's files to `files.txt` and those no demo pattern matches to `kept.txt`, and prints `patterns[]` (each glob, its `files` count and a `sample`), `excluded`, `directories` and `also_matched[]`: `uv run {detectRegistryHelper} --help` describes them.

**If `scope.demo_patterns` is specified in the brief:** exclude what those patterns match, with no prompt. When `also_matched[]` is not empty, log: "Files the default demo patterns match are left in, since the brief's `scope.demo_patterns` names none of them: {each `also_matched[]` glob, its file count and its sample}. Add a glob to the brief's `scope.demo_patterns` to leave them out."

**Otherwise, when `excluded` is not 0, ask for confirmation**, since some `examples/` directories hold API-level code (`{N}` is `excluded`, `{M}` is `directories`):

"**Auto-detected {N} demo/example files** in {M} directories matching these patterns:
{for each patterns[] entry: its glob, its file count and its sample files}

Confirm exclusion? [Y/n] Or adjust patterns:"

**GATE [default: Y]**: if `{headless_mode}` is true, auto-confirm the auto-detected exclusion patterns, log "headless: auto-confirm demo/example exclusion ({N} files, {M} directories)", and record it per the Workflow Rules: stage `{"step": "component-extraction", "gate": "demo-exclusion", "decision": "Y", "value": "{N} files / {M} dirs", "rationale": "headless mode: auto-detected demo patterns accepted"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"` (step 5 §7 renders it in the evidence report's `## Auto-Decisions` table). Then proceed without waiting.

Wait for user response (interactive only). When the user adjusts the patterns, run the command again with one `--pattern` for each pattern given and use that result. On `n`, exclude nothing. Record `demo_files_excluded: {count}` in context (0 on `n`), and `demo_answer` ← the `patterns[]` globs the user confirmed or gave (none on `n`, in headless mode, or when the brief set them).

Bind `{scan_list}`, the filtered file list for the rest of this step: `{component_scan}/kept.txt` when files were excluded, else `{component_scan}/files.txt`.

**If the command exits non-zero, or no `{detectRegistryHelper}` candidate resolves:** warn "Demo exclusion and registry detection are skipped: {its stderr, or 'skf-detect-registry.py is missing, so re-install SKF'}.", exclude nothing and bind `{scan_list}` to null. Phase 2 then takes a brief's `scope.registry_path` as the registry unscored, or goes on with no registry.

### Phase 2: Registry Detection

The component registry is the primary API surface for component libraries. Score it with the helper, from `{project-root}`:

- **If the brief sets `scope.registry_path`:** `uv run {detectRegistryHelper} registry --source-root "{source_root}" --path "{scope.registry_path}"`. Its `selected` file is the registry whatever its score: continue to Phase 3 with no prompt. When `selected` is null (`candidates[0].error` says why), warn "The brief's scope.registry_path `{scope.registry_path}` could not be read ({error}): detecting the registry instead.", set `registry_path_unreadable` ← true, and run the next command.
- **Otherwise:** `uv run {detectRegistryHelper} registry --files-from "{scan_list}" --source-root "{source_root}"`.

With no local tree, first fetch the files the command reads into `{component_scan}/registry/`, each at its own relative path (`gh api "repos/{owner}/{repo}/contents/{path}?ref={source_ref}" -H "Accept: application/vnd.github.raw"`): the brief's `scope.registry_path` or a path the user gives below, else the paths `uv run {detectRegistryHelper} registry --files-from "{scan_list}" --candidates-only` prints, one per line. Then pass `--source-root "{component_scan}/registry"`.

It prints `selected` (the best qualifying candidate, or null), `headless_accept` and `candidates[]`, each with its `path`, `score` out of 9, `entry_count` and `sample` (its first entries): `uv run {detectRegistryHelper} --help` gives the candidate rules and the score rubric. When it exits non-zero, go on as when no registry was found.

**If `selected` is not null, ask for confirmation:**

"**Registry candidate detected** at `{path}` (confidence: {score}/9, {count} entries).

Sample entries:
{show the selected candidate's sample entries with id, name, category}
{if another candidate qualifies: 'Other candidates: {path} ({score}/9, {count} entries)'}

Is this the component registry? [Y/n] Or provide the correct path:"

**GATE [default: Y]**: if `{headless_mode}` is true and `headless_accept` is true: auto-confirm the `selected` candidate, log "headless: auto-confirm registry candidate `{path}` (score {score}/9)", and record it per the Workflow Rules: stage `{"step": "component-extraction", "gate": "registry-confirm", "decision": "Y", "value": "{path} score={score}/9", "rationale": "headless mode: high-confidence registry candidate auto-accepted"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. If `headless_accept` is false in headless mode, auto-reject the candidate (treat as "no registry found"), log "headless: auto-reject registry candidate `{path}` (score {score}/9), below the auto-accept threshold", record the decision the same way (`"decision": "reject-low-score"`), and fall through to the "no registry found" branch below.

Wait for user response (interactive only). On `Y`, the registry is `selected`: set `registry_answer` ← its path, with `registry_evidence` ← "score {score}/9, {count} entries". When the user gives a path instead, run the `--path` command above with it: when its `selected` is null, show its `error` and ask again; otherwise use that file, with `registry_answer` ← the path and `registry_evidence` ← "given by the user, {count} entries". On `n` with no path, no registry was found.

**If no registry was found and the brief holds no usable `scope.registry_path`:**

"**No component registry detected.** Component-library extraction works best with a registry file. Options:
- **[P]** Provide the registry file path
- **[S]** Skip registry — proceed with standard props-first extraction only"

**GATE [default: S]**: if `{headless_mode}` is true: auto-select [S] Skip (props-first extraction without registry), log "headless: no registry detected, auto-skip to props-first extraction (no usable path in brief.scope.registry_path)", and record it per the Workflow Rules: stage `{"step": "component-extraction", "gate": "provide-or-skip-registry", "decision": "S", "rationale": "headless mode: no human to provide registry path"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. The default is `[S]` rather than `[P]` because providing a path requires user input that headless cannot supply; skipping degrades gracefully to a smaller but valid extraction.

Wait for user response (interactive only). On [P], run the `--path` command above with the path given: when its `selected` is null, show its `error` and ask again; otherwise use that file, with `registry_answer` ← the path and `registry_evidence` ← "given by the user, {count} entries".

### Phase 2b: Record the Answers in the Brief

Write back only what a user answered at a gate above, never a headless auto-decision, so that a second run of the same brief asks neither question: `demo_answer`, which the brief never set, and `registry_answer`, which fills an unset `scope.registry_path` or replaces one Phase 2 could not read (`registry_path_unreadable`). **Skip this phase when neither `demo_answer` nor `registry_answer` is set.**

Resolve `{writeSkillBriefHelper}` from `{writeSkillBriefProbeOrder}` and, from `{project-root}`, pipe it each answer that is set (leave out the key of one that is not), with its amendment entries: one per glob of `demo_answer` (`action: "demo-excluded"`, `evidence`: "{files} files" from the glob's `patterns[]` entry) and one for `registry_answer` (`action: "registry-confirmed"`, `evidence`: `registry_evidence`). Every entry takes `category: "demo-and-registry"`, today's ISO `date`, `workflow: "skf-create-skill"` and a `reason`: the user's own, else "user confirmed the demo exclusion at create-skill step 3d", "user adjusted the demo patterns at create-skill step 3d", "user confirmed the detected registry at create-skill step 3d", "user gave the registry path at create-skill step 3d" or, when `registry_path_unreadable` is true, "user replaced the unreadable registry path at create-skill step 3d":

```bash
uv run {writeSkillBriefHelper} amend --target "{brief_file}" <<'SKF_BRIEF_ANSWERS'
{"demo_patterns": ["{glob}", ...], "registry_path": "{registry_answer}", "amendments": [{"path": "{glob or registry file}", "action": "{action}", "category": "demo-and-registry", "reason": "{reason}", "evidence": "{evidence}", "date": "{today ISO}", "workflow": "skf-create-skill"}, ...]}
SKF_BRIEF_ANSWERS
```

It reads the brief again (step 3 §2b may have amended it since step 1 loaded it), sets the fields, appends the entries, keeps the previous brief as `{brief_file}.bak` and writes the new one atomically. On exit 0, display: "**Recorded in the brief:** {`scope.demo_patterns` and/or `scope.registry_path`}, with a `demo-and-registry` amendment for each." When it exits non-zero, or no candidate resolves, warn "The step 3d answers were not saved to the brief ({its stderr}): the next run asks again." and continue.

### Phase 3: Parse Registry

If a registry was confirmed, bind `{registry_file}` ← its path (the brief's `scope.registry_path`, `selected` or the path the user gave) and write its entries to `{component_scan}/registry.json`, from `{project-root}`, with the `--source-root` Phase 2 used:

```bash
uv run {detectRegistryHelper} registry --source-root "{source_root}" --path "{registry_file}" --entries > "{component_scan}/registry.json"
```

Its selected candidate lists `entries[]`, one per object literal of the registry's array, each with its `line`, its `keys` and the `id`, `name`, `component`, `category`, `tags` and `description` it has. Phase 4's Step 4 call maps each entry, keyed by its `id` (else `name`, else `component`), to one `component_catalog[]` entry: its `name`, `description`, `category` and `tags`, the variants that hold its components (`available_in`) and their files (`code_paths`), and its citation, `[SRC:{registry_file}:L{line}]`, with the entry's `line`.

When the command exits non-zero, no candidate resolves, or its selected candidate lists no `entries` (the file holds no array of object literals, such as an object map), warn "The registry was not parsed: {its stderr, or 'skf-detect-registry.py is missing, so re-install SKF', or '{registry_file} holds no array of entries'}." and go on with no registry: Step 4's call reads the registry through the same script and exits 2 on one with no `entries`.

**If no registry:** proceed to Phase 4. The catalog stays empty.

### Phase 4: Props-First Extraction

Extract props interfaces as the primary API contracts, then link to components.

At Quick tier no recipe runs: read the shapes the steps below name from source, as T1-low. At Forge, Forge+ and Deep tiers, run the component-library recipes over `{scan_list}` in one call. Resolve `{extractPublicApiHelper}` from `{extractPublicApiProbeOrder}`; it writes `{extraction_json}`, which step 3 §2a bound beside the staging folder: step 3 §5's `init` seeds the inventory from it, so it sits outside the scratch folder Phase 6 removes. From `{project-root}`, create its folder (the runner creates none), remove the JSON an earlier run left there and run the runner with `{tier}` the forge tier (when `{scan_list}` is null, pass `--brief "{brief_file}"` in place of `--files-from "{scan_list}"`: the runner then lists the brief's files itself):

```bash
mkdir -p "{project-root}/_bmad-output/.skf-stage"
rm -f "{extraction_json}"
uv run {extractPublicApiHelper} --mode full --source-root "{source_root}" --files-from "{scan_list}" --recipe-set component-library --scope-type component-library --tier {tier} -o "{extraction_json}"
```

Act on the JSON's `status`, never on the exit code. **On `incomplete`**, remove the JSON and run the command once more, then act on the second run's JSON. **On `ok` or `incomplete`**, each of the `exports[]` in `{extraction_json}` is T1: it carries its `citation` (`[AST:{file}:L{line}]`), `ast_recipe`, `ast_node_type`, `export_type`, `confidence` and `extraction_method`, and Step 4's call sorts the exports by `ast_recipe`, and an export read by eye, which has none, by its `export_type` and name (a `*Props` interface read by eye is a Props contract). Read by eye, as T1-low, each file its `file_issues` lists as `syntax-errors` or `not-utf8`, where a recipe can miss an export, and, when the run is still incomplete, each file an `errors[]` item lists in `unread` (a failed call can keep some of a file's exports and lose the rest). A `no-recipes` issue is a file no recipe reads, such as a stylesheet: there is nothing to extract from it. A `missing` or `unreadable` issue is a listed file the runner could not read: record it for the evidence report as not extracted. Step 3 §5's `init` records the runner's warnings, and Gate 2 shows them: the head-cap warning when `truncated` is true (a recipe, which `recipes[]` marks, found more matches than the head cap keeps), and each `errors[]` item of an `incomplete` run (an ast-grep run failed or timed out, so its files were read by eye).

**On `no-ast-grep`, or with no JSON at `{extraction_json}`** (an input error, or no candidate resolves): load `{extractionPatternsData}`, which holds every recipe the steps below name and the forms each does not cover (Known Limitation #11), and run each of them as its AST Extraction Protocol says: its **When the Runner Cannot Run** loads the recipes' notes, the languages each runs in among them. When that section warns that the runner failed (no JSON, and a stderr line that holds `error:`), send the warning with step 3 §5's `add --field warnings`, so Gate 2 and the evidence report show it.

**Step 1 (extract Props interfaces):**

The Props contracts are the exports `react-props-interfaces` finds (`typescript` for `.ts` files, `tsx` for `.tsx` files) and, in a Vue component library, those `vue-define-props` finds in the `.vue` files (`vue-define-props-tsx` for a `<script setup lang="tsx">` block): each such match's `$NAME` is the props type of the component its `.vue` file defines. Without the runner, the Vue recipes run through the CLI with the scratch `sgconfig.yml` the Vue note in `extraction-patterns-by-hand.md` describes.

Once Step 4's call has run, for each Props contract it lists in `props_contracts`, or, when it printed no JSON, each Props contract Steps 1 and 2 found (a `*Props` interface or type, or a Vue props type):
- Extract all fields with types, optionality, and default values (for a Vue props type, from the interface or type literal it names)
- Extract JSDoc descriptions per field (if present)
- Record: interface name, fields[], source file, line number
- Provenance: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

**Step 2 (extract component exports):**

The component exports are those `react-component-functions` (its `javascript` form for `.js` and `.jsx` files), `react-component-arrow-functions` and `react-wrapped-components` (for `memo`, `forwardRef` and `lazy` components) find, and the items of a local list such as the `export { Button, buttonVariants }` that ends a shadcn/ui component file, which `js-local-exports` finds. Step 4's call sorts a local list's items by what they name: a `*Props` type among them is a Props contract (read its fields from the interface or type the list names), a value such as `buttonVariants` a shared export.

Step 4's call lists each component with its file and line. Do not document the function signature in detail (a component's contract is its Props interface: Test Skill compares the props a form writes, never its return type or wrapper).

**Step 3 (extract shared types):**

The shared types are the exports `ts-exported-types` finds: the exported interfaces, type aliases and enums, generic, `extends` and `export declare` forms included, less the Props contracts. It returns top-level exports only: a member of an `export namespace` block is not a module export.

**Step 4 (sort, link and count):**

When any export was read by eye, write those entries, as Phase 6 lists them, each with the `export_name`, `export_type`, `signature`, `params`, `return_type`, `source_file`, `source_line` and `citation` step 3 §5's `add --field exports` takes, as one JSON list to `{read_by_eye_json}` (bound in step 3 §2a), a Props contract's `params` null (Step 1 reads its fields after the call, and step 3 §5 sends them with `patch`). Then, from `{project-root}`, run `{detectRegistryHelper}`, with `--extraction` when `{extraction_json}` exists, `--exports` when you wrote `{read_by_eye_json}`, `--registry` when Phase 3's JSON lists `entries`, `--categories` only on the rerun below, and `{demo_files_excluded}` Phase 1's count (0 when it excluded nothing):

```bash
uv run {detectRegistryHelper} components [--extraction "{extraction_json}"] [--exports "{read_by_eye_json}"] [--registry "{component_scan}/registry.json"] [--categories "{component_scan}/categories.json"] --brief "{brief_file}" --demo-excluded {demo_files_excluded} --set-to "{components_json}" > "{component_scan}/components.json"
```

It sorts the exports into `props_contracts`, `components`, `shared_types` and `shared_exports`, links each Props contract to its component in `links` (its `link_method` is `naming-convention`, `co-location`, `generic-param` or `none`), maps the registry to `component_catalog` and `catalog_by_category`, and counts: `uv run {detectRegistryHelper} --help` gives the rules. It writes `component_catalog` and `component_stats` to `{components_json}`, which step 3 §5's `set` reads. Show its `warnings`. With a registry, display: "**Parsed component catalog: {N} components across {M} categories.**" ({N} the `component_catalog` entries, {M} the `catalog_by_category` rows whose `category` is not null). When it lists `unmatched_entries` (the registry entries no component joined, by name or by file name), warn "No component was found for {each of them}: their `available_in`, `code_paths` and `props` stay empty." When an entry's `category` is null, name one from the folders of its `code_paths` (from its `name` and `description` when it has none), write each as `{"<id>": "<category>"}` to `{component_scan}/categories.json`, and run the command once more with `--categories`; when that run exits non-zero, fix `categories.json` as its stderr says and run it again.

**If no `{detectRegistryHelper}` candidate resolves, or the command exits non-zero:** warn "Components were not sorted or counted: {its stderr, or 'skf-detect-registry.py is missing, so re-install SKF'}.", send the warning with step 3 §5's `add --field warnings`, and go on with no `{components_json}`: never sort, link or count by hand.

### Phase 5: Variant Consolidation

**Skip this phase unless Step 4's call printed JSON whose `variants` is not empty** (the brief's `scope.ui_variants`).

The call grouped the components by registry entry (by name with no registry), put each file in its variant, took each entry's canonical Props contract (`props`: the primary variant's, else the first variant's that has one) and counted `components_unique` and `components_total_with_variants`. For each catalog entry whose `available_in` holds 2 or more variants (with no registry, each component name whose `components` sit in 2 or more variants), compare the Props contracts `links` gives for its files, and record each variant-specific prop as a note (e.g., "Base UI variant adds `slots` prop").

Display: "**Variant consolidation: {components_unique} unique components across {variant_count} variants** ({components_total_with_variants} total including variants). Primary variant: {the `variants` entry whose `primary` is true}."

### Phase 6: Build Component Extraction Results

Step 3 §5 takes the runner's exports from `{extraction_json}` as it wrote them. Prepare what it sends on top: an entry below for each export read by eye (Quick tier, a `file_issues` file, a file an `errors[]` item lists in `unread`, or the runner's fallback), the list Step 4 writes to `{read_by_eye_json}`, and each Props interface's fields as its `params`:

**Per-export entry (for Props interfaces — primary API):**

- Interface name (e.g., `NativeLiquidButtonProps`)
- Full interface with all fields and types
- `params`: each field as `{name, type, default, optional, description}`, sent with `patch`
- Source file and line number
- Provenance citation
- Confidence tier: T1 when an ast-grep rule matched the interface, T1-low when it was read by eye
- `extraction_method`: `ast-grep` or `source-read`, the tool that produced the entry
- `ast_node_type`: the `kind` the matching recipe declares (`export_statement` for `react-props-interfaces`: the recipe matches the whole export, not the `interface_declaration` inside it), or `null` when read by eye
- `ast_recipe`: the `id` of the recipe that matched it, or `null` when read by eye

**Per-export entry (for component functions):**

- Component name
- Source file and line number
- Provenance citation
- Confidence tier, `extraction_method`, `ast_node_type` and `ast_recipe`, labeled by the tool that produced the entry as for Props interfaces above (a component `js-local-exports` found records `export_specifier`, the kind that recipe declares)

**Per-export entry (for shared types):**

- Same as standard extraction format

Each Props contract's component is its `links` row, and each catalog entry's contract its `props`. `component_stats` is Step 4's `stats_extra`, which the call wrote with `component_catalog` to `{components_json}`: step 3 §5's `set` reads that file into the inventory, where step 5 reads both for the Component Catalog section and the metadata stats.

Remove this step's scratch folder, from `{project-root}` (the `case` guard deletes nothing unless `{component_scan}` is the folder Phase 1 made):

```bash
case "{component_scan}" in "{project-root}/_bmad-output/.skf-run/skf-create-skill-3d-"*) rm -rf "{component_scan}" ;; esac
```

Display: "**Component extraction complete.** Returning to main extraction flow."

## RETURN PROTOCOL

After Phase 6 completes, return control to step 3 section 5 (Build Extraction Inventory). The extraction results from this step are merged into the standard extraction inventory format. Step-03 continues with its normal Gate 2 summary and confirmation.

Resume step 3 at its §5. If §5 is no longer in context, load `{returnToStep}` and execute from its §5 (Build Extraction Inventory) onward; never re-run its §1 to §4c, whose §2a start clean deletes the `{extraction_json}` Phase 4 wrote.
