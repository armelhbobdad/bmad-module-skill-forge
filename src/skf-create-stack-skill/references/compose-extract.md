---
nextStepFile: 'compose-pairs.md'
enumerateStackSkillsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-enumerate-stack-skills.py'
  - '{project-root}/src/shared/scripts/skf-enumerate-stack-skills.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
bundleFile: '{run_dir}/extraction-bundle.json'
stackInventoryFile: '{run_dir}/stack-inventory.json'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Read the Constituent Skills

## STEP GOAL:

For each confirmed skill, take its exports, tier and hash from the inventory helper, read its description keywords, usage patterns and signatures through a subagent, and write them to the extraction bundle.

## Rules

- Take each constituent's exports, tier and hash from `skf-enumerate-stack-skills.py`
- Keep each constituent's SKILL.md out of this context: its subagent (§2) returns only the fields §3 writes, and with no subagent support §2 keeps only those fields

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "compose", "stack_libraries": ["<confirmed library>", ...]}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

**Extraction bundle.** What this step reads goes to `{bundleFile}`, so no later step works from memory: step 5 reads each skill's tier, `signatures` and `description_keywords` there and adds the pairs it keeps, step 6 compiles from it, and step 7 writes the reference files, `metadata.json` and the provenance map from it. It is one JSON object, written with the run's other files in `{run_dir}`: `{"mode": "compose", "scope": ["<confirmed skill>"], "per_library_extractions": [<one §3 entry per confirmed skill>], "failed": [], "integrations": [], "cross_cutting": []}`. `scope` is step 3's `confirmed_dependencies`; step 5 fills `integrations` and `cross_cutting`.

### 1. Resolve the Constituents

**Re-resolve at step 4 entry:** a concurrent write could have advanced a skill's version between step 2 and step 4. Re-resolve each confirmed skill from this step's helper result below: its `bundle_entries[]` entry gives the fresh `skill_package_path` (`{skills_output_folder}/{path}`), and the `skills[]` entry whose `name` is its `skill_dir` the fresh `metadata_hash`. **The provenance anchor is the hash of the package this step reads**: step 2's value, unless the package changed since. When the `metadata_hash` diverges from the value step 2 stored, append a `workflow_warnings[]` entry (`step: "step-04"`, `severity: "warn"`, `code: "constituent-changed"`, `message`: "constituent '{skill_name}' changed between step 2 and step 4: using fresh values") and replace the workflow-state entry. If `bundle_entries_missing[]` names a confirmed skill, it has no SKF package now: HALT (exit 3, `halt_reason: "resolution-failure"`, phase `compose-extract:constituent-gone`) with "constituent `{skill_dir}` is no longer an SKF skill package: re-run [SS]."

Use `skill_package_path` directly: it points to the package the helper resolved.

**Exports resolution order, script-driven:** Do NOT walk per-skill `metadata.json` → `references/` → SKILL.md by hand. Invoke the helper once at step entry to compute the full inventory for every confirmed skill in one deterministic call:

**Resolve `{enumerateStackSkillsHelper}`** from `{enumerateStackSkillsProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `compose-extract:enumerate`) with "**Cannot proceed.** `skf-enumerate-stack-skills.py` is missing, so no constituent's exports can be read. Re-install SKF, then re-run."

```bash
uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --bundle-entries "<names>" > "{stackInventoryFile}"
```

`<names>` are the confirmed skills' `skill_dir`s, comma-separated. Its JSON, in `{stackInventoryFile}`, has the form:

```json
{
  "skills": [
    {
      "name": "<skill-name>",
      "path": "<rel-to-skills-root, forward-slash>",
      "exports": ["..."],
      "exports_source": "metadata|references|skill-md|unknown",
      "confidence": "T1|T2|T1-low",
      "evidence_tier": "T1|T1-low|T2|T3",
      "metadata_hash": "sha256:..."
    }
  ],
  "cycles": ["<skill-name>"],
  "warnings": ["<text>"],
  "not_skf_output": ["<skill-name>"],
  "bundle_entries": [
    {
      "library": "<skill-name>",
      "skill_dir": "<skill-name>",
      "skill_package_path": "<skills_output_folder>/<path>",
      "version": "<version>",
      "source_authority": "official|community|internal|null",
      "exports": ["..."],
      "exports_source": "metadata|references|skill-md|unknown",
      "confidence": "<its evidence_tier>"
    }
  ],
  "bundle_entries_missing": ["<skill-name>"]
}
```

This step reads that JSON from `{stackInventoryFile}`: each constituent's exports come from it, never from memory or from re-reading its `SKILL.md`, `metadata.json` or `references/`. Append to `workflow_warnings[]` the `warnings[]` entries that name a confirmed skill (each starts with `<skill_dir>: `, e.g. `"<skill-name>: no exports found via any resolution path"`). If `cycles[]` names a confirmed skill, a composes-cycle makes the stack unbuildable: HALT (exit 3, `halt_reason: "resolution-failure"`, phase `compose-extract:cycle`) with "composes cycle among the confirmed skills: {the `cycles[]` names}."

### 2. Read Each Constituent

Read each constituent's `SKILL.md` through its own subagent, so this context holds only what the subagent returns: launch one per confirmed skill, at most five in one message, each with `run_in_background: false`, and wait for every one before you launch more. Tell each to stop and return what it has after about 20 tool calls. With no subagent support, read them one at a time here and keep only the fields below. Give each its skill's `skill_package_path` (§1 refreshed it) and the export names its `{stackInventoryFile}` entry lists. It reads that package's `SKILL.md`, and its `references/` for a listed export whose signature `SKILL.md` does not give, and returns only:

```json
{"library": "<skill_dir>", "description_keywords": ["<a domain term its description names, such as orm or validation, never a language>"], "usage_patterns": ["<pattern> (<the file:line it cites>)"], "signatures": {"<listed export>": "<its signature as the package writes it>"}}
```

When a subagent returns nothing usable, that skill's `description_keywords` and `usage_patterns` are `[]` and its `signatures` `{}`: append a `workflow_warnings[]` entry (`step: "step-04"`, `severity: "warn"`, `code: "constituent-read-failed"`, `message`: the skill and why). Its exports still come from §1.

### 3. Write the Bundle

Build a `per_library_extractions[]` entry for each confirmed skill: its `bundle_entries[]` entry in `{stackInventoryFile}` as it stands, whose `confidence` is the skill's `evidence_tier`, the library's tier steps 5 and 7 read, plus:
- `description_keywords`, `usage_patterns` and `signatures`: what §2 returned for it, each usage pattern with the file and line it cites.

No `metadata_hash`: step 7's provenance helper copies the anchor §1 names from `{stackInventoryFile}` into `constituents[]`.

Write `{bundleFile}`: `mode`, `scope` and these entries.

### 4. Display the Loaded Constituents

Report the loaded extractions: for each skill, export count, confidence tier, and load status, and the number of skills §2 could not read (`constituent-read-failed`).

### 5. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.
