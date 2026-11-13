---
nextStepFile: 'gather-intent.md'
autoBriefFile: 'references/step-auto-brief.md'
headlessArgsFile: 'references/headless-args.md'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 0: Preflight

Every run starts here, whatever its mode: §1 creates the run folder and reads the forge tier, and §1b sends the run on to the stage its mode takes.

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

Right after the bind, write the run's halt state, which every halt's `emit-halt` reads from the run folder:

```bash
cat > "{run_dir}/halt-state.json" <<'SKF_JSON'
{"interactive": <true when neither {headless_mode} nor {auto_mode} is true, else false>, "mode": <"auto" when {auto_mode} is true, else null>}
SKF_JSON
```

When On Activation step 3 kept `{customization_resolver_unavailable}`, record it next: write `customization_resolver_unavailable: {customization_resolver_unavailable}` to `{run_dir}/resolver-warning.txt` with a file write, never `echo` (the reason can hold quotes or `$( )`), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/resolver-warning.txt")"`.

`mkdir -p` succeeds on a pre-existing read-only mount, but the `printf > file` redirect actually attempts a write, which catches read-only, disk-full, and permissions-denied uniformly. **On any non-zero exit:** in a headless or `[auto]` run, emit the halt envelope first, `uv run {emitEnvelopeHelper} emit-halt --workflow skf-brief-skill --target stderr --halt-reason write-failed` (no `--run-dir`: the run folder does not exist; add `--mode auto` in an `[auto]` run), then HALT (exit code 4): `"**Error:** {forge_data_folder} or the run folder under {project-root}/_bmad-output/.skf-run/ is not writable: {captured stderr}. Verify the path exists, the mount is writable, and there is free disk space, then re-run."` When On Activation step 3 kept `{customization_resolver_unavailable}`, the command also takes `--customization-resolver-unavailable-from -` with the reason on stdin, so the line still warns that the `_bmad/custom/` overrides were not applied:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-brief-skill --target stderr --halt-reason write-failed --customization-resolver-unavailable-from - <<'SKF_REASON'
{customization_resolver_unavailable}
SKF_REASON
```

On success, continue silently to the forge-tier load below.

Read the forge tier with `{forgeTierRwHelper}`, resolved from `{forgeTierRwProbeOrder}` (first existing path wins; HALT if no candidate exists). It reads `{forgeTierFile}` and applies the `tier_override` of `{sidecar_path}/preferences.yaml` only when it names Quick, Forge, Forge+ or Deep, capital letters included. Run it from `{project-root}`:

```bash
uv run {forgeTierRwHelper} effective --target "{forgeTierFile}" --preferences "{sidecar_path}/preferences.yaml"
```

**If found** (exit 0 with `exists` true): bind `tier`, `detected_tier`, `tier_source` and `tools` from its JSON. `tier` is the tier this run works at. `tier_source` `override` is step 1 §2's "tier override was applied", and `detected_tier` is then the tier it replaced. Later sections read the tool flags from `tools` (`tools.qmd`, `tools.ccc`), never from the file. When `override_rejected` is true, display `warn: tier_override {tier_override} is not one of Quick, Forge, Forge+, Deep and was ignored: using the detected tier {detected_tier}` and record it: write that line to `{run_dir}/warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. When `preferences_error` is set, display `warn: preferences.yaml not read, so no tier_override applies: {preferences_error}` and record that line the same way, through `{run_dir}/warning.txt`. Join the lines of a multi-line message with spaces, so each warning is one line.

**If found but not usable** (exit 2, any other non-zero exit, or no JSON: a forge-tier.yaml that is corrupted or truncated, or holds no `tier` it can use):
- Display: "**Cannot read forge-tier.yaml** at `{forgeTierFile}`: `{message}`. The setup workflow can rewrite it cleanly. Until then, the brief workflow falls back to **Quick** tier (no extra tools assumed)." `{message}` is the helper's stderr `message`, else its first stderr line.
- Write `warn: cannot read forge-tier.yaml at {forgeTierFile}, so the run falls back to Quick tier: {message}`, its lines joined the same way, to `{run_dir}/warning.txt` with a file write, never `echo`, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.
- Continue with `tier = "Quick"`, `tools = {}` and `tier_source: "fallback-corrupted-config"`, which later steps read for diagnostics. Do not HALT.

**If not found** (exit 0 with `exists` false): emit the halt envelope first, `uv run {emitEnvelopeHelper} emit-halt --workflow skf-brief-skill --run-dir "{run_dir}" --target stderr --halt-reason forge-tier-missing`, then HALT (exit code 3): "**Cannot proceed.** forge-tier.yaml not found at `{forgeTierFile}`. Run the **setup** workflow first to configure your forge tier (Quick/Forge/Forge+/Deep)."

### 1b. Route by Mode

The first route that applies runs, and it leaves this file:

- **`{auto_mode}` is true** (a pipeline's `BS[auto]`): read `brief_path` from the pipeline data context (the forger passes it from AN's `SKF_ANALYZE_RESULT_JSON` `brief_paths[]`). If `brief_path` is not available, emit the halt envelope first, `uv run {emitEnvelopeHelper} emit-halt --workflow skf-brief-skill --run-dir "{run_dir}" --target stderr --halt-reason input-missing`, then HARD HALT (exit code 2): "**Auto mode requires `brief_path` in pipeline context: AN must run before BS[auto].**"
  Read `source_repo` from the pipeline data context too (the target the forger forwards), else from the upstream brief. Display "**Auto mode activated: bypassing the interactive brief workflow.**", then load, read fully, and execute `{autoBriefFile}`.
- **`{headless_mode}` is true:** load, read fully, and execute `{headlessArgsFile}`. Its input gate validates the arguments before any later section uses them, then continues at step 2, or ratifies the brief a `from_brief` argument names.
- **Otherwise** the run is interactive: load, read fully, and execute `{nextStepFile}` (gather-intent.md) at its §2.
