---
versionResolutionFile: 'references/version-resolution.md'
qmdRegistrationFile: 'references/qmd-collection-registration.md'
nextStepFile: 'health-check.md'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
forgeTierFile: '{sidecar_path}/forge-tier.yaml'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Write Brief

## Rules

- Focus only on writing the file — all decisions have been made
- Do not change any field values without user request — the brief was already approved
- Chains to the local health-check step via `{nextStepFile}` after completion — the user-facing success summary is NOT the terminal step
- All user-facing output in `{communication_language}`; written artifact (`description`, `notes`) in `{document_output_language}`
- **Determinism delegation:** YAML rendering, version-precedence, atomic write, the headless result envelope, and the QMD-collection registry mutation are all delegated to shared SKF scripts. The LLM's job in this step is to assemble inputs, branch on script results, and surface user-facing prose — not to render YAML, JSON envelopes, or YAML-mutation diffs in the model.

## Sequence

### 1. Reference the Schema (LLM context only)

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}`; first existing path wins. HALT if no candidate exists.

`assets/skill-brief-schema.md` and `{versionResolutionFile}` document the brief contract for human readers. The deterministic enforcement of that contract lives in `{writeSkillBriefHelper}` and its JSON Schema artifact at `src/shared/scripts/schemas/skill-brief.v1.json`. Load `assets/skill-brief-schema.md` only if you need to explain a specific field to the user during inline adjustments; otherwise skip the read: the script is the source of truth.

### 2. Resolve Output Path

Resolve the target write path:
- Primary: `{forge_data_folder}/{skill-name}/skill-brief.yaml`
- Fallback (when `{forge_data_folder}` is not set or doesn't exist): `{output_folder}/forge-data/{skill-name}/skill-brief.yaml` and inform user "**Note:** forge_data_folder not configured. Writing to {output_folder}/forge-data/{skill-name}/ instead."

The script's atomic-write helper creates parent directories as needed (`mkdir -p`) — no separate mkdir call required.

### 2b. Existing Brief — Overwrite Policy

Before writing, check whether the resolved target path already exists.

**Ratify path (`ratify_mode: true` in workflow context):** step 1 (`references/gather-intent-ratify.md`) authorized overwriting only the brief it read, `ratify_source_path`: interactively by `[R] Ratify`, then reviewed and approved at step 4, or headlessly by a `from_brief` argument. Check whether the target is that file (the same file through any path or link), each path written as it is on its line between the markers:

```bash
uv run python -c 'import os, sys; a, b = sys.stdin.read().splitlines()[:2]; print("same" if os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b) else "different")' <<'SKF_PATHS'
{resolved-target-path}
{ratify_source_path}
SKF_PATHS
```

- **`same`:** skip both gates below, with no `force` needed: log a single-line `brief-skill: ratify-mode auto-overwriting existing brief at {path}` and proceed to §3.
- **`different`** (the brief lives outside `{forge_data_folder}/<name>/`, or step 4 renamed it): an existing file at the target is another brief, so the gates below apply as on the derive route.

**Interactive (`{headless_mode}` is false), unless the ratify check printed `same`:**

If the file exists, present:

"**An existing brief was found at `{path}`.**
Overwrite it with the brief you just approved? [Y/N]"

- **[Y]** Overwrite — proceed to §3.
- **[N]** Cancel — emit a single-line stderr log `brief-skill: overwrite-cancelled at {path}` and HALT with exit code 5 (do not chain to step 6; the run produced no new artifact).

**GATE [default: HALT unless `force` was supplied]**: headless (`{headless_mode}` is true), unless the ratify check printed `same`:

If the file exists:

- If `force` was supplied as a headless argument: log `"headless: force-overwriting existing brief at {path}"` and proceed to §3.
- Otherwise: emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "overwrite-cancelled"` (SKILL.md Halt Contract), then HALT with exit code 5.

If the file does not exist, proceed normally.

### 3. Write the Brief

Assemble the brief context as a **flat** JSON object — every approved value is a top-level key, scope is split across four `scope_*` keys instead of nested, and every optional field is passed as `null` when not set rather than conditionally omitted. This eliminates the "decide what to omit" cognitive load that previously made this the most expensive HALT-typo site in the workflow:

```json
{
  "name":             "{approved skill name}",
  "target_version":   "{target_version from step 01, or null}",
  "detected_version": "{auto-detected version from step 02, or null}",
  "source_type":      "{source or docs-only}",
  "source_repo":      "{approved source repo or doc site URL}",
  "language":         "{approved language}",
  "description":      "{approved description}",
  "forge_tier":       "{Quick|Forge|Forge+|Deep}",
  "created":          "{current ISO date YYYY-MM-DD}",
  "created_by":       "{user_name}",
  "scope_type":       "{approved scope type}",
  "scope_include":    ["{approved include patterns}"],
  "scope_exclude":    ["{approved exclude patterns}"],
  "scope_notes":      "{approved scope notes or empty string}",
  "scope_rationale":  null | {"recommended":"...","chosen":"...","accepted_recommendation":true|false,"heuristic":"...","reason":"...","recorded":"YYYY-MM-DD"},
  "scope_tier_a_include": null | ["{tier-A authoring-surface patterns — from step 03 §3c capture, or hydrated on a ratify run}"],
  "scope_amendments":     null | [{"path":"...","action":"...","reason":"...","date":"YYYY-MM-DD","workflow":"..."}],
  "scope_registry_path":  null | "{a component library's registry file, from step 03's component-library flow or hydrated on a ratify run}",
  "scope_ui_variants":    null | [{"name": "...", "package": "..."}],
  "scope_demo_patterns":  null | ["{demo globs}"],
  "doc_urls":         null | [{"url": "...", "label": "...", "source": "{optional: language-registry|readme-detection|homepage|pages-api|docs-folder}"}],
  "scripts_intent":   null | "{detect|none|free-text}",
  "assets_intent":    null | "{detect|none|free-text}",
  "source_authority": null | "{official|community|internal}",
  "target_ref":       null | "{the explicit git ref: step 1's /tree/<ref>/ URL, or hydrated on a ratify run}",
  "source_ref":       null | "{resolved git ref — ratify only}"
}
```

**Ratify mode (`ratify_mode: true`):** step 2 never re-derives the version on a ratify run (an [R] pass analyzes the brief's ref but keeps the hydrated version): the version was hydrated from the upstream brief when step 1 ratified it (`references/gather-intent-ratify.md`). Add a `version_resolved` key set to that hydrated `version`; the writer's precedence checks `version_resolved` first, so this pins the output to the brief's authored version. **Without it**, `target_version` and `detected_version` are both null on a ratify run and the writer falls through to the `1.0.0` default, silently discarding the upstream version. Keep `target_version` set to the brief's `target_version` (null if it had none) so the writer's `target_version == version` invariant still holds. Likewise carry `target_ref`, `source_ref`, `scope_tier_a_include`/`scope_amendments` and `scope_registry_path`/`scope_ui_variants`/`scope_demo_patterns` from the hydrated brief, so the writer round-trips the monorepo git ref, the stratified tier-A surface, the amendment audit log, and a component library's registry file, design system variants and demo globs instead of dropping them. A derive run sets them itself, each null when nothing set it: `target_ref` from step 1's `/tree/<ref>/` URL, `scope_tier_a_include` from step 3 §3c, and the three component-library keys from step 3's component-library flow or its headless default; `source_ref` and `scope_amendments` are null.

Stage it in the run folder, then run the writer on the file with the `--from-flat` flag:

```bash
cat > "{run_dir}/brief-context.json" <<'SKF_JSON'
<the brief context above, as one JSON object>
SKF_JSON
uv run {writeSkillBriefHelper} write --target {resolved-target-path} --from-flat < "{run_dir}/brief-context.json"
```

The script translates flat → nested internally, drops the null optional fields, and runs the same schema validation and atomic write as before — pass every key always, the writer decides what reaches the YAML.

The script:
- Validates the context against `src/shared/scripts/schemas/skill-brief.v1.json`
- Applies the version-precedence rule from `{versionResolutionFile}`
- Enforces the `target_version == version` invariant (refuses to write a brief that violates it)
- Renders YAML in canonical key order (byte-stable across runs)
- Atomically writes the file via temp + fsync + rename (no half-written file ever visible)
- Emits a JSON success envelope on stdout: `{"status":"ok","brief_path":"…","version":"…","bytes":…,"warnings":[…]}`

**On script failure (non-zero exit):**
- Exit 1 (validation/invariant): The error JSON on stderr names the offending field. This indicates a context-assembly bug, not a user error — surface the message to the user, log it, then HALT.
  - Interactive: **HALT** — display the error JSON's `message` field.
  - Headless: emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-invalid"` (SKILL.md Halt Contract), then HALT (exit code 2).
- Exit 2 (I/O failure): The atomic write failed (target unwritable, disk full, etc.).
  - Interactive: **HALT** — "**Error:** Failed to write skill-brief.yaml. Check that the directory is writable and try again."
  - Headless: emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "write-failed"` (SKILL.md Halt Contract), then HALT (exit code 4).

**On success:** capture `brief_path` and `version` from the response envelope (§4b, §6 and §6b need them), and add each entry of its `warnings[]` to `workflow_warnings[]`.

**Draft cleanup.** After a successful write, remove `{forge_data_folder}/{skill-name}/.brief-draft.json` if it exists (`rm -f`, silent on absent). The draft was the checkpoint step 1 §8 and step 3 §5c wrote for the in-flight workflow window; once the brief is written it is no longer meaningful. In headless mode this rm is a no-op (drafts are only written interactively).

### 3b. QMD Collection Registration (Deep Tier Only)

**IF forge tier is Deep AND QMD tool is available:** resolve `{forgeTierRwHelper}` from `{forgeTierRwProbeOrder}` (first existing path wins), then load `{qmdRegistrationFile}` and follow the procedure there to index the brief into a QMD collection and update the forge-tier registry. If neither path exists, do not HALT: the brief is already written, and a QMD problem never fails the run. Index the brief all the same, skip the procedure's registry update, and add `QMD registry not updated: skf-forge-tier-rw.py not found` to `workflow_warnings[]`. A warning the procedure logs goes on `workflow_warnings[]` too, which is why this runs before §4b builds the envelope.

**IF forge tier is NOT Deep OR QMD is not available:** skip this section silently: do not load `{qmdRegistrationFile}`. No messaging.

### 4b. Result Envelope (Headless)

When `{headless_mode}` is true, build the run's `SKF_BRIEF_RESULT_JSON` line now, after the write (§3) and the QMD registration (§3b), so `workflow_warnings[]` holds every warning the run raised. `{emitBriefEnvelopeHelper}` was resolved at SKILL.md On Activation step 4, and `references/invocation-contract.md` defines each field. Bind `{result_envelope_line}` to the line it prints, and do not display it here: the shared health check displays it verbatim as the run's last line, the final message a `claude -p` caller reads:

```bash
uv run {emitBriefEnvelopeHelper} emit <<'SKF_BRIEF_RESULT'
{"status":"success","brief_path":"<brief_path from §3>","skill_name":"<name>","version":"<version from §3>","language":"<language>","scope_type":"<scope.type>","halt_reason":null,"mode":null,"warnings":[<workflow_warnings[] as JSON strings>]}
SKF_BRIEF_RESULT
```

The helper derives `exit_code`, checks the line against the envelope schema and prints it on stdout. If `{emitBriefEnvelopeHelper}` has no path, or the helper exits non-zero or prints no line, leave `{result_envelope_line}` empty and display its error: the brief is already written, so the run goes on.

A HALT in this step, or in steps 1 and 2, does not use this section: it emits the error envelope through the SKILL.md Halt Contract, which also gives the `unknown` placeholder for a halt before the skill name is resolved.

When `{headless_mode}` is false, skip this section silently: no envelope is emitted.

### 6. Display Success Summary

When `{headless_mode}` is true, skip this section: the envelope §4b bound is the run's result.

"**Skill brief written successfully.**

---

**File:** `{brief_path from §3 response}`
**Skill:** {name}
**Language:** {language}
**Scope:** {scope type}
**Forge Tier:** {forge tier}

---

## Next Steps

Your skill brief is ready. To compile the actual skill from this brief, run:

**create-skill** — Reads your skill-brief.yaml and compiles a complete SKILL.md with AST-backed analysis.

After compilation, you can:
- **test-skill** — Validate the compiled skill
- **export-skill** — Package the skill for distribution

---

**Brief-skill workflow complete.**"

### 6b. On-Complete Hook (pipeline integration)

If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`), invoke it now, after the brief has been written (§3) and, in a headless run, the result envelope built and bound to `{result_envelope_line}` (§4b):

```bash
{onCompleteCommand} --result-path={brief_path}
```

where `{brief_path}` is the absolute path captured from the §3 response envelope (the freshly written `skill-brief.yaml`, the stable artifact a downstream consumer chains from).

- **Never fail the workflow on hook errors:** the hook is for pipeline integration (chaining into create-skill, Slack, dashboards, CI), not for gating brief production. On a non-zero exit or a process error, display one line, `on_complete hook failed (exit {code}): {first line of its stderr}`, and continue. A headless run bound its envelope at §4b, so the envelope does not carry this line.
- On success, add nothing: the hook's own output is its report.

When `{onCompleteCommand}` is empty (bundled default), skip this section entirely: no hook is invoked. An `[auto]` run never loads this file: step-auto-validate.md §3 runs the same hook right after its envelope.

### 7. Chain to Health Check

Once the brief file has been written (and, outside headless mode, the success summary displayed), remove the run folder step 1 §1 created, with what the run staged in it (the guard keeps the command to that folder):

```bash
case "{run_dir}" in "{project-root}/_bmad-output/.skf-run/skf-brief-skill-"*) rm -rf "{run_dir}" ;; esac
```

Then load, read the full file, and execute `{nextStepFile}`. The health-check step is the true terminal step: do not stop here even though the summary reads as final.
