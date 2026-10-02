<!-- Config: communicate in {communication_language}. -->

# Step 1a §0c: Coexistence Gate

Loaded by `step-auto-scope.md` when a skill already holds the name or the source this run would forge: from §0c when its `matches[]` has one or more entries, and from §6 when the derived name belongs to a skill from another source, which §6 passes as the one `matches[]` entry. Each entry is `{name, active_version, source_repo, active_path, match_reason, skf_skill}`; `skf_skill` is true when SKF generated the matched skill. Only those are offered for a merge: a merge hands the skill to update-skill, which rewrites its files, and SKF changes only the skills it generated.

## MANDATORY SEQUENCE

### 4. Present the Coexistence Gate

Present the user with the coexistence decision, one bullet per `matches[]` entry (`{skill_name}` = `matches[].name`, `{version}` = `matches[].active_version`, `{source_repo}` = `matches[].source_repo`). Append " (not SKF output, merge not offered)" to the bullet of every entry whose `matches[].skf_skill` is false, and leave the `[M]erge` line out when no entry has `matches[].skf_skill` true:

```
⚠️ Existing skill(s) found for {target_name}:

  • {skill_name} (v{version}), source: {source_repo}
  [repeat for each entry in matches[]]

Actions:
  [A]longside: Create a new wiki skill with "-wiki" suffix (existing skill untouched)
  [M]erge:     Update the existing skill via US workflow (wiki data enriches it; SKF-generated skills only)
  [S]kip:      Do not create or modify any skill for this library

Choose [A/M/S]:
```

**GATE [default: A]**: in headless mode (`{headless_mode}` is true), auto-select `[A]longside` and log: "Headless: coexistence detected for {target_name}, auto-selecting [A]longside". The envelope's `coexistence` field carries the choice.

### 5. Handle the Selection

- **[A]longside:** Set `{coexistence_suffix}` to `-wiki`; the existing skill is untouched. Return to the section that loaded this file: from §0c, continue with `references/auto-docs-only.md` for a documentation URL and with §1 for every other input; from §6, go on with §6.

- **[M]erge:** Offered only for entries whose `matches[].skf_skill` is true. If more than one such entry exists, prompt the user to select which one to merge into before proceeding. Read `{matched_skill_name}` = the selected entry's `matches[].name` and `{matched_active_path}` = its `matches[].active_path`. End the run as `step-auto-scope.md` §9 says, with a redirect that signals the forger to route to the US workflow for the selected skill: write `{run_dir}/result-context.json` as

  ```json
  {"status": "redirect", "redirect_to": "US", "skill_name": "{matched_skill_name}", "skill_path": "{matched_active_path}", "mode": "auto", "coexistence": "merge", "result_contract": {"skill": "skf-analyze-source", "status": "redirect", "outputs": [], "summary": {"mode": "auto", "redirect_to": "US", "skill_name": "{matched_skill_name}"}}}
  ```

  and go to §9 of `step-auto-scope.md`. **STOP HERE: do not proceed to the docs-only sub-flow or §1.**

- **[S]kip:** End the run as `step-auto-scope.md` §9 says, with a skip: write `{run_dir}/result-context.json` as

  ```json
  {"status": "skipped", "unit_counts": {"confirmed": 0, "skipped": 1, "maybe": 0}, "mode": "auto", "coexistence": "skip", "skipped_reason": "Existing skill for {matched_skill_name}", "result_contract": {"skill": "skf-analyze-source", "status": "skipped", "outputs": [], "summary": {"mode": "auto", "skipped_reason": "Existing skill for {matched_skill_name}"}}}
  ```

  and go to §9 of `step-auto-scope.md`. **STOP HERE: do not proceed to the docs-only sub-flow or §1.**
