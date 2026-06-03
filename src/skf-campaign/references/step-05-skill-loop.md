---
nextStepFile: 'step-06-batch.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
depsScript: 'scripts/campaign-deps.py'
kickoffTemplate: '{kickoffTemplatePath}'
kickoffScript: 'scripts/campaign-render-kickoff.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Skill Loop

## STEP GOAL:

Iterate skills in `dependency_graph.execution_order`, processing each Tier A skill through the full pipeline while enforcing dependency gates. Write state after each skill completes to survive context death between skills.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.current_stage` to `4`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Write state after EACH skill completes (not just at end) — context death between skills must be survivable.
- The per-skill pipeline body (§5.2) runs inline, not in a delegated subagent: AN→BS→CS→TS are nested skill activations, and a subagent cannot spawn further subagents. This is a deliberate constraint, not an oversight — inline keeps the full pipeline reachable and preserves NFR-2 (every skill's state is written before the next begins).
- If `{headless_mode}` is true, auto-proceed through confirmation gates. Dependency gate blocks default to HALT (safest — never silently skip dependencies).

## TASKS

### §1 — Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2 — Read Brief

Load `{briefFile}`. Build a lookup map from `targets[].name` to `targets[].repo_url`. HALT (exit code 8, `missing-brief`) if the brief is missing or unreadable.

### §3 — Read Directive

If `campaign.directive_path` is set in state, load the file at that path and apply its contents as campaign-wide context for all skill processing, per the directive contract in `references/campaign-directive-spec.md`. If the file is not found, continue without error (directive is optional).

### §4 — Dependency Gate Check

For each skill in `dependency_graph.execution_order`, before processing:

1. Skip Tier B skills — they are processed in step-06 via batch mode.
2. Skip skills whose status is already `"completed"`, `"failed"`, or `"skipped"` (resume support).
3. Run `uv run {depsScript} --check --state-file {stateFile} --skill {skill_name}`.
4. If `ready: true` — proceed to §5 for this skill.
5. If `ready: false` — present the blocked skill and its unmet dependencies:
   - `[S]kip` — mark skill as `"skipped"`, backup and write state, continue to next skill.
   - `[F]orce` — re-run with `--force`, proceed to §5 despite unmet deps.
   - `[H]alt` — stop the campaign loop. (Default in headless mode.)
6. **Deadlock detection:** after iterating through all remaining skills and finding none ready, present the same recovery menu as §4.5, scoped to the mutually-blocked set (this is the strictly harder situation, so it must not get worse UX than a single blocked skill):
   - List the blocked skills and their unmet dependencies.
   - `[F]orce one` — choose a skill to re-run with `--force` and resume the loop from it.
   - `[S]kip one` — choose a skill to mark `"skipped"`, backup and write state, then re-evaluate readiness.
   - `[H]alt` — stop the campaign loop with exit code 7 (`dependency-deadlock`). **Default in headless mode** (never silently force or skip a dependency). Log the chosen action to the decision log.

### §5 — Per-Skill Processing

For each ready Tier A skill:

1. **Activate** — set `status` to `"active"`, set `started_at` to current ISO-8601 with timezone. Backup and write state.
2. **Execute pipeline:**
   - **Pre-apply** — apply known workarounds before generation by running the shared pre-apply helper against the skill's working directory:
     ```
     uv run {project-root}/_bmad/skf/shared/scripts/skf-preapply.py --target-dir <skill-working-dir> --log-dir {campaignWorkspacePath}
     ```
     (During development the helper lives at `src/shared/scripts/skf-preapply.py`.) Parse `applied[]` from the JSON output and capture the list of applied workarounds. Pre-apply is best-effort: if the helper is missing or exits non-zero, log a warning and proceed — it is not a gate.
   - **Kickoff emit** — render the mechanical placeholders deterministically, then fill the three judgment slots. Run:
     ```
     uv run {kickoffScript} --state-file {stateFile} --brief-file {briefFile} --skill {skill_name} --template {kickoffTemplate} --workarounds '<JSON list of applied workarounds from pre-apply>'
     ```
     The script fills `{{campaign_name}}`, `{{current_stage}}`, `{{quality_gate_summary}}`, `{{skill_name}}`, `{{skill_tier}}`, `{{pin}}`, `{{commit_sha}}`, `{{repo_url}}`, `{{workarounds_list}}`, and `{{dependency_status_table}}` from state + brief. Then fill the three judgment slots that remain in the rendered output:
     - `{{brief_summary}}` — a concise summary of this target's brief entry (name, repo_url, tier, pin, depends_on). The per-skill brief does NOT exist yet at kickoff — BS produces it during this pipeline run (see below), so do not read `brief_path`; summarize the campaign brief's target entry instead.
     - `{{persistent_facts}}` — the campaign-wide persistent facts resolved in On Activation (literal sentences and loaded `file:` contents), as a bullet list, or "None" if empty. This is how house style/guardrails reach every skill's pipeline.
     - `{{directive_content}}` — raw content of the file at `campaign.directive_path`, or "No directive configured" if unset/missing.
     Present the completed kickoff message as the context for the skill's pipeline run.
   - **AN → BS → CS → TS** — standard forge pipeline for this skill. When BS (Brief Synthesis) produces the skill's brief, set `skills[current].brief_path` to the brief path from the BS result envelope so the field the schema declares is populated and available for resume and reporting.
   - **Doc-rot check** — grep feeder artifacts for corrections emitted during the pipeline run. Append any doc-rot findings to the skill's `workarounds_applied` array (prefixed with `[doc-rot]`) so they survive state write and are available for §6 propagation.
3. **Record results:**
   - On success: set `status` to `"completed"`, set `completed_at` to current ISO-8601 with timezone, record `quality_score`. Backup and write state.
   - On failure: set `status` to `"failed"`. Log the failure reason (the sub-skill's `halt_reason`/exit code, or "unparseable result envelope") to the decision log so `campaign status` and the report surface *why* a skill failed without the operator opening sub-skill logs. Backup and write state. Downstream skills whose `depends_on` does NOT include the failed skill continue processing normally; those that DO depend on it are blocked at §4's dependency gate.

### §6 — Propagate Findings

After each completed skill, propagate quality findings and doc-rot corrections to campaign-level tracking (`workarounds_applied`, `quality_score`).

### §7 — Loop Completion

When all Tier A skills in `execution_order` are processed (completed, failed, or skipped):

1. Set `campaign.current_stage` to `4`.
2. Set `campaign.last_updated` to current ISO-8601 with timezone.
3. Backup and write state.

## OUTPUT

Display per-skill summary: name, status, quality_score (if completed). Chain to `{nextStepFile}`.
