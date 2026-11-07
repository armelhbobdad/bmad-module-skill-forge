---
title: Verifying a Skill
description: How to audit an SKF skill by tracing its instructions back to an upstream commit and line number in under 60 seconds.
---

**Nothing is made up.** Every instruction in a skill compiled from source with Create Skill or Stack Skill traces back to a specific file, a specific line, and a specific commit in the upstream source. If a skill claims a function exists, you can open the real source tree at the pinned commit and see it with your own eyes. If the claim and the source disagree, that's a bug, and SKF treats it as one.

---

## The three-step audit

Pick any symbol in a skill compiled from source. You can trace it to the exact line of upstream source in under 60 seconds.

This audit needs the provenance map that Create Skill and Stack Skill write. Quick Skill writes none, so its skills name the upstream repository but not the line behind each symbol. A docs-only skill cites documentation links (`[EXT:...]`) instead of source lines, so it has no commit to check. A stack skill built from code has no `source_commit` or `source_repo` in its `metadata.json`. Look in its `provenance-map.json` (step 2) instead, where `source_repo` lists each repository and `source_commit` lists one commit per repository. A stack skill composed from other skills has no commit of its own and traces back to those skills instead.

### 1. Open the skill's `metadata.json`

Every skill ships a `metadata.json` next to its `SKILL.md`. Note two fields:

- `source_commit`: the exact commit SHA the skill was compiled from
- `source_repo`: the upstream repository

This is the anchor. Everything else traces back to this commit.

### 2. Open the skill's `provenance-map.json`

Provenance maps live in `forge-data/{skill}/{version}/provenance-map.json` in the project that compiled the skill. They are part of the audit trail and do not ship inside the skill package, so for a published skill, look in the repository that publishes it (oh-my-skills keeps its `forge-data/` folder public). Find your symbol. Every entry carries its own `source_file` and `source_line`, and its `confidence` and `extraction_method` name the tool that read it. The skill's `SKILL.md` also cites each signature inline, as `[AST:file:Lnn]` for an export ast-grep matched or `[SRC:file:Lnn]` for one read by eye, so you can often go straight to step 3. The entry for an export ast-grep matched looks like this:

```json
{
  "export_name": "search",
  "export_type": "function",
  "source_library": "cognee",
  "params": ["query_text: str", "query_type: SearchType = SearchType.HYBRID_COMPLETION"],
  "return_type": "list[SearchResult]",
  "source_file": "cognee/api/v1/search/search.py",
  "source_line": 41,
  "confidence": "T1",
  "extraction_method": "ast-grep",
  "ast_node_type": "function_definition",
  "signature_source": "T1"
}
```

This is the published entry for cognee's `search` in oh-my-skills' [`forge-data/oms-cognee/1.6.2/provenance-map.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.6.2/provenance-map.json), shortened to its first two parameters (`search` takes 27). It points at line 41, where `async def search(` is defined at cognee v1.6.2's commit (`ba3631f2`), and the skill's `SKILL.md` cites `[AST:cognee/api/v1/search/search.py:L41]`. Its labels follow the tool that read it: an ast-grep match gives `T1`, `ast-grep`, the node kind its rule matched and an `[AST:]` citation. An export read by eye instead, because ast-grep could not parse its file, an ast-grep call that failed or timed out left its file unread, or no rule matched it, gets `T1-low`, `source-read`, no node kind and an `[SRC:]` citation, at every forge tier.

The 1.6.2 map passes the [line, label and citation checks](#workflow-time-enforcement) that SKF 3.0.0 added. Under SKF 4.0.0 a strict test passed the skill at 99%. SKF 7.0.0's Test Skill found real errors in it, all since fixed by hand against the pinned source, and SKF 8.0.0 still blocks it on two false positives: it compares the skill's forms of the lightweight `cognee.pipelines.run_pipeline` with the dataset orchestrator of the same name ([#918](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/918)). So the skill has no score (see [the scores](#the-scores-including-the-ones-we-lose)). The older map next to it, [`forge-data/oms-cognee/1.0.0/provenance-map.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.0.0/provenance-map.json), was compiled before labels followed the tool and still shows what those checks catch. It records `search` as `source-read` but labels it `T1`, and it points at line 26, the blank line above the definition, while that version's `SKILL.md` cites `[AST:cognee/api/v1/search/search.py:L27]`. A source read is `T1-low` with an `[SRC:]` citation, and its line is 27, the `def` line at v1.0.0.

### 3. Visit the upstream repo at the pinned commit

Open `{source_repo}` at `{source_commit}`, jump to `{source_file}` line `{source_line}`. The signature in `SKILL.md` should match what you see in the source.

If it doesn't, **that's a bug**. For a skill you built, Test Skill (`@Ferris TS`) rates a signature mismatch as a Critical gap, which stops the test at its [hard gate](#hard-gate). It compares only what a signature writes: a component by its props alone, so `FC<P>` and `(props: P) => JSX.Element` are one signature, and a type or a return type the skill does not write, or type arguments it leaves out (`dict` against `dict[str, Any]`), are not compared. When the skill documents a name in several places, such as a brief usage in `SKILL.md` and a full props list in a reference file, each form that lists parameters, gives a usage or states a return type is compared, and a `const` holding a component, such as a `forwardRef(...)` result, is compared by the usage or declaration the skill writes for it. When the source declares two functions of one name, a form is compared only with the one its own `[AST:]` or `[SRC:]` citation names, at a line or in a range that holds its line or a later one before the next declaration the extraction records in that file. Test Skill reads that citation on the form's line, or on the next non-blank line unless that line writes the name itself, and, for a form in a code block, in a comment just above it in the block or, when the block documents no other form of the name, in a comment on the block's first non-blank line or on the first non-blank line after the block, unless that line writes the name. A line that writes two forms of the name that differ, such as a table row that quotes the other function's form as a contrast, gives none of those forms a citation. A form whose citations name neither function, or both, is compared as before, with the declarations the package exports. Two differences a caller never meets are rated lower and still count as matching: a renamed parameter in a TypeScript, JavaScript, Go, Rust, Java, C or C++ file, whose callers pass arguments by position, is a Low gap, and an optional parameter left out of a signature the skill labels partial (such as `Props (simplified)`) is an Info observation. A renamed Python parameter stays Critical, because Test Skill cannot see which parameters a caller must pass by position, and so does a renamed Vue component prop, which callers set by name. Update Skill (`@Ferris US`) with `--from-test-report` repairs the gaps a test report lists. If you think SKF extracted it wrong, [open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). Falsifiability isn't a feature. It's the whole deal.

### Workflow-time enforcement

SKF checks the same anchor while it works, so a skill and its citations always describe one commit.

- **Create Skill (`@Ferris CS`)**, at Forge tier and above, reads a remote source in a private checkout at the commit it resolves from the brief: the ref its `target_ref` names, or the tag that matches its version. It records that commit as the skill's `source_commit`, and it moves SKF's shared clone of the repository to the same commit. If it could not move the clone, it says why, and the run skips ccc discovery and the ccc index registration.
- **Update Skill (`@Ferris US`)**, for a skill built from a remote repository, reads the source in a private checkout at the commit that the skill's `source_ref` (or the `--target-ref` you pass) points to now. When it writes, it records that commit as the new `source_commit`. If it could not move SKF's shared clone to that commit, its report says why and how to move it.
- **Test Skill (`@Ferris TS`)**, and **Update Skill with `--from-test-report`** (a repair driven by a test report's gaps), first compare the commit your local source is on (`git rev-parse HEAD`) with `metadata.source_commit`. If they differ, they stop before reading any source: Test Skill with `workspace-drift`, Update Skill with `halted-for-workspace-drift`. The message names the commit to check out, so a spot-check never quietly reads the wrong tree.
- To read the current commit anyway, pass `--allow-workspace-drift`. The final report records the override. In Test Skill, a pass under this override is recorded as `pass-with-drift`, and SKF recommends Update Skill instead of export. Update Skill with `--from-test-report` takes nothing from the current commit: it never moves a provenance line to it or records one from it, and it reads no signature, parameter list, return type or node kind there. Every new or changed export in the test report, whatever its severity, needs one of those from the source, so it stops the run with `halted-for-workspace-drift` before it changes the skill, and the message lists what each gap needs. A rescope (a gap that takes an export out of the skill's scope) stops the run the same way, because recounting the public API needs the pinned tree: the run has not written the scope amendment to the skill brief yet, so the brief stays as it was and a re-run asks again. A report whose gaps are only provenance line fixes, structural fixes or metadata patches still runs: a line it would have moved is recorded as `unknown` instead, and a node kind it would have looked up in the source stays as it is, each with a warning, while the stats keep the public API counts `metadata.json` records.
- **Line, label and citation checks.** When the source is on disk, Create Skill and Update Skill check that each provenance `source_line` in a Python, TypeScript or JavaScript file is the line that defines its export (the `def` or declaration line, not a decorator or blank line above it). With or without the source, they check that each `[AST:]` / `[SRC:]` citation matches how its entry was extracted: ast-grep gives `[AST:]`, reading the source by eye gives `[SRC:]`. Each entry's labels must also match its `extraction_method`: an ast-grep entry is `T1` with a node kind, and an entry read by eye is `T1-low` with no node kind and a `signature_source` other than `T1`. They relabel an entry that disagrees, so a source read labeled `T1` becomes `T1-low`. They also ask the ast-grep CLI whether each ast-grep entry's `ast_node_type` is a node kind of its file's language, and replace a kind it does not know with the kind the matching recipe declares. They fix each finding that has one answer and list the rest as warnings in the evidence report. With the local source at hand, Test Skill reports each wrong line as a Low gap, and Update Skill with `--from-test-report` moves the entry to its definition line. When the checks find no line that defines an export, which can mean a shape they do not cover, the entry is left as it is and Test Skill asks you to check it by hand.

---

## Where to look for what

Every file in the per-skill output carries a specific job. Here's the lookup table for the really skeptical:

| Question | File |
|---|---|
| What commit was the source pinned to? | `skills/{name}/{version}/{name}/metadata.json` → `source_commit` |
| Which symbols are documented and where did each come from? | `forge-data/{name}/{version}/provenance-map.json` |
| What AST patterns were used for extraction? | `forge-data/{name}/{version}/extraction-rules.yaml` |
| What signatures, types, and examples did the extractor actually capture? | `forge-data/{name}/{version}/evidence-report.md` |
| How was the skill scored? Show me the math. | `forge-data/{name}/{version}/test-report-{name}-{run_id}.md` (one report per run, named with the run ID; the newest one counts. Test Skill gives a report this name only once its checks pass, so a run that halts leaves just its hidden in-progress file, `.skf-test-report-{name}-{run_id}.md`, and the last finished report still counts. Reports from SKF 2.x and earlier are named `test-report-{name}.md`) |
| How was the skill scoped, and what was deliberately left out? | `forge-data/{name}/skill-brief.yaml` |

Everything a reader needs to reconstruct the compilation is in the two sibling directories: `skills/` ships to consumers, `forge-data/` is the audit trail.

---

## The scores, including the ones we lose

The [scoring formula](#how-the-score-is-computed) is deterministic and the pass threshold is **80%**. Every test report also logs the specific edges where a skill falls short, so the numbers aren't marketing.

Take oh-my-skills' four reference skills as an example. Under SKF 4.0.0, strict tests that applied the signature rule as then written passed oms-cocoindex at 100% and oms-cognee at 99%, and blocked the other two. Earlier passes are kept in each skill's history; the oms-cocoindex, oms-cognee and oms-storybook-react-vite ones read the rule leniently.

SKF 5.0.0 to 7.0.0 put every signature rule in one file that every judge reads, compare each form a skill documents, and pin the names and signatures it writes in a fixed form. On the same skills, the first 7.0.0 tests passed oms-cocoindex and oms-uitripled at 100% (uitripled's `cn` false positive was gone) and blocked oms-cognee, on 8 Critical and 1 High gaps, and oms-storybook-react-vite, on 1 Critical gap with Export Coverage at 63.78% of the names its brief's `scope.tier_a_include` lists. Two rounds of fixes per skill (three for oms-storybook-react-vite), each followed by a strict re-test, then found real errors in all four skills, the two that passed included:
- `@coco.fn(batching=True)` documented as a working decorator, although at the pinned commit it raises `ValueError` for any function.
- Defaults written on props that a component's props type requires.
- Prose calls that leave out a required argument.
- 134 tier A names the storybook skill did not document.

Every fix was made by hand against the pinned source. Each round's fixes were reviewed before its test, except the last one-row storybook correction.

Today, on a strict SKF 8.0.0 test of the version each one ships, three skills pass, all at 100%, and one is blocked. On unchanged text, 8.0.0 raised oms-storybook-react-vite from 98.23% to 100%, because a star re-export from another package now adds no name ([#926](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/926)), and a written rule ([#932](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/932)) now settles the three oms-uitripled forms its 7.0.0 pass rested on without recording them; uitripled stays at 100%. The first 8.0.0 run of oms-cocoindex counted `ExceptionContext`, named only inside another export's type, as undocumented (99.37%), a reader's call the inventory contract does not settle ([#967](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/967)); oh-my-skills then documented it. Every pass still rests on calls the reader or the judge makes where the rules leave the case open, and each report now writes them down, with how it counted them: storybook's turns on how the split-body check reads two different exports that share a name, uitripled's on an em-dash placeholder in a Default cell read as empty, and cocoindex's on a call to a decorator instance compared with its `__call__`. The judges also still read some cases differently from run to run: three oms-uitripled lines were matches in one 7.0.0 run and Critical gaps in the next, with no change to the lines. Every report, the failing ones included, is kept: in the skill's `forge-data/` folder, or, for the reverted oms-storybook-react-vite repair, in oh-my-skills' git history. Even a passing report names the drift it found:

| Skill | Score | What the report discloses |
|---|---|---|
| [oms-cocoindex](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cocoindex/1.0.0/test-report-oms-cocoindex-20261107T115927Z-5db1615d.md) | **100%** | 72/72 exports of the root barrel (since 7.0.0 the brief's `scope.exclude` applies before the source is read as one Python package, not a Cargo workspace), 48/48 signatures. Type Coverage is 1/1: the root exports Test Skill restores when the brief's doc globs match no file carry no kind, so the category counts a single type ([#913](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/913)). The report records how it read `@coco.fn(...)`, a call to a decorator instance, compared with the instance's `__call__`. The first 8.0.0 run counted `ExceptionContext`, named only inside another export's type, as undocumented (99.37%; [#967](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/967)); oh-my-skills documented it. Left open: 11 Medium stale-documentation gaps on connector exports that the reconcile counts outside the surface ([#912](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/912)), a brief glob that matches no file and a barrel count. |
| [oms-cognee](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.6.2/test-report-oms-cognee-20261107T112455Z-eec853d0.md) | **blocked** | 2 Critical false positives: the test compares the skill's two forms of the lightweight `cognee.pipelines.run_pipeline` with the orchestrator of the same name, the only `run_pipeline` its surface holds ([#918](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/918); the fix, [#956](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/956), is not in 8.0.0). Every other check passes: 92/92 exports of the `cognee/__init__.py` barrel at pinned commit `ba3631f2` (v1.6.2), 74 of 75 signature names and 35/35 types. External Validation is 90%: skill-check finds the `SKILL.md` body over its 5,000-token budget. |
| [oms-storybook-react-vite](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-storybook-react-vite/10.3.5/test-report-oms-storybook-react-vite-20261107T112449Z-0cc4693c.md) | **100%** | Counted on the brief's `scope.tier_a_include` set: 370/370 exports, 180/180 signatures (66 of them Testing Library bindings whose parameters are typed in another package, counted as matching without comparison under 8.0.0's rule, [#925](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/925)), 128/128 types. Under 7.0.0 the run read `export type * from '@vitest/spy'` as 19 names, 13 of them undocumented (98.23%); 8.0.0 counts none ([#926](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/926)). The pass turns on how the split-body check reads two different exports that share a name, core's and React's `composeStories`: read as one export, they would be a High gap ([#927](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/927)). |
| [oms-uitripled](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-uitripled/0.1.0/test-report-oms-uitripled-20261107T112452Z-65994952.md) | **100%** | 327/327 exports against the stored count for the brief's `scope.include` union, 269/269 signatures and 42/42 types. The report records the call the pass rests on, an em-dash placeholder in two props tables' Default column read as an empty cell as Create Skill's own format writes it (read as a value, two Critical gaps), and one the 100% rests on: seven primitives named only on import lines, counted as documented (without them, Export Coverage would be 97.86%). |

Perfection is suspicious. Visible fallibility is trustworthy. SKF writes down the edges it can't score cleanly, so you can read them and decide for yourself whether the remaining coverage is enough for your use case.

### oms-storybook-react-vite: a worked example of a score that was too high

A first round of SKF 4.0.0 repairs of oms-storybook-react-vite, three Update Skill runs, passed at 99.93% by documenting about 800 internal names that its brief's wide `code/core/**` glob pulled in. Those repairs were reverted, and the brief now names the story-authoring entry points in `scope.tier_a_include` (280 names).

After the tiered brief, two re-tests were blocked and repaired by Update Skill before a third scored the skill at 95.17%. That number was still too high, for two reasons:
- Export Coverage read 100% because the stored count then credited every documented name ([#792](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/792)).
- Its signature judges read the doc-block prop lists leniently, a call no rule settled then. Test Skill's signature rules now say how a props list compares.

Removing the stored count made the next run name every undocumented export. It measured 206 of the 280 authored names documented, and it found real errors, such as `definePreview` listed under `storybook/preview-api`. Update Skill repaired 22 signatures from a later report. Two fixes were made by hand because its repair halted: the test had cited Angular's `definePreview`, and Update Skill would have copied that signature into a React skill ([#824](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/824), [#830](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/830)). The other hand fixes, also checked against the pinned source, corrected errors no test gap covered and a later re-test's `DocsContainer` and Canvas gaps.

A strict SKF 4.0.0 test of the version that shipped then ([report](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-storybook-react-vite/10.3.5/test-report-oms-storybook-react-vite-20261103T131516Z-6e2b972a.md)) covered all of those fixes. It was blocked on 4 Critical gaps: two compared the React portable-stories wrappers with core's functions, and two were older real errors no earlier run had flagged. So oh-my-skills published no score instead of quoting the earlier number.

SKF 7.0.0 measures the skill against the names its brief lists. Its first test found 63.78% of them documented. The next rounds documented the 134 missing names and fixed the errors the tests and reviews found, by hand against the pinned source. A strict SKF 7.0.0 test of the version that ships passed at 98.23%, and the same text passes a strict SKF 8.0.0 test at 100% ([report](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-storybook-react-vite/10.3.5/test-report-oms-storybook-react-vite-20261107T112449Z-0cc4693c.md)). Nothing was hidden: every report on the way is kept.

That's the pattern SKF asks you to trust: when scoring can't reach 100%, the report says so, cites the line, and leaves a fingerprint for the next audit.

---

## How the Score Is Computed

The Test Skill workflow (`@Ferris TS`) calculates the completeness score: a weighted measure of how thoroughly and accurately a skill documents its target. This score is the quality gate. A pass means the skill is ready for export. A fail routes it to Update Skill for repair. When there is too little evidence to grade the skill, the result is INCONCLUSIVE, and SKF asks you to review it by hand.

### Categories and weights

The score is a weighted sum of up to five categories. The weights below are the starting point. No single run scores all five: naive mode drops Coherence, and contextual mode drops Signature Accuracy and Type Coverage.

| Category | Weight | What it measures |
|---|---|---|
| **Export Coverage** | 36% | Percentage of source exports documented in `SKILL.md` |
| **Signature Accuracy** | 22% | Documented function signatures match actual source signatures (parameter names, types, order, return types). A renamed parameter in a TypeScript, JavaScript, Go, Rust, Java, C or C++ file, whose callers pass every argument by position, still matches, and so does a signature the skill labels partial that leaves out only optional parameters. A component is compared by its props alone, a type or return type a signature does not write is not compared, and each form a name is documented in is compared on its own, with the declaration its own citation names when the source has two of that name |
| **Type Coverage** | 14% | Types and interfaces referenced in exports are fully documented |
| **Coherence** | 18% | Cross-references resolve, integration patterns are complete (contextual mode only) |
| **External Validation** | 10% | skill-check quality score (0–100), averaged with the Tessl Review score (0–100) when you opt in to Tessl Review |

### Formula

```
total_score = sum(category_weight × category_score)
```

Each category score is a percentage: `(items_passing / items_total) × 100`.

**Coherence** (contextual mode) combines two sub-scores:

```
coherence = (reference_validity × 0.6) + (integration_completeness × 0.4)
```

If no integration patterns exist, coherence equals reference validity alone.

**External validation** averages skill-check and Tessl Review when both produce a score. When only one does, that score is used. When neither does, the 10% weight is redistributed proportionally to the other active categories.

**Tessl Review is optional.** It runs only after you set `tessl_review_workspace` in `_bmad/_memory/forger-sidecar/preferences.yaml` to the name of one of your Tessl workspaces (after `tessl login`, or with `TESSL_TOKEN` set). Create Skill and Test Skill then send the skill's `SKILL.md`, `references/`, `scripts/` and `assets/` to Tessl, where each review stays in that workspace's history, and each fresh review spends Tessl credits; each workflow run can spend one. A review takes Tessl about two minutes: the workflow checks on it in calls of under two minutes each, for up to about ten minutes, and records `timeout` if it has not finished by then. SKF never applies Tessl's suggestions: it lists them in the evidence and test reports, and you act on a description suggestion by editing the brief.

### Deterministic scoring

The weight redistribution and score aggregation are computed by a deterministic Python script ([`compute-score.py`](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-test-skill/scripts/compute-score.py)). It reads, by path, the score files the earlier steps' scripts wrote in the run folder, such as the Signature Accuracy and Type Coverage that `score-signatures.py` scored and the export surface `load-coverage-inputs.py` built, so no score is copied out of the test report by hand. Same inputs always produce the same score. When a scoring script cannot run, Test Skill halts without a score rather than scoring by hand.

### Naive vs contextual mode

Test Skill runs in one of two modes, detected automatically:

- **Contextual mode** (stack skills): Coherence is scored, but Signature Accuracy and Type Coverage are not, because a stack skill's signatures and types belong to the libraries it combines. Their 36% is shared out in proportion, so Export Coverage weighs about 56%, Coherence about 28% and External Validation about 16%.
- **Naive mode** (individual skills): Coherence is not scored. Its 18% weight is redistributed:

| Category | Naive Weight |
|---|---|
| Export Coverage | 45% |
| Signature Accuracy | 25% |
| Type Coverage | 20% |
| External Validation | 10% |

### Tier adjustments

Some categories cannot be scored for every skill. These conditions skip Signature Accuracy and Type Coverage:

| Condition | Skipped Categories | Reason |
|---|---|---|
| **Quick** tier | Signature Accuracy, Type Coverage | No AST parsing available |
| **Docs-only** skill (every citation is a documentation link, `[EXT:...]`) | Signature Accuracy, Type Coverage | No source code to compare against |
| **Source not on disk**: Test Skill works from the saved provenance map (`analysisConfidence` `provenance-map`), from the export list in the skill's `metadata.json` (`metadata-only`) or from a remote read of the source (`remote-only`) | Signature Accuracy, Type Coverage | Names can be matched, but signatures cannot be re-checked without the source |
| **Stack skill**, any tier | Signature Accuracy, Type Coverage | The signatures and types belong to the libraries the stack combines |
| **Reference-app skill**, any tier | Signature Accuracy, Type Coverage | It documents how parts are wired together, not a library's exports |
| **Forge / Forge+ / Deep** individual skill with its source on disk | None | Full AST-backed scoring |

When categories are skipped, their combined weight is redistributed proportionally to the remaining active categories. A Quick-tier skill and a Deep-tier skill both pass at the same 80% threshold. The score reflects what your tier can actually measure.

### Hard gate

Before scoring, a hard gate reads the run's gap ledger, `test-findings-{run_id}.json` in the skill's version folder under `forge-data/`, where the coverage, coherence and external validation steps record every gap they find with its severity. If any gap is **Critical** or **High**, Test Skill stops there: no score is computed, and the result is FAIL whatever the coverage. A blocked run still completes its record. It writes the Gap Report, with the blocking gaps first, and a FAIL result record whose `halt_reason` is `hard-gate-blocked`, runs the `on_complete` hook and the health check, then exits with code 2. SKF recommends `@Ferris US <name> --from-test-report` to repair the blocking gaps. Medium, Low and Info gaps pass through to scoring: a missing export, for example, is Medium, so it lowers Export Coverage and the threshold decides the verdict.

### Pass/fail

```
threshold = --threshold=<N> if you passed it, else the pipeline default, else default_threshold (80 unless your team changed it)

score >= threshold  →  PASS  →  Recommend export-skill
score <  threshold  →  FAIL  →  Recommend update-skill
too little evidence  →  INCONCLUSIVE  →  Review by hand
```

INCONCLUSIVE means fewer than two categories were left to score, or a Quick-tier skill had only Export Coverage to go on. It is neither a pass nor a fail: SKF does not export the skill or retry, and it leaves the decision to you. To get a verdict, add evidence and test again: install skill-check so `npx skill-check` runs without a download, or install ast-grep and re-run `@Ferris SF` to move up a tier.

The default threshold is **80%**. Pipeline aliases declare their own defaults: `forge-auto` targets **90%**, `forge` and `forge-quick` target **80%**. To set the threshold for one run, pass `--threshold=85` to Test Skill, or write `TS[min:85]` inside a pipeline sequence. To change the default for your whole team, set `default_threshold` in `_bmad/custom/skf-test-skill.toml`. That file is read only in a project where the BMAD Method installer has added its customization script. With SKF installed alone, pass `--threshold` on each run instead (see [Customizing a Workflow](/docs/workflows.md#customizing-a-workflow)).

Test Skill does not run without its tools: a missing `uv` or `python3` halts the run before it tests anything (`runtime-missing`). Two caps turn a pass into a fail. The first fires whenever the report's `toolingStatus` is not `ok`, for example when the frontmatter validator timed out (`frontmatter-validator-timeout`). A docs-only stack skill that neither skill-check nor Tessl Review scored is capped the same way, because too little is left to grade it. A docs-only individual skill in that state has only Export Coverage left, so it ends INCONCLUSIVE instead. A capped run stays FAIL at any threshold: the fallback below never accepts it.

When no cap fired and a skill scores between 80% and its target threshold (for example, 82% against a 90% target), it still passes at the 80% floor, and Test Skill writes an evidence report to `forge-data/{skill}/{version}/evidence-report-fallback.md` that records the shortfall.

A run that found drift and went on under `--allow-workspace-drift` ends **pass-with-drift**, not PASS, when it reaches the threshold. It read a different commit than the skill cites, so test again on the pinned commit before you export.

### Gap severities

Each step rates every gap it records against the Gap Severity table in Test Skill's [`scoring-rules.md`](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-test-skill/references/scoring-rules.md), so a gap gets the same severity on every run. Critical and High gaps found before scoring block the run at the [hard gate](#hard-gate). The others lower the score or guide remediation:

| Severity | Examples |
|---|---|
| **Critical** | A wrong signature (any difference but the renamed parameter and the partial signature of the Low and Info rows), or a fabricated one (a documented export that the source does not define at the line the skill cites); a broken reference in a stack skill (a file, skill, type, or `scripts/` or `assets/` file that does not exist) |
| **High** | An inaccurate reference in a stack skill (the target exists but does not match), or a reference whose real path leads outside the skill and its sources; a split-body mismatch (two files of the skill, `SKILL.md` or a `references/` file, document one export differently); `metadata.json` stats that count every export as documented while some are missing from the skill; in an individual skill, a missing required section, an unbalanced code fence, or an example that awaits a sync function or method or skips the `await` of an async one (a method call the check cannot tie to its class is listed but not checked) |
| **Medium** | A missing export or type (a missing export lowers Export Coverage); stale documentation (a documented export outside the coverage surface that the run did not match to one declaration in the source, or that a brief scopes out); an incomplete integration pattern in a stack skill; in an individual skill, a code fence with no language tag, a function no example names, or a table row whose column count differs from its header |
| **Low** | Gaps in metadata, the description or provenance lines, such as missing optional metadata or a provenance line that is not the definition line; a renamed parameter in a TypeScript, JavaScript, Go, Rust, Java, C or C++ file, whose callers pass arguments by position |
| **Info** | Observations such as style suggestions or a documented extra (a documented name outside the coverage surface that the source still declares); a partial signature (an optional parameter left out of a signature the skill labels partial); discovery testing not performed |

Only some runs can find a documented extra: the source must be Python or TypeScript/JavaScript, and the run needs the Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `workspaceDrift` not `overridden`, a provenance map and a coverage surface that a complete extraction built. On any other run, every documented export outside the coverage surface is stale documentation.

A declaration the run finds only in an `example`, `examples`, `demo`, `demos`, `sample`, `samples`, `scripts`, `playground`, `bench`, `benchmark`, `benchmarks`, `migrations` or `docs` folder right below a package's root, or in an `e2e` or `__fixtures__` folder anywhere, does not count, so a name declared only in `scripts/foo.py` stays stale documentation unless the provenance map cites a file in that folder. Nor does a module named after the name count (such as `client.py` for a documented `client()`) when the skill documents the name as a function, hook, class, interface, enum or type, unless the provenance map records the name as a module or package, or the module is a TypeScript or JavaScript file that is itself the export (`export default`, `module.exports =`).

Discovery testing runs after the hard gate, so a discovery gap (Info, Medium or High) is counted in the Gap Report and blocks nothing.

### Score report output

The test report includes a score breakdown table showing each category's raw score, weight, and weighted contribution. This example is an individual skill (naive mode) at Deep tier:

| Category | Score | Weight | Weighted |
|---|---|---|---|
| Export Coverage | 92% | 45% | 41.4% |
| Signature Accuracy | 85% | 25% | 21.25% |
| Type Coverage | 100% | 20% | 20.0% |
| Coherence | not scored (naive mode) | 0% | 0% |
| External Validation | 78% | 10% | 7.8% |
| **Total** | | **100%** | **90.45%** |

The report also records `analysisConfidence`, how Test Skill read the source (`full`, `provenance-map`, `metadata-only`, `remote-only` or `docs-only`), and includes a degradation notice when source access was limited. It records the health of the tools the run used apart from that, as `toolingStatus`: `ok`, or `frontmatter-validator-timeout`.

---

## Build-time drift detection (for docs themselves)

The library version numbers in the SKF docs you're reading right now are checked against oh-my-skills. A `docs/_data/pinned.yaml` anchor file records the exact version, commit SHA, and confidence tier of every reference skill. A Node validator (`tools/validate-docs-drift.js`) runs as part of `npm run quality` and:

1. **Confirms canonical truth.** Every anchor in `pinned.yaml` is cross-checked against the actual `metadata.json` in oh-my-skills: version, commit, tier, and authority must match. The `skf_version` in `pinned.yaml` must also match the version in SKF's own `package.json`.
2. **Scans docs for stale prose.** Every published `.md` page under `docs/` is searched for `<library> v?<x.y.z>` patterns, and any version that disagrees with `pinned.yaml` is flagged with its file and line number.

CI does not run this check. It needs a local clone of oh-my-skills, so run it yourself before you merge any change to the docs or to `pinned.yaml`. It's the same "nothing is made up" contract SKF applies to skills, applied to the docs that describe SKF. When the anchor file is updated to reflect a new oh-my-skills release, the prose must update too, or `npm run docs:validate-drift` fails.

Run it from the SKF repo root. By default it reads oh-my-skills from `../oh-my-skills`, a clone next to your SKF checkout, and it fails if no clone is there:

```bash
npm run docs:validate-drift
```

Or point it at a different local copy of oh-my-skills:

```bash
OMS=/path/to/your/oh-my-skills npm run docs:validate-drift
```

Clean output looks like this:

```
OK: skf_version x.y.z matches package.json; 4 skills checked against /home/you/oh-my-skills, no drift.
```

Dirty output lists each finding. A stale version in the docs is cited by file and line, and an anchor mismatch names the skill and the value its `metadata.json` holds, so the fix is mechanical.

---

## Reference output: oh-my-skills

Every example in this page points at [**oh-my-skills**](https://github.com/armelhbobdad/oh-my-skills), the SKF reference portfolio. Four Deep-tier skills (cocoindex, cognee, Storybook v10, uitripled), each shipping its full audit trail alongside the compiled skill. Both the worked example for this page and a public record of what the pipeline gets right and where its test still falls short. If you want to see what SKF produces when you run it on real libraries, that's the answer.
