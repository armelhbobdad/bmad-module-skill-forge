---
scoringRulesFile: 'references/scoring-rules.md'
locateExportSegmentsScript: 'scripts/locate-export-segments.py'
migrationSectionRules: 'references/migration-section-rules.md'
---

# Coherence Check: Naive Mode

Load this file only from coherence-check.md §1, in naive mode, and follow it. `{run_dir}`, the `{scanSkillMdStructureHelper}` coherence-check.md §1 resolved (a command of it that exits non-zero halts as that section says) and coherence-check.md's **Halt envelope** apply here. A bare §1 or §6 is coherence-check.md's, any other bare § this file's. coherence-check.md §6 records what this file finds in the gap ledger under stage `coherence-check`, as `structural`, `scripts-assets` and `migration-section` gaps.

## Sections

### 2. Naive Mode: Concrete Structural Validation

Perform the following explicit checks (most use a single deterministic script; severity assignments are binding; do not relax them).

**2.0 Run the structural scan.** Invoke `{scanSkillMdStructureHelper}` (§1) twice, saving each output to the run folder. These results back §§2.1, 2.2, 2.3, 2.6 and 2.7: do not re-implement those checks with grep/sed/awk loops.

```bash
uv run {scanSkillMdStructureHelper} scan "{resolved_skill_package}/SKILL.md" --required-sections > "{run_dir}/required-sections.json"
uv run {scanSkillMdStructureHelper} scan "{resolved_skill_package}/SKILL.md" > "{run_dir}/structure.json"
```

The first call returns `{ description: {satisfied, matched_synonym, tried[]}, usage: {...}, api_surface: {...}, frontmatter_description, outline[{line,level,text}] }`. The second returns `{ unbalanced_fences, fence_count, bare_opening_fences[{line,text}], table_drift[{line,section,expected_cols,actual_cols,row}], scripts_assets{folders[],section,missing} }`. Hold both JSON blobs, which the files keep, for the checks below.

**2.1 Required sections present.** Read the first JSON blob from §2.0. For each of the three families (`description`, `usage`, `api_surface`):

- `satisfied: true` → no finding.
- `satisfied: false`, family `description` and `frontmatter_description: true` (a non-empty frontmatter `description` satisfies the family) → no finding.
- `satisfied: false` otherwise: read `outline`, each heading of the body with its line. When one heading's section serves the family (it shows how to call the library, for `usage`; it lists the library's exports, for `api_surface`; it says what the library is for, for `description`), there is no finding: name that heading and its line in the Coherence Analysis, and pass the family to §6 as `--served`. Otherwise → **High severity** finding: `naive-coherence: missing required section: {family}`.

The script matches the full heading text, case-insensitively, at any heading level, outside the frontmatter and fenced code. Its synonyms, `tried[]`, include every SKF template and override heading, so a skill built from a template reports `satisfied: true` and the `matched_synonym`.

**2.2 Code fence balance.** Read `unbalanced_fences` from the second JSON blob. **`true` → High severity** finding: `naive-coherence: unbalanced code fence (unclosed block)` (the JSON's `fence_count` may be cited in the detail).

**2.3 Language tags on opening fences.** Read `bare_opening_fences[]` from the second JSON blob. The script already runs the stateful open/close scan, so closing fences are never reported. For each entry, emit a **Medium severity** finding: `naive-coherence: opening code fence at line {entry.line} missing language tag`.

**2.4 Exports cross-used in a usage-family section.** The scanner counts how often each function and method export of the validated inventory (the file step 3 wrote) is used in the usage-family scope, so no name is grepped by hand:

```bash
uv run {scanSkillMdStructureHelper} usage-scope "{resolved_skill_package}/SKILL.md" --exports "{run_dir}/inventory.json" --kinds function,method [--body single] > "{run_dir}/usage-scope.json"
```

The script decides split-body from the `references/` folder alone; whether the `## Full*` sections are stubs is your judgment, so pass `--body single` when a `references/` directory exists but those sections carry real content. Read `zero_usage[]` from the output:
- **Zero occurrences across the entire scope → Medium severity** finding, one per `zero_usage[]` entry: `naive-coherence: exported {kind} \`{name}\` is not referenced in any usage-family section or reference file`. This catches the "documented but unused" failure mode that trivially fails discovery testing. Like a missing export, it is a completeness gap, so it does not block the hard gate.

**2.5 Async/sync consistency.** `{locateExportSegmentsScript}` reports the facts: for each export the step 3 inventory lists with `kind` `function` or `method`, and each method a class, interface, struct, trait or type entry lists in `methods`, with that entry as its `owner`, where the skill describes it (`descriptions[]`: the heading sections, table rows, list items and paragraphs that name it in code, and the signature lines that declare it) and each call to it in fenced code, with whether the call awaits it (`awaited`) and how (`awaitedVia`): `direct` when the await applies to the call itself (`directlyAwaited`), `chain` when it applies to a member, subscript, call or group around the call, `consumer` for an async loop or context manager, and `argument` or `runner` when the call sits in the arguments of an awaited call or of a runner, whose callee `enclosingCallee` names. A method with an `owner` (a `method` entry that gives one, or an item of an entry's `methods`) counts only the calls on that owner or on a variable the same example binds to it (`receiverMatch` `owner` for `cognee.agents.get(...)`, `bound` for `gen.next_uuid()` after `gen = UuidGenerator()`); a call on another owner (`cognee.config.get(...)`) is not its call, and a call with no receiver or on one it cannot tie to the owner is listed in `unverifiedCalls[]` (for a method with no tied call, in `notCalledUnverified[]`). It reads the names from the validated inventory file itself, keeping the `function` and `method` entries and the `methods` of each class, interface, struct, trait or type entry, so no name is copied by hand. Skip this check when the inventory has no `function` or `method` entry and no class, interface, struct, trait or type entry with `methods`; otherwise run the script (it resolves relative to the skill root):

```bash
uv run {locateExportSegmentsScript} --inventory "{run_dir}/inventory.json" --skill-dir "{resolved_skill_package}"
```

The script judges no meaning. For each `exports[]` entry, read its `descriptions[]` and decide what they assert about **this** export (with an `owner`, the method on that owner). The word `async` in a description decides nothing:

- **async**: the caller must await what it returns (a promise, a coroutine or a future), as its signature or its description says. A Kotlin `suspend` function needs no `await`, so it makes no async claim here.
- **sync**: it returns its result directly, for example as the blocking counterpart of an async export.
- **no claim**: nothing says how it returns. A description that names a paired sync or async variant (`readFileSync` as "the sync counterpart of the async `readFile`"), or says async about another API, such as a same-named method of another owner (`config.get` for `agents.get`), asserts nothing about this export.

Then, for each export:

- **async**, no call is awaited (`awaitedCount` is 0) and no unawaited call hands its result on → **High severity** finding: `naive-coherence: \`{name}\` described as async but example lacks \`await\`` (cite the first call's `file` and `line`). A call hands its result on when its `chainedMember` waits for it (`then`, `catch`, `join`, `get`), the example returns it (`return fetchData(x)` in an async function) or stores it and awaits it later: read the call lines before raising the finding.
- **sync** and `directlyAwaitedCount` is above 0 → **High severity** finding: `naive-coherence: \`{name}\` described as sync but example awaits it` (cite the first directly awaited call).
- **sync**, `directlyAwaitedCount` is 0 and a call sits in the arguments of a call that needs awaitable arguments → the same **High severity** finding (cite the first such call's `file` and `line`): its `awaitedVia` is `runner` (a runner such as Python `asyncio.run` or `loop.run_until_complete`, Rust `block_on`), or `argument` with an `enclosingCallee` of Python `asyncio.gather`, `asyncio.wait` or `asyncio.wait_for`. JavaScript `Promise.all`, `Promise.race` and `Promise.allSettled` accept plain values, so a call in their arguments raises nothing, and neither does any other call that is `awaited` but not `directlyAwaited` (`awaitedVia` `chain`, `consumer`, or `argument` of another callee).
- Otherwise no finding. The names in `notCalled[]` (a method as `owner.name`) have no call an example ties to them, so they raise none. A call in `unverifiedCalls[]` or `notCalledUnverified[]` raises none either. For an export with an `owner`, its finding's title writes `{owner}.{name}` for `{name}`, and so does its ledger record's `export`.

**2.6 Table syntax.** Read `table_drift[]` from the second JSON blob (§2.0). The script normalizes escaped pipes (`\|`, used inside TypeScript union types such as `string \| undefined`) before splitting and compares each row against its header's column count, so a plain `split on |` false-positive cannot occur here. For each entry, emit a **Medium severity** finding: `naive-coherence: table row at line {entry.line} has {entry.actual_cols} columns; header has {entry.expected_cols}` (the `entry.section` and `entry.row` fields populate the detail when present).

**2.7 Scripts & Assets section.** Read `scripts_assets` from the second JSON blob (§2.0): `folders` names the `scripts/` and `assets/` folders beside SKILL.md, and `section` the first heading that starts with `Scripts` (null when there is none).
- `missing` is true (a folder exists AND no Scripts heading) → **Medium severity** finding: `naive-coherence: scripts/assets directory exists but Scripts & Assets section missing` (per `{scoringRulesFile}`)

Each §2.1 to §2.7 finding is a row of the naive Structural Findings table that §6 records; with none, the **Structural Issues** count is 0.

### 2b. Migration/Deprecation Verification (Mode-Independent)

Apply rules from `{migrationSectionRules}`, the single source of truth for the gate, scope and case rules.

When this file is done, continue at coherence-check.md §6.
