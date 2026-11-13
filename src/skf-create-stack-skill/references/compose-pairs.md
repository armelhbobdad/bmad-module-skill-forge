---
nextStepFile: 'detect-integrations.md'
comentionProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'
  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'
validateFeasibilityReportProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-feasibility-report.py'
  - '{project-root}/src/shared/scripts/skf-validate-feasibility-report.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
bundleFile: '{run_dir}/extraction-bundle.json'
# A fixed path: the compose rules are not a customization surface.
composeModeRulesPath: 'references/compose-mode-rules.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Find the Compose Pairs

## STEP GOAL:

Find the confirmed skills that work together, from the architecture document or, with none, from the skills' own docs and keywords, judge every candidate on its evidence, and write the pairs kept to the extraction bundle, where `references/detect-integrations.md` §3 classifies them.

## Rules

- Judge every candidate on the helper's evidence; never search the documents for pairs by hand
- Do not classify or tier a pair: `references/detect-integrations.md` §3 does

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "compose", "stack_libraries": ["<confirmed library>", ...]}`, adding `"path"` when the halt names a file, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

### 1. Find the Candidates

A helper reports candidate pairs with their evidence; a candidate becomes an integration only when that evidence shows how the two libraries work together. **Resolve `{comentionHelper}`** from `{comentionProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `compose-pairs:comention`) with "**Cannot proceed.** `skf-comention-pairs.py` is missing, so no compose-mode pair can be found. Re-install SKF, then re-run."

1. Load `{composeModeRulesPath}` for the integration evidence format and labels
2. **If `{architecture_doc_path}` is null or not available:** skip to the **No architecture document** path below
3. **Find the candidates with the shared script:**

   ```bash
   uv run {comentionHelper} comention --doc {architecture_doc_path} --skills -
   ```
   piping the `confirmed_dependencies` names as a JSON array on stdin (e.g. `["react", "express"]`; if stdin piping is unavailable, write it to `{run_dir}/skills.json` and pass that path to `--skills`). Its `pairs[]` holds each pair a body paragraph names in one unit or through a lead-in, with `paragraph_count`, `comention_count`, `lead_in_count` and one `evidence[]` entry per paragraph naming both; `unit_excerpt` quotes a `co-mention` or `lead-in` entry, from `unit_line` (a `list-only` entry quotes nothing), and `excluded_section` is true under an introductory heading (Overview, Introduction and the like). `list_only_pair_count` counts the pairs only listed together, which it leaves out. When `pairs[]` is empty, append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "info"`, `code: "comention-no-candidates"`, `message`: "no passage names two confirmed libraries together ({list_only_pair_count} pairs only listed, {excluded_section_count} introductory sections)").

4. **Pairs only listed together.** When `list_only_pair_count` is above 0, append one `workflow_warnings[]` entry (`step: "step-05"`, `severity: "info"`, `code: "comention-list-only"`, `message`: "{list_only_pair_count} pairs only listed together"), which the evidence report lists.
5. **Confirm each candidate** from the `unit_excerpt` of its `co-mention` and `lead-in` entries. Keep the pair only when an excerpt says how the two libraries work together: data flows from one to the other, one wraps or adapts the other, one configures or initializes the other, or one handles the other's events. The script reads fenced code as text, so a diagram line counts too: a Mermaid edge between the two (`react --> express`) shows data flow. Two names side by side ("built with React and Express") do not confirm a pair, and an `excluded_section` entry whose excerpt only names both confirms nothing; one excerpt that says how the two work together is enough, wherever it sits. Drop each pair no excerpt confirms and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "comention-unconfirmed"`, `message`: the pair and the excerpts read).
6. For each confirmed pair, build its evidence in the format of `{composeModeRulesPath}`: one `[from skill: <skill>] <signature>` line per skill, the signature from that skill's `signatures` in `{bundleFile}` for an export the pair rests on, else that export's name from its `exports`, with the confirming `unit_excerpt` as its architecture reference and the VS verdicts of §2; §3 writes them to the pair's bundle entry. Its tier comes from the pair-tiers call of `references/detect-integrations.md` §3 (see **Confidence Tier Inheritance** in `{composeModeRulesPath}`), and every compose-mode label takes the `[composed]` suffix except an inferred-shared-domain one.

Then go on to [Read the VS Verdicts](#2-read-the-vs-verdicts).

**No architecture document.** Find the candidates in the constituents themselves, with the `{comentionHelper}` resolved above:

```bash
uv run {comentionHelper} infer --skills - --top-k 20
```

piping one object per confirmed skill on stdin: `{"name": "<skill>", "keywords": ["<keyword>", ...], "language": "<language>", "docs": ["<path>", ...]}`. Its `keywords` are its bundle entry's `description_keywords`, `language` is the one step 2 read from its `metadata.json`, and `docs` are its `SKILL.md` and the `.md` files in its `references/`, under `skill_package_path`, which the helper reads. A pair is a candidate only on this evidence, never on a shared language alone, and each candidate is judged like a co-mention:

- **`docs-mention`:** one skill's own docs name the other; `excerpt` quotes the first such line (`doc`, `line`). Keep the pair as a `constituent-documented-contract` integration only when that line says how the two work together, never on a "see also" or "unlike" line.
- **`shared-keywords`:** the two share a domain keyword. Keep the pair as an `inferred-shared-domain` integration only when both skills' `description_keywords`, `usage_patterns` and `exports` in `{bundleFile}` show how that domain makes them work together (one feeds, wraps, configures or consumes the other), never for two libraries that do the same job, such as `zod` and `yup` or `express` and `fastify`.

Drop every other candidate and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-unconfirmed"`, `message`: the pair and the evidence read). When `truncated` is true, append an entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-cap-truncated"`, `message`: its `total_pairs` and the top 20 analyzed); when `language_only_pair_count` is above 0, append an entry (`step: "step-05"`, `severity: "info"`, `code: "infer-language-only"`) giving that count. On exit `1` its stderr names the input it refused, such as a `docs` path that is missing, unreadable or not UTF-8: fix or drop it and run the call again. On exit `2`, or when `uv` cannot run it, compose with no inferred pairs and append an entry (`step: "step-05"`, `severity: "warn"`, `code: "infer-unavailable"`, `message`: the reason).

For each kept pair, write one `[from skill: <skill>] <signature>` line per skill from `{bundleFile}`, as item 6 says, and as its reference the `**Contract reference:**` line (a docs mention) or the `**Shared domain:**` line (shared keywords) of `{composeModeRulesPath}`.

Skip to [Write the Kept Pairs](#3-write-the-kept-pairs) with these pairs: the [VS] report rates architecture pairs only.

### 2. Read the VS Verdicts

**VS verdicts (architecture-document pairs).** Resolve `{validateFeasibilityReportHelper}` from `{validateFeasibilityReportProbeOrder}` (first existing path wins) and locate the [VS] report through it (see `shared/references/feasibility-report-schema.md`):

```bash
uv run {validateFeasibilityReportHelper} --locate "{forge_data_folder}" --project-name "{project_name}"
```

Act on the first of these that applies:

- **`status: "ok"`:** add each confirmed pair's `pairVerdicts` row (`lib_a` and `lib_b` in either order) and the `overallVerdict` to its evidence, as `{composeModeRulesPath}` shows.
- **`status: "not-found"`, or no JSON** (no candidate resolves, or `uv` cannot run it): compose without VS verdicts. With no JSON, append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "vs-report-unread"`, `message`: the reason).
- **`schemaVersionOk` is false:** never interpret the report. HALT (exit 2, `halt_reason: "schema-version-mismatch"`, phase `compose-pairs:vs-report`, `path` the report's `path`) with "feasibility-report schemaVersion mismatch: expected '1.0', got '{schemaVersion}'; refusing to proceed".
- **`unknownTokens` is not empty:** a verdict token outside the schema's set is a hard error, as the schema requires: HALT (exit 2, `halt_reason: "unknown-verdict-token"`, phase `compose-pairs:vs-report`, `path` the report's `path`), naming each token with its line and pair, and never drop or map one.
- **Any other exit `1`, or exit `2` with a JSON:** the report breaks the contract otherwise (a section missing or out of order, no verdict table or a second one) or could not be read. Read no verdict from it: compose without VS verdicts and append a `workflow_warnings[]` entry (`step: "step-05"`, `severity: "warn"`, `code: "vs-report-unusable"`, `message`: its `path` and each problem its JSON names, or its `error`).

### 3. Write the Kept Pairs

Set `{bundleFile}`'s `integrations[]` to one entry per kept pair, so `references/detect-integrations.md` §3 reads them from disk:

```json
{"a": "<library>", "b": "<library>", "qualifier": "<below>", "detection_method": "<below>", "evidence": ["[from skill: <A>] <signature>", "[from skill: <B>] <signature>"], "reference": "<its Architecture reference, Contract reference or Shared domain line>", "vs": {"pair": "<verdict>", "overall": "<overallVerdict>"}}
```

`vs` is `null` when no usable [VS] report rated the pair. The `qualifier` says how §1 found the pair, and sets its `detection_method`:

- `architecture-co-mention`: compose-mode pair the architecture document names together, confirmed from its excerpt in §1. Maps to `detection_method: architecture_co_mention` in `provenance-map.json`.
- `constituent-documented-contract`: compose-mode pair with no architecture document whose contract a constituent's own docs state, a docs mention §1 confirmed. Maps to `detection_method: constituent_documented_contract` in `provenance-map.json`.
- `inferred-shared-domain`: compose-mode pair with no architecture document, a shared-keywords candidate §1 kept (no cited contract, never a shared language alone). Maps to `detection_method: inferred_from_shared_domain` in `provenance-map.json`.

With no pair kept, `integrations[]` stays empty.

### 4. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`: its §1 sends a compose run to §3, which classifies these pairs.
