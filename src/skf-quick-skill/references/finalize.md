---
nextStepFile: 'health-check.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. Generated SKILL.md text in {document_output_language}. -->

# Step 6: Finalize

## STEP GOAL:

To finalize the skill by creating the active-version pointer, displaying the completion summary, and writing the result contract. Deliverables (SKILL.md, context-snippet.md, metadata.json) were already written in step 5 so that validation could run against files on disk; this step only performs the post-write finalization.

## Rules

- Do not rewrite deliverables — they were written and validated in step 5
- Create the active pointer via the shared helper — never `rm` + `ln -s` manually
- Result contract writing is mandatory (pipeline consumers depend on it)

## Steps

### 1. Create Active Pointer (atomic flip, Windows-safe)

**If `{overrides.no_active_pointer}` is true** — skip the helper invocation entirely. Log: "Active pointer: skipped per `--no-active-pointer` override." Do not update `{skill_group}/active`. Proceed to §2 with the active-pointer line omitted from the completion summary and the outputs payload.

`{skill_group}` and `{skill_package}` were computed in step 5 §1 from `{skills_output_folder}`, `{repo_name}`, and `{version}`; `{version}` was resolved from the extraction inventory. Reuse the same values here — do not recompute.

Create or update the `active` pointer at `{skill_group}/active` pointing to `{version}` using the shared atomic-flip helper. The helper acquires an `flock` on `{skill_group}/active.skf-lock`, refuses to replace a non-link at `{skill_group}/active` (protecting against accidental `rm -rf` of a real directory), and uses a rename-over-symlink pattern so the update is atomic from a concurrent reader's perspective. On Windows the helper automatically falls back to a directory junction (`mklink /J`) when `os.symlink` fails with `PRIVILEGE_NOT_HELD` / `ACCESS_DENIED` — junctions require no admin elevation and resolve identically for `skf-skill-inventory`'s consumers:

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists, skip the flip the same way `--no-active-pointer` does: log "Active pointer: skipped — atomic-write helper unavailable", omit the active-pointer line from the completion summary and outputs, and record `active_pointer: "skipped-helper-missing"` in the result-contract summary (§3) so consumers see why the pointer is absent. The deliverables are already on disk, so a missing helper degrades to "no pointer" rather than a failed run. There is no manual fallback: a hand-rolled `rm` + `ln -s` loses the helper's atomicity and non-link guard, risking a half-flipped pointer or an `rm -rf` into a real directory.

```bash
python3 {atomicWriteHelper} flip-link \
  --link {skill_group}/active \
  --target {version}
```

The helper returns non-zero (helper exit 2) if `{skill_group}/active` already exists as a real directory or file rather than a link — in that case, HARD HALT the workflow with **exit code 7 (finalize-blocked)** per the exit-code map in `references/halt-contract.md`: "Refusing to flip `{skill_group}/active` — existing path is not a symlink or junction. Investigate manually; expected a link pointing at a version directory." Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "finalize"`, `error.code: "finalize-blocked"`, `skill_package` set, `outputs` listing the deliverables already on disk from step 5). A common cause on Windows is a prior run that executed `ln -s` under git-bash without Developer Mode enabled, which silently wrote a full directory copy; remove that copy and retry.

Confirm: "Active pointer: {skill_group}/active -> {version} ({kind})" where `{kind}` is `symlink` or `junction` as returned by the helper.

### 2. Display Completion Summary

"**Quick Skill complete.**

**Skill:** {repo_name} v{version}
**Language:** {language}
**Source:** {resolved_url}
**Authority:** community
**Confidence:** {extraction confidence}
{If `scope_hint` is non-empty, add:} **Scope:** {scope_hint}

**Files written:**
- `{skill_package}/SKILL.md`
- `{skill_package}/context-snippet.md` (omit this line when `--skip-snippet` was set)
- `{skill_package}/metadata.json`
- `{skill_group}/active` -> `{version}` (omit this line when `--no-active-pointer` was set)

**Exports documented:** {count}
**Validation:** {pass / N issues (advisory)}

---

**Recommended next steps:**

1. **test-skill** (advisory) — Run cognitive completeness verification on the generated skill
2. **export-skill** — Package and distribute the skill with platform-aware context injection

**Note:** This is a best-effort community skill. For deeper analysis with AST-verified exports and provenance tracking, use the full **create-skill** workflow with a skill brief."

### 3. Result Contract

Write the result contract per `shared/references/output-contract-schema.md`: the per-run record at `{skill_package}/quick-skill-result-{YYYYMMDD-HHmmss}.json` (UTC timestamp, resolution to seconds) and a copy at `{skill_package}/quick-skill-result-latest.json` (stable path for pipeline consumers — copy, not symlink). Include `SKILL.md`, `context-snippet.md`, and `metadata.json` paths in `outputs` and export count in `summary`.

**Post-completion hook (optional).** If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`), invoke it after the result contract is finalized:

```bash
{onCompleteCommand} --skill-package={skill_package}
```

Log success/failure but never fail the workflow on a hook error — the skill is already written. The hook runs last so a git-add, registry registration, or notifier sees a complete package. When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely.

### 4. Chain to Health Check

Once the active pointer, completion summary, result contract, and any post-completion hook are done, load and execute {nextStepFile}. Do not stop here — health-check is the true terminal step even though the summary reads as final.
