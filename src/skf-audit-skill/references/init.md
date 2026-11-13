---
nextStepFile: 're-index.md'
composeStepFile: 'constituent-freshness.md'
docsOnlyStepFile: 'doc-drift.md'
upstreamCheckoutFile: 'upstream-checkout.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
templateFile: '{driftReportTemplatePath}'
loadProvenanceProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-load-provenance.py'
  - '{project-root}/src/shared/scripts/skf-load-provenance.py'
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
checkWorkspaceDriftProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py'
  - '{project-root}/src/shared/scripts/skf-check-workspace-drift.py'
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Initialize Audit

## STEP GOAL:

Load the existing skill artifacts, provenance map, and forge tier configuration to establish the baseline for drift detection. Create the drift report document and present a baseline summary, stopping for the user's confirmation only when the baseline looks wrong (§7).

## Rules

- Focus only on loading skill artifacts and establishing the baseline — do not perform any diff or analysis
- Do not proceed if skill path is invalid or SKILL.md not found
- Present the baseline summary clearly, and ask for confirmation only when §7 finds a reason to doubt the baseline
- A skill is audited against the baseline it recorded: a provenance map for a skill built from source (§4), the documents' content hashes for a docs-only skill (§3). A skill that records neither stops at step 1 (`no-baseline`)

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. When `{source_tree}` is set (the [C] of `upstream-checkout.md`), first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}`, with `{sourceTreeHelper}` resolved from `{sourceTreeProbeOrder}` when it is not bound, and go on whatever it prints. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>"}`, adding `"skill_name"` once §1 named the skill, `"report_path": "{outputFile}"` once §6 wrote the report, and `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Get Skill Path

"**Audit Skill — Drift Detection**

Which skill would you like to audit? Please provide the skill name or path."

Resolve `{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}`. It chooses the version to audit and binds its paths by the Reading Workflows rules of `knowledge/version-paths.md`, the Manifest-lag guard included, so this step never walks the export manifest or the `active` link by hand.

A `skill_name` or `skill_path` the invocation supplied answers the question above, and it is not asked. When neither was supplied in an interactive run, offer the skills SKF generated: from `{project-root}`, run `uv run {skillInventoryHelper} "{skills_output_folder}"` and, above the question, list, numbered, the `name` and `active_version` of each `skills[]` entry whose `skf_skill` is true; a number answers with that skill's name. When no candidate resolves, the command fails or prints no JSON, or no entry qualifies, ask the question alone. A headless run with neither halts (Headless default below).

**If the user provides a skill name** (not a full path), run:

```bash
uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill_name} --forge-data-folder "{forge_data_folder}"
```

Log each entry of `resolve.errors` (a broken `active` link, for example), and `resolve.manifest_error` when it is set (an export manifest that cannot be read), as an Info note, then act on `reason`:

1. `manifest-and-link`, `manifest` or `link`: the export manifest or the `active` link names the version, and its package is on disk. Bind it (below).
2. `manifest-lags-link`: the `active` link names a version the export manifest has not caught up with (a writing workflow, typically update-skill, flipped the link after the last export), and the helper chose the link's version, as the Manifest-lag guard prescribes. Bind it (below) and print one Info note, filled from the `resolve` object: "Auditing `{symlink_target}`, the version the `active` link names; the export manifest still names `{active_version}`. Run `[EX] Export Skill` to reconcile the manifest, or set `skill_path` to `{skill_group}/{active_version}/{skill_name}` to audit `{active_version}` instead." No gate decides anything here, so nothing is recorded.

   Only when `paths.provenance_map.path` is null and `candidates.manifest.provenance_map` is set (the link's version has no provenance map and the manifest's has one), present the manifest-vs-symlink gate instead of the note, filled from the same object:

   "**The export manifest lags behind the `active` link.**

   | | Manifest | `active` link |
   |---|---|---|
   | Version | `{active_version}` | `{symlink_target}` |
   | Exported / forged | `{manifest_last_exported}` | `{candidates.symlink.generated_at}` |

   `{symlink_target}` has no provenance map, so **[N]** stops at §4 with no baseline to audit against; **[M]** audits `{active_version}` against its map. Options:

   - **[N] Audit the link's version ({symlink_target})**: the version the skill resolves to now, which this run cannot audit.
   - **[M] Audit the manifest's version ({active_version})**: the older version, against the provenance map it records.
   - **[X] Abort**: halt without producing a report (exit 6, `halt_reason: "user-cancelled"`, phase `init:manifest-gate`). To audit `{active_version}`, set `skill_path` to `{skill_group}/{active_version}/{skill_name}` and re-run."

   The headless log adds: `"{symlink_target} has no provenance map, so this run stops at step 1 (no-baseline): set skill_path to the {active_version} package to audit that version against its map."`

   **[N]**, the default, binds the helper's values. **[M]** runs the command above again with `--version {active_version}` and binds that run's values (its `reason` is `requested`). **GATE [default: N]**: headless mode auto-selects **[N]**, logs `"headless: the manifest names {active_version} but the active link names {symlink_target}; auditing the link's version. Run export-skill to reconcile."` and records the decision in the run sink: stage `{run_dir}/decision.json` as `{"gate": "init.manifest-lags-link", "default_action": "N", "taken_action": "N", "reason": "<the log line>", "evidence": {"manifest_version": "{active_version}", "link_version": "{symlink_target}"}}` and run `uv run {emitEnvelopeHelper} record --workflow skf-audit-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.
3. `flat-layout`: fall back to the flat path `{skills_output_folder}/{skill_name}/` (`SKILL.md` sits at the skill folder root, with no version folder yet). Check that SKF generated it before anything moves:
   - Run `uv run {skillInventoryHelper} "{skills_output_folder}" --skill {skill_name}`, and bind `{group_flat_skf}` ← `skills[0].flat_skf` and `{group_errors}` ← `skills[0].errors`.
   - **`{group_flat_skf}` is true:** run `uv run {skillInventoryHelper} migrate "{skills_output_folder}" --skill {skill_name} --forge-data-folder "{forge_data_folder}"` and show its `message` as an Info note, then run the `resolve` command above again and bind its values anew: they now name the version folder. When `migrate` exits 1, HALT as item 6 says, with its `error`.
   - **Otherwise** (`{group_flat_skf}` is false, the status is not `ok`, `skills[]` has no entry, or no helper candidate resolves): do not migrate. HALT before anything moves, with `halt_reason: "not-skf-output"` and this message: "**`{skill_name}` is not SKF output: nothing was moved.** `{skills_output_folder}/{skill_name}/SKILL.md` has no SKF marker in the `metadata.json` beside it, so SKF will not move or audit it. A shared `{skills_output_folder}` is supported: SKF leaves the skills it did not generate alone, so manage `{skill_name}` yourself. Only if `{skills_output_folder}` holds a module's own source rather than skills, set `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` to a folder of its own, move your SKF skills there and re-run `/skf-setup`." When there is another reason, show it in place of the marker sentence: `{group_errors}` when it is non-empty (for example, the folder is a link, which SKF never moves), the helper's `error` when the status is not `ok`, and, when no helper candidate resolved, that SKF could not check the marker because `skf-skill-inventory.py` is missing, so re-install SKF. HALT with **exit 3**.
4. `missing`, or the helper stops with `SKILL_NOT_FOUND` or `DIR_NOT_FOUND`: no version of the skill is on disk. Take the "Skill not found" halt below, naming the skill and adding the helper's `detail` or `error`.
5. `newest-on-disk`: version folders exist, but neither the export manifest nor a working `active` link names one, and the Reading Workflows rules audit only a version one of them names. Take the "Skill not found" halt below with the helper's `detail`, and add: "Point `{skills_output_folder}/{skill_name}/active` at the version to audit, then re-run."
6. Any other error: HALT with **exit 3**, `halt_reason: "skill-not-found"`, showing the helper's message. A command that prints no JSON crashed (On Activation already checked `uv`): HALT with **exit 3**, `halt_reason: "helper-missing"`, showing its first stderr line. Nothing is written.

If no helper candidate resolves, SKF can neither choose the version nor check a flat skill's marker, and nothing moves: when `{skills_output_folder}/{skill_name}/SKILL.md` exists, take item 3's Otherwise branch; else HALT with **exit 3**, `halt_reason: "helper-missing"`, and the message "Cannot locate `skf-skill-inventory.py` at `{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py` or `{project-root}/src/shared/scripts/skf-skill-inventory.py`. Install the SKF module or run from a development checkout with `src/` present."

**If the user provides a full path** (or the `skill_path` input is set): audit the package at that path, bypassing the export manifest and the `active` link. Read the `metadata.json` in it, bind `{skill_name}` ← its `name` (else the folder's name), and run the command above with `--version {version}` from the same file (`reason` is `requested`). When the helper stops with `SKILL_NOT_FOUND` (a package outside `{skills_output_folder}` that the manifest does not list), bind these values from the same file instead: `{audited_version}` ← that `version`, `{audited_version_reason}` ← `requested`, `{forge_version}` ← `{forge_data_folder}/{skill_name}/{version}` (the version folder `knowledge/version-paths.md` defines), and `{provenanceMap}` ← `{forge_version}/provenance-map.json` when that file exists, else null. A `metadata.json` that is missing or names no `version` leaves no version to audit: take the "Skill not found" halt below.

**Bind** the audited version from the `resolve` object, so every later step reads and writes one version folder:

- `{audited_version}` ← `chosen_version`
- `{audited_version_reason}` ← `reason`
- `{manifest_version}` ← `active_version`, kept only when it differs from `chosen_version` (else null)
- `{resolved_skill_package}` ← `skill_package` (a full path keeps the path as given)
- `{forge_version}` ← `forge_version`: the audited version's folder in the forge data, where §4 reads the provenance map and every step writes its outputs (the drift report, the extraction snapshot, the stage data and the result files)
- `{provenanceMap}` ← `paths.provenance_map.path`: the version folder's map when it exists, else the flat copy an older skill may still keep in `{forge_data_folder}/{skill_name}/`, else null

§6 writes the audited version, its reason and the manifest's version into the drift report's frontmatter, and step 6 shows them in its Provenance table.

**Validate:** Check that `SKILL.md` exists at the resolved path.
- If missing → "Skill not found at `{resolved_skill_package}`. Check the path and try again."
- If found → Continue

**Headless default** (when `{headless_mode}`): nothing is asked again, and every §1 halt uses phase `init:skill-path`. With neither `skill_name` nor `skill_path`, HALT with **exit 2**, `halt_reason: "input-missing"`, with no `skill_name` in the payload. The "Skill not found" case halts with **exit 3**, `halt_reason: "skill-not-found"`, in place of asking again.

### 2. Load Forge Tier

Resolve `{forgeTierRwHelper}` from `{forgeTierRwProbeOrder}`; first existing path wins (On Activation checked that one exists). From `{project-root}`, run it once, with an unset `tier_override` input passed as an empty string:

```bash
uv run {forgeTierRwHelper} effective --target "{sidecar_path}/forge-tier.yaml" --preferences "{sidecar_path}/preferences.yaml" --tier-override="{tier_override}"
```

**Apply tier override:** the helper reads `{sidecar_path}/forge-tier.yaml` and applies the override chain: the invocation's `tier_override` input wins, then `tier_override` in `{sidecar_path}/preferences.yaml`, then the detected tier, each only when it is one of Quick, Forge, Forge+ or Deep. Act on its result:

**If found** (exit 0 with `exists` true): bind `{current_tier}` ← `tier` and the tool flags from `tools` (gh_bridge, ast_bridge, qmd_bridge: `knowledge/tool-resolution.md` gives each tool's resolution per IDE), and log the tier with its `tier_source` (`invocation`, `override` or `detected`). For each rejected value, `invocation_override_rejected` for the input (`{value}` its `invocation_override`, `{where}` `input`) and `override_rejected` for preferences.yaml (`{value}` its `tier_override`, `{where}` `preferences.yaml`), display `warn: tier_override {value} ({where}) is not one of Quick, Forge, Forge+, Deep and was ignored` and record it for the envelope: write `tier_override_ignored: {value} ({where})` to `{run_dir}/warning.txt` with a file write (the value can hold quotes), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

**If file missing** (exit 0 with `exists` false):
- "Setup-forge has not been run. Cannot determine tool availability. Run `[SF] Setup Forge` first."
- HALT with **exit 3**, `halt_reason: "forge-tier-missing"`, phase `init:forge-tier`, `"path": "{sidecar_path}/forge-tier.yaml"`.

**If it cannot be read** (exit 2 with the helper's JSON error on stderr: it does not parse, is cut short, or names no valid tier): HALT with **exit 3**, `halt_reason: "forge-tier-missing"`, phase `init:forge-tier`, `"path": "{sidecar_path}/forge-tier.yaml"`: "`{sidecar_path}/forge-tier.yaml` cannot be read: {its `message`}. Run `[SF] Setup Forge` to write it again."

**Any other exit, or no JSON:** HALT with **exit 3**, `halt_reason: "helper-missing"`, phase `init:forge-tier`, showing its first stderr line. An exit 2 with no JSON on stderr counts here: an older `skf-forge-tier-rw.py`, with no `effective` command or no `--tier-override`, exits 2 that way, so re-install SKF.

### 3. Load Skill Artifacts

Load the following from the skill directory:

**Required:**
- `SKILL.md` — The skill document to audit
- `metadata.json` — Skill metadata (version, created date, export count)

**Extract from metadata.json:**
- `name`, `version` and `generation_date`
- `source_root` — Resolved source code path used during extraction
- `source_repo`: the repository the skill was built from, which the [C] of `upstream-checkout.md` reads a newer ref of (`{source_repo}`, an empty string when the field is null or missing)

**Baseline facts.** Resolve `{loadProvenanceHelper}` from `{loadProvenanceProbeOrder}`; first existing path wins (On Activation checked that one exists). From `{project-root}`, run it once, with a null `{provenanceMap}` passed as an empty string (on §1's `SKILL_NOT_FOUND` full-path branch, `{resolved_skill_package}` is the path as given):

```bash
uv run {loadProvenanceHelper} baseline --metadata "{resolved_skill_package}/metadata.json" --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" --provenance-map "{provenanceMap}" --current-tier "{current_tier}"
```

If it exits 1, HALT with **exit 3**, `halt_reason: "provenance-invalid"`, phase `init:baseline`, showing its stderr, with `"path"` the file it names (`{resolved_skill_package}/metadata.json` or `{provenanceMap}`): metadata.json or the provenance map cannot be read. Any other non-zero exit HALTs with **exit 3**, `halt_reason: "helper-missing"`, phase `init:baseline`, showing its first stderr line: an older `skf-load-provenance.py`, with no `baseline` command, exits 2 that way, so re-install SKF. Otherwise bind from its JSON:
- `{original_tier}` ← `original_tier`: the tier the skill was compiled at, null when metadata.json records none
- `{scope_type}` ← `scope_type`: the `scope_type` metadata.json records, else the `scope.type` of `{forge_data_folder}/{skill_name}/skill-brief.yaml` when that file exists and names one (a skill whose metadata.json records no scope type is audited under its brief's), else null. When it is `public-api`, step 2 passes `--scope-type public-api` to the recipe runner and the snapshot build (`re-index.md` §3), so step 3 does not report as added an export off the public surface that create-skill and update-skill keep the skill's map to. When `brief_error` is set (a brief that is there but cannot be read), show it as an Info note
- `{docs_only_skill}` ← `docs_only_skill`: true when the `scope_type` metadata.json records, or the `source_type` an older one records, is `docs-only`, never from the brief
- `{tier_dropped}` ← `tier_dropped` and `{baseline_old}` ← `baseline_old`: §7's two doubts

Then route on `no_baseline`. **`no-doc-hashes`**: a docs-only skill has no source tree, so create-skill recorded each document it was built from in `doc_sources`, with its content hash, for step 5a to compare; here no entry of it has a `content_hash` (create-skill records null for a document it could not fetch), so nothing records the documents' state: HALT with **exit 3**, `halt_reason: "no-baseline"`, phase `init:baseline`: "**`{skill_name}` records no documentation hashes, so there is no baseline to audit it against.** Re-create it with `[CS] Create Skill`, which records them." **A docs-only skill** (`{docs_only_skill}` true) otherwise skips §4, Stack Skill Detection and §5, takes §5b's docs-only skip, and continues at §6. Every other skill continues at §4.

### 4. Load Provenance Map

Load the provenance map at `{provenanceMap}`, the path §1 bound: the audited version's map, or the flat copy an older skill may still keep.

**If `{provenanceMap}` is set:**
- Normalize the map's deterministic projections in one subprocess call, with the `{loadProvenanceHelper}` §3 resolved:

  ```bash
  uv run {loadProvenanceHelper} normalize {provenanceMap}
  ```

  Parse the emitted JSON and stash these fields in workflow context (downstream steps read them directly — no re-walk):
  - `{bounded_scan_files}` — sorted POSIX list, union of `entries[].source_file` and `file_entries[].source_file`. Step 2 `re-index.md` consumes this as the bounded scan list.
  - `{is_stack_skill}`, `{legacy_stack_provenance}` and `{compose_mode_stack}`: stack-skill flags (see Stack Skill Detection below for downstream branching). §6 records them in the drift report's frontmatter, and the later steps read them there.
  - `{source_root}`, `{baseline_commit}`, `{baseline_ref}` — used by §5 Resolve Source Path and §5b Detect Upstream Drift.
  - `{export_count}` ← `export_count`, `{provenance_generated_at}` ← `generated_at` and `{provenance_age_days}` ← `age_days`: the baseline facts §7 shows and §6 records. `age_days` counts from the map's `generated_at`, or from the file's modification time when the map has none.

  If the script exits non-zero, HALT with **exit 3**, `halt_reason: "provenance-invalid"`, phase `init:provenance`, `"path": "{provenanceMap}"`, showing its stderr: the map is structurally invalid and downstream steps cannot proceed.

**If `{provenanceMap}` is null** (no map in the version folder, nor a flat copy): the skill records no baseline, so there is nothing to diff the source against. Quick Skill writes no provenance map, and neither does a skill made outside SKF. HALT with **exit 3**, `halt_reason: "no-baseline"`, phase `init:provenance`, in either mode: "**`{skill_name}` has no provenance map, so there is no baseline to audit it against.** Run `[TS] Test Skill` to check the skill against its current source, or `[CS] Create Skill` to re-create it with the provenance map an audit needs."

### Stack Skill Detection

`{is_stack_skill}`, `{legacy_stack_provenance}` and `{compose_mode_stack}` are already resolved by the normalize call in §4: no additional walk needed. Apply the post-detection logic:

If `{compose_mode_stack}` is true (a stack whose map holds `constituents[]`: a compose-mode stack), the audit takes the compose route. Its provenance entries record the constituent skills it was composed from, not a source tree, so §5 and §5b skip, and §7 then loads `{composeStepFile}` (step 1c), which checks each constituent's freshness in place of steps 2 to 4. Comparing hashes is analysis, which this step does not do.

If `{legacy_stack_provenance}` is true: log a note that this stack uses the v1 provenance format, whose entries name no library, so step 3 diffs its exports as one list; re-compose it with `[SS]` for per-library results.

### 5. Resolve Source Path

**A compose-mode stack** (`{compose_mode_stack}`) has no source tree to resolve: skip this section, and §5b skips too.

**A code-mode stack** (`{is_stack_skill}` true, `{compose_mode_stack}` false) has no single `source_root` in its map: create-stack-skill scanned the project root and recorded each `source_file` relative to it. Bind `{source_root}` ← `{project-root}`. Its `{baseline_commit}` and `{baseline_ref}` stay null: the map records one commit per repository, which §5b's single-commit check does not compare.

**Every other skill** uses `{source_root}`, which §4's normalize call extracted. `{baseline_commit}` and `{baseline_ref}` are already populated by §4. If `{baseline_commit}` is null in the projection, fall back to `metadata.source_commit`. `{baseline_ref}` may be a tag, branch, `HEAD`, or `"local"`.

**Validate:** Confirm the source directory exists and is accessible. If it is missing or unreadable → HALT with **exit 3**, `halt_reason: "source-dir-missing"`, phase `init:source-dir`, `"path": "{source_root}"`.

### 5b. Detect Upstream Drift

**A compose-mode stack** (`{compose_mode_stack}`) has no source tree: skip this section with `upstream_fetch = "skipped: compose-mode stack"`, `audit_ref` and `audit_commit` `"(unknown)"`, `audit_ref_source = "unavailable"` and the upstream values null, and continue to §6. A docs-only skill (§3) skips it the same way, with `upstream_fetch = "skipped: docs-only skill"`.

**Otherwise**, ask the remote once, whatever the baseline: the helper decides itself when there is nothing to ask (a `baseline_ref` that is `local`, null or unset, no `baseline_commit`, a code-mode stack's per-repository commits), and still returns the audit-ref values step 6 renders. Resolve `{checkWorkspaceDriftHelper}` ← first existing path in `{checkWorkspaceDriftProbeOrder}` and, from `{project-root}`, run (a null baseline value passes as an empty string):

```bash
uv run {checkWorkspaceDriftHelper} upstream --source-root "{source_root}" --baseline-commit "{baseline_commit}" --baseline-ref "{baseline_ref}"
```

Never compare refs by hand. Bind from its JSON `latest_tag` ← `latest_tag`, `remote_head` ← `remote_head`, `{baseline_commit_short}` ← `baseline_commit_short`, `{remote_head_short}` ← `remote_head_short`, `{upstream_commit}` ← `upstream_commit` and `{upstream_commit_short}` ← `upstream_commit_short`, then act on its `status`:

- **`unchanged`**: set `upstream_fetch = "ok"`, `upstream_moved = false`, `upstream_ref = null`, and `audit_ref`, `audit_ref_source` and `audit_commit` to the JSON's values of those names (the baseline). Continue to §6.
- **`skipped`** (`skip_reason` says why: no baseline ref or commit, not a git tree, git unavailable, a baseline ref the remote no longer has, and the like): set `upstream_fetch = "skipped: {skip_reason}"`, `upstream_moved = null`, `upstream_ref = null`, and the audit-ref values from the JSON. Continue to §6.
- **`fetch-failed`** (no network, no remote, a remote that did not answer in time): log `fetch_error`, set `upstream_fetch = "failed:{fetch_error}"`, `upstream_moved = null`, `upstream_ref = null`, and the audit-ref values from the JSON. Continue to §6 without gating.
- **`moved`**: set `upstream_fetch = "ok"`, `upstream_moved = true` and `upstream_ref` ← `upstream_ref`, the ref to read instead (the newer tag, the moved tag or branch, or `HEAD`). Then load, read the full file and execute `{upstreamCheckoutFile}`: its gate decides whether this run reads `{upstream_ref}` from a private tree or stays on the baseline, binds `audit_ref`, `audit_ref_source` and `audit_commit`, and brings the run back here, to **Record for report** and §6.
- **No candidate resolves, or the command exits non-zero or prints no JSON:** set `upstream_fetch = "failed:helper-unavailable"`, `upstream_moved = null`, `upstream_ref = null`, `audit_ref` and `audit_commit` to `baseline_ref` and `baseline_commit` (`"(unknown)"` when unset) and `audit_ref_source = "baseline"`. Continue to §6 without gating.

**Record for report:** keep `audit_ref`, `audit_ref_source`, `audit_commit`, `latest_tag`, `remote_head`, `upstream_fetch`, `upstream_moved`, `upstream_ref`, `{source_tree}`, `baseline_ref` and `baseline_commit`: §6 writes them into the drift report's frontmatter, step 6 builds its Provenance section and its workflow recommendation from there, and the result envelope carries `upstream_moved` and `upstream_ref`, so readers and pipelines can tell which comparison actually ran and whether the skill's ref is behind upstream.

### 6. Create Drift Report

Create `{outputFile}` from `{templateFile}`:

- Populate frontmatter: skill_name, skill_path, source_path, forge_tier, date, user_name
- Record the run context in the frontmatter, so later steps read it from the file rather than from a session that may have been compacted: `audited_version`, `audited_version_reason` and `manifest_version` (§1); `docs_only_skill` (§3: `{docs_only_skill}`, which steps 5a and 5 read here to pick their next step); `scope_type` (§3, `{scope_type}`); `is_stack_skill`, `legacy_stack_provenance` and `compose_mode_stack` (§4's normalize call); `provenance_map` (`{provenanceMap}`), `provenance_generated_at` and `provenance_age_days` (§4); `baseline_ref`, `baseline_commit`, `audit_ref`, `audit_ref_source`, `audit_commit`, `latest_tag`, `remote_head`, `upstream_fetch`, `upstream_moved`, `upstream_ref` and `source_tree` (`{source_tree}`, the private tree every later step reads the source in) (§5b, and `upstream-checkout.md` when upstream moved). Write null for a value the run does not have. `source_path` keeps the source root the provenance map records.
- Set `stepsCompleted: ['init']`
- Fill Audit Summary skeleton with loaded baseline data

If the write fails (read-only mount, disk full, permissions denied) → HALT with **exit 4**, `halt_reason: "write-failed"`, phase `init:write-report`, `"path": "{outputFile}"`, and no `report_path` in the payload.

### 7. Present Baseline Summary (Confirm Only on Doubt)

"**Audit Baseline Loaded**

| Field | Value |
|-------|-------|
| **Skill** | {skill_name} v{audited_version} ({audited_version_reason}) |
| **Created** | {generation_date} |
| **Source** | {source_path} |
| **Forge Tier** | {current_tier} (created at {original_tier}) |
| **Provenance Age** | {provenance_age_days} days since last extraction |
| **Export Count** | {export_count} exports in provenance map |

Show `n/a` for a value the run does not have (a docs-only skill reads no provenance map).

**Analysis plan based on tier:**
- {Quick: text-diff comparison → T1-low for every export (read by eye)}
- {Forge: AST structural comparison → T1 for each export an ast-grep rule matches, T1-low for each export read by eye}
- {Forge+: AST structural comparison + CCC-assisted rename detection → the same labels as Forge}
- {Deep: AST structural + a semantic comparison → the same labels as Forge, plus `T2` from QMD or `T1-low-fallback` from the skill's files}
- {Compose-mode stack, at any tier: constituent freshness by metadata hash (step 1c), with no source re-index}
- {Docs-only skill, at any tier: each tracked document's content hash against the one recorded at compile time (step 5a), each changed document graded by step 5, with no source re-index}"

Display the summary and the plan. When neither doubt below holds, go straight on: load, read the entire file, and execute `{nextStepFile}`, or `{composeStepFile}` when `{compose_mode_stack}` is true, or `{docsOnlyStepFile}` when `{docs_only_skill}` is true (§6 already wrote the baseline and `stepsCompleted`). Either of these doubts stops the run here:

- **The tier dropped:** `{tier_dropped}` (§3) is true: the run takes steps 2 to 4 (neither a compose-mode stack nor a docs-only skill), and `{current_tier}` (§2) comes before `{original_tier}` in the order Quick, Forge, Forge+, Deep.
- **The baseline is old:** `{baseline_old}` (§3) is true: the provenance map is more than 90 days old.

On a doubt, ask, keeping the line of each that holds:

"**This baseline may mislead the audit:**
- {The tier dropped: the skill was compiled at {original_tier} and this run is at {current_tier}, so it lacks {Quick: ast-grep, so exports are read by eye / Forge: ccc, so an export moved out of the scan list reads as removed / Forge+: QMD, so no semantic diff runs}, and its drift can reflect the tools rather than the source. `[SF] Setup Forge` detects the tools again.}
- {The baseline is old: the provenance map is {provenance_age_days} days old, so the report can list the changes of many releases at once. `[US] Update Skill` (for a stack, `[SS] Create Stack Skill`) refreshes it.}

- **[C] Continue the audit** (default)
- **[X] Stop**, to refresh the baseline first"

Halt and wait for the user's answer. **[C]** loads the next file as above. **[X]** HALTs with **exit 6**, `halt_reason: "user-cancelled"`, phase `init:baseline-confirm`: "Audit stopped: `{outputFile}` holds the baseline only. Refresh it as above, then run `[AS] Audit Skill` again." On any other input, help the user, then re-ask.

**GATE [default: C]**: Baseline Confirm Gate [C/X], reached only on a doubt above. If `{headless_mode}`, continue with [C] and log: "headless: auto-continue past baseline confirmation ({each doubt that holds})". In headless mode, after that log line, record the decision in the run sink: stage `{run_dir}/decision.json` as `{"gate": "init.baseline-confirm", "default_action": "C", "taken_action": "C", "reason": "<the log line>", "evidence": {"original_tier": "{original_tier}", "current_tier": "{current_tier}", "provenance_age_days": {provenance_age_days}}}`, with JSON `null` for an `{original_tier}` that is null, and run `uv run {emitEnvelopeHelper} record --workflow skf-audit-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.
