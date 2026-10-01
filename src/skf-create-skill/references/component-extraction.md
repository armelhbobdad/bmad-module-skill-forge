---
returnToStep: 'extract.md'
extractionPatternsData: 'references/extraction-patterns.md'
# If neither path exists, Phase 1 goes on without demo exclusion or
# registry detection.
detectRegistryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-registry.py'
  - '{project-root}/src/shared/scripts/skf-detect-registry.py'
# If neither path exists, Phase 4 runs the AST Extraction Protocol instead.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# If neither path exists, Phase 2b saves no answer and the next run asks
# again.
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
- Do not compile SKILL.md content (Step 05). Write only the scratch files under `{component_scan}` and, in Phase 2b, the brief
- Every extracted item must have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

## MANDATORY SEQUENCE

**Prerequisite: §2a already ran.** Step-03 executes `§2a Discovered Authoritative Files Protocol` before delegating to this file. Any promoted authoritative files (`llms.txt`, `AGENTS.md`, etc.) are tracked in the `promoted_docs[]` context list and will be written to `file_entries[]` with `file_type: "doc"` by step 5 §6. Phase 1 lists them with the brief's other files (a promotion adds each to `scope.include`), and no Phase 4 recipe reads a doc, so this file needs no special handling for them. See step 3 §2a for the full flow.

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

With no local tree (`{source_root}` is not a folder: a Quick-tier remote source, or one step 3 §2b could not read into a tree), pipe it the repository's file list, `gh api "repos/{owner}/{repo}/git/trees/{source_ref}?recursive=1" --jq '.tree[] | select(.type == "blob") | .path'`, with `--files-from -` in place of `--source-root`.

It writes the brief's files to `files.txt` and those no demo pattern matches to `kept.txt`, and prints `patterns[]` (each glob, its `files` count and a `sample`), `excluded`, `directories` and `also_matched[]`: `uv run {detectRegistryHelper} --help` describes them.

**If `scope.demo_patterns` is specified in the brief:** exclude what those patterns match, with no prompt. When `also_matched[]` is not empty, log: "Files the default demo patterns match are left in, since the brief's `scope.demo_patterns` names none of them: {each `also_matched[]` glob, its file count and its sample}. Add a glob to the brief's `scope.demo_patterns` to leave them out."

**Otherwise, when `excluded` is not 0, ask for confirmation**, since some `examples/` directories hold API-level code (`{N}` is `excluded`, `{M}` is `directories`):

"**Auto-detected {N} demo/example files** in {M} directories matching these patterns:
{for each patterns[] entry: its glob, its file count and its sample files}

Confirm exclusion? [Y/n] Or adjust patterns:"

**GATE [default: Y]**: if `{headless_mode}` is true, auto-confirm the auto-detected exclusion patterns, log "headless: auto-confirm demo/example exclusion ({N} files, {M} directories)", and record it per the Workflow Rules: stage `{"step": "component-extraction", "gate": "demo-exclusion", "decision": "Y", "value": "{N} files / {M} dirs", "rationale": "headless mode: auto-detected demo patterns accepted", "timestamp": "{ISO}"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"` (step 5 §7 renders it in the evidence report's `## Auto-Decisions` table). Then proceed without waiting.

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

**GATE [default: Y]**: if `{headless_mode}` is true and `headless_accept` is true: auto-confirm the `selected` candidate, log "headless: auto-confirm registry candidate `{path}` (score {score}/9)", and record it per the Workflow Rules: stage `{"step": "component-extraction", "gate": "registry-confirm", "decision": "Y", "value": "{path} score={score}/9", "rationale": "headless mode: high-confidence registry candidate auto-accepted", "timestamp": "{ISO}"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. If `headless_accept` is false in headless mode, auto-reject the candidate (treat as "no registry found"), log "headless: auto-reject registry candidate `{path}` (score {score}/9), below the auto-accept threshold", record the decision the same way (`"decision": "reject-low-score"`), and fall through to the "no registry found" branch below.

Wait for user response (interactive only). On `Y`, the registry is `selected`: set `registry_answer` ← its path, with `registry_evidence` ← "score {score}/9, {count} entries". When the user gives a path instead, run the `--path` command above with it: when its `selected` is null, show its `error` and ask again; otherwise use that file, with `registry_answer` ← the path and `registry_evidence` ← "given by the user, {count} entries". On `n` with no path, no registry was found.

**If no registry was found and the brief holds no usable `scope.registry_path`:**

"**No component registry detected.** Component-library extraction works best with a registry file. Options:
- **[P]** Provide the registry file path
- **[S]** Skip registry — proceed with standard props-first extraction only"

**GATE [default: S]**: if `{headless_mode}` is true: auto-select [S] Skip (props-first extraction without registry), log "headless: no registry detected, auto-skip to props-first extraction (no usable path in brief.scope.registry_path)", and record it per the Workflow Rules: stage `{"step": "component-extraction", "gate": "provide-or-skip-registry", "decision": "S", "rationale": "headless mode: no human to provide registry path", "timestamp": "{ISO}"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`. The default is `[S]` rather than `[P]` because providing a path requires user input that headless cannot supply; skipping degrades gracefully to a smaller but valid extraction.

Wait for user response (interactive only). On [P], run the `--path` command above with the path given: when its `selected` is null, show its `error` and ask again; otherwise use that file, with `registry_answer` ← the path and `registry_evidence` ← "given by the user, {count} entries".

### Phase 2b: Record the Answers in the Brief

Write back only what a user answered at a gate above, never a headless auto-decision, so that a second run of the same brief asks neither question: `demo_answer`, which the brief never set, and `registry_answer`, which fills an unset `scope.registry_path` or replaces one Phase 2 could not read (`registry_path_unreadable`). **Skip this phase when neither `demo_answer` nor `registry_answer` is set.**

Resolve `{writeSkillBriefHelper}` from `{writeSkillBriefProbeOrder}` and, from `{project-root}`, pipe it each answer that is set (leave out the key of one that is not), with its amendment entries: one per glob of `demo_answer` (`action: "demo-excluded"`, `evidence`: "{files} files" from the glob's `patterns[]` entry) and one for `registry_answer` (`action: "registry-confirmed"`, `evidence`: `registry_evidence`). Every entry takes `category: "demo-and-registry"`, today's ISO `date`, `workflow: "skf-create-skill"` and a `reason`: the user's own, else "user confirmed the demo exclusion at create-skill step 3d", "user adjusted the demo patterns at create-skill step 3d", "user confirmed the detected registry at create-skill step 3d", "user gave the registry path at create-skill step 3d" or, when `registry_path_unreadable` is true, "user replaced the unreadable registry path at create-skill step 3d":

```bash
uv run {writeSkillBriefHelper} amend --target "{brief_file}" <<'SKF_BRIEF_ANSWERS'
{"demo_patterns": ["{glob}", ...], "registry_path": "{registry_answer}", "amendments": [{"path": "{glob or registry file}", "action": "{action}", "category": "demo-and-registry", "reason": "{reason}", "evidence": "{evidence}", "date": "{today ISO}", "workflow": "skf-create-skill"}, ...]}
SKF_BRIEF_ANSWERS
```

It reads the brief again (step 3 §2a may have amended it since step 1 loaded it), sets the fields, appends the entries, keeps the previous brief as `{brief_file}.bak` and writes the new one atomically. On exit 0, display: "**Recorded in the brief:** {`scope.demo_patterns` and/or `scope.registry_path`}, with a `demo-and-registry` amendment for each." When it exits non-zero, or no candidate resolves, warn "The step 3d answers were not saved to the brief ({its stderr}): the next run asks again." and continue.

### Phase 3: Parse Registry

If a registry was confirmed, bind `{registry_file}` ← its path (the brief's `scope.registry_path`, `selected` or the path the user gave) and list its entries, from `{project-root}`, with the `--source-root` Phase 2 used:

```bash
uv run {detectRegistryHelper} registry --source-root "{source_root}" --path "{registry_file}" --entries
```

Map each of its `entries[]` (one per object literal of the registry's array, each with its `line`, its `keys` and the `id`, `name`, `component`, `category`, `tags` and `description` it has) to one `component_catalog[]` entry:

- `id`: the entry's `id` (used for the CLI `add` command)
- `name`: display name (PascalCase), from `name` or `component`
- `description`: `description`, or empty
- `category`: `category`, or from the directory structure
- `available_in[]`: which design system variants include this component
- `code_paths[]`: source file path for each variant (from the entry's other `keys`, read at its `line` in the registry file, or from the directory structure)
- `tags[]`: `tags`, or empty
- Provenance citation: `[SRC:{registry_file}:L{line}]`, with the entry's `line`

When the command exits non-zero, or no candidate resolves, read the entries from the registry file by eye instead.

Display: "**Parsed component catalog: {N} components across {M} categories.**"

**If no registry:** Set `component_catalog: []` and proceed to Phase 4.

### Phase 4: Props-First Extraction

Extract props interfaces as the primary API contracts, then link to components.

At Quick tier no recipe runs: read the shapes the steps below name from source, as T1-low. At Forge, Forge+ and Deep tiers, run the component-library recipes over `{scan_list}` in one call. Resolve `{extractPublicApiHelper}` from `{extractPublicApiProbeOrder}` and, from `{project-root}`, run it with `{tier}` the forge tier (when `{scan_list}` is null, pass `--brief "{brief_file}"` in place of `--files-from "{scan_list}"`: the runner then lists the brief's files itself):

```bash
uv run {extractPublicApiHelper} --mode full --source-root "{source_root}" --files-from "{scan_list}" --recipe-set component-library --scope-type component-library --tier {tier} -o "{component_scan}/extraction.json"
```

**On exit 0**, each of the `exports[]` in `{component_scan}/extraction.json` is T1: it carries its `citation` (`[AST:{file}:L{line}]`), `ast_recipe`, `ast_node_type`, `export_type`, `confidence` and `extraction_method`, and the steps below sort the exports by `ast_recipe`. Read by eye, as T1-low, each file its `file_issues` lists as `syntax-errors` or `not-utf8`, where a recipe can miss an export. A `no-recipes` issue is a file no recipe reads, such as a stylesheet: there is nothing to extract from it. A `missing` or `unreadable` issue is a listed file the runner could not read: record it for the evidence report as not extracted. When `truncated` is true, a recipe (`recipes[]` marks it) found more matches than the head cap keeps: Phase 6 says so.

**On exit 1, 2 or 3, or when no candidate resolves** (1: an ast-grep run failed or timed out, so files may be unread; 3: no ast-grep the runner can run): load `{extractionPatternsData}`, which holds every recipe the steps below name, with the languages each runs in (its language notes) and the forms each does not cover (Known Limitation #11), and run each of them as its AST Extraction Protocol says.

**Step 1 (extract Props interfaces):**

The Props contracts are the exports `react-props-interfaces` finds (`typescript` for `.ts` files, `tsx` for `.tsx` files) and, in a Vue component library, those `vue-define-props` finds in the `.vue` files (`vue-define-props-tsx` for a `<script setup lang="tsx">` block): each such match's `$NAME` is the props type of the component its `.vue` file defines. Without the runner, the Vue recipes run through the CLI with the scratch `sgconfig.yml` their Vue note describes.

For each Props contract found (a `*Props` interface, or a Vue props type):
- Extract all fields with types, optionality, and default values (for a Vue props type, from the interface or type literal it names)
- Extract JSDoc descriptions per field (if present)
- Record: interface name, fields[], source file, line number
- Provenance: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

**Step 2 (extract component exports):**

The component exports are those `react-component-functions` (its `javascript` form for `.js` and `.jsx` files), `react-component-arrow-functions` and `react-wrapped-components` (for `memo`, `forwardRef` and `lazy` components) find, and the items of a local list such as the `export { Button, buttonVariants }` that ends a shadcn/ui component file, which `js-local-exports` finds. Sort a local list's items by what they name: the runner records an item's `export_type` as the kind of the declaration it names (`interface`, `type` or `enum` for a type). A type-only item (one in an `export type { ... }` list, or a `type X` specifier) is a type: one whose name ends in `Props` is a Props contract for Steps 1 and 3 (read its fields from the interface or type the list names), and any other is a shared type for Step 4. A PascalCase value item is a component, and any other value item (such as `buttonVariants`) is a shared export: record it with the shared types of Step 4.

For each component export: record name, source file, line number. Do not document the function signature in detail (it's always `(props: XProps) => JSX.Element`).

**Step 3 (link Props to components):**

Use a 3-level fallback chain:

1. **Naming convention (primary):** Match `FooProps` → `Foo` component by stripping the `Props` suffix
2. **File co-location (fallback):** If naming doesn't match, check if a Props interface and a component are defined in the same file
3. **Generic parameter (deep fallback):** Look for `ComponentProps<typeof Foo>` or similar generic patterns that reference the component

For each linked pair, record the association. For unlinked Props interfaces, include them as standalone type exports. Include an unlinked component export with a note that no Props interface was found (signature-only, T1-low confidence for API contract).

**Step 4 (extract shared types):**

The shared types are the exports `ts-exported-types` finds: the exported interfaces, type aliases and enums, generic, `extends` and `export declare` forms included, less the `*Props` interfaces Step 1 took. It returns top-level exports only: a member of an `export namespace` block is not a module export.

### Phase 5: Variant Consolidation

**Skip this phase if `scope.ui_variants` is not specified and no variant directories detected.**

When multiple design system variants exist:

1. **Group components by registry `id`** (not by filename — registry is source of truth):
   - For each `id` in `component_catalog[]`, collect all variant paths from `available_in[]` and `code_paths[]`

2. **Select canonical props definition:**
   - Use the primary variant (first in `scope.ui_variants` list) as canonical
   - If primary variant's props are unavailable, use the first available variant

3. **Detect props differences between variants:**
   - For components available in 2+ variants, compare Props interfaces
   - Record any variant-specific props as notes (e.g., "Base UI variant adds `slots` prop")

4. **Deduplicate export counts:**
   - Count unique components (by registry `id`), not total files across variants
   - Record: `components_unique: {N}`, `components_total_with_variants: {M}`

Display: "**Variant consolidation: {unique} unique components across {variant_count} variants** ({total} total including variants). Primary variant: {primary_name}."

### Phase 6: Build Component Extraction Results

Compile all extracted data into the format expected by step 3 section 5:

**Per-export entry (for Props interfaces — primary API):**

- Interface name (e.g., `NativeLiquidButtonProps`)
- Full interface with all fields and types
- Parameters: each field as name, type, required/optional, default
- Linked component name (e.g., `NativeLiquidButton`)
- Source file and line number
- Provenance citation
- Confidence tier: T1 when an ast-grep rule matched the interface, T1-low when it was read by eye
- `extraction_method`: `ast-grep` or `source-read`, the tool that produced the entry
- `ast_node_type`: the `kind` the matching recipe declares (`export_statement` for `react-props-interfaces`: the recipe matches the whole export, not the `interface_declaration` inside it), or `null` when read by eye
- `ast_recipe`: the `id` of the recipe that matched it, or `null` when read by eye

**Per-export entry (for component functions):**

- Component name
- Linked Props interface (if found)
- Source file and line number
- Provenance citation
- Confidence tier, `extraction_method`, `ast_node_type` and `ast_recipe`, labeled by the tool that produced the entry as for Props interfaces above (a component `js-local-exports` found records `export_specifier`, the kind that recipe declares)

**Per-export entry (for shared types):**

- Same as standard extraction format

**Component library aggregate counts:**

- `components_registered`: count from registry (or 0)
- `components_documented`: count of components with linked Props
- `props_interfaces_extracted`: count of `*Props` interfaces
- `components_unique`: deduplicated count (after variant consolidation)
- `demo_files_excluded`: count from Phase 1
- `design_variants`: map of variant name → component count (if variants exist)

**Store `component_catalog[]` in context** — this is consumed by step 5 for the Component Catalog section.

Remove this step's scratch folder, from `{project-root}` (the `case` guard deletes nothing unless `{component_scan}` is the folder Phase 1 made):

```bash
case "{component_scan}" in "{project-root}/_bmad-output/.skf-run/skf-create-skill-3d-"*) rm -rf "{component_scan}" ;; esac
```

Display: "**Component extraction complete.** Returning to main extraction flow." When the Phase 4 run's `truncated` was true, add: "{the recipes `recipes[]` marks truncated} stopped at the head cap of {head_cap} matches: exports past it are missing."

## RETURN PROTOCOL

After Phase 6 completes, return control to step 3 section 5 (Build Extraction Inventory). The extraction results from this step are merged into the standard extraction inventory format. Step-03 continues with its normal Gate 2 summary and confirmation.

Do not load `{returnToStep}` — the calling step (step 3) continues from where it delegated.
