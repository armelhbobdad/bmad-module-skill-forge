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

Provenance maps live in `forge-data/{skill}/{version}/provenance-map.json` in the project that compiled the skill. They are part of the audit trail and do not ship inside the skill package, so for a published skill, look in the repository that publishes it (oh-my-skills keeps its `forge-data/` folder public). Find your symbol. Every entry carries its own `source_file` and `source_line`. The skill's `SKILL.md` also cites each signature inline, for example `[AST:cognee/api/v1/search/search.py:L27]`, so you can often go straight to step 3:

```json
{
  "export_name": "search",
  "export_type": "async_function",
  "source_library": "cognee",
  "params": ["query_text: str", "query_type: SearchType = SearchType.GRAPH_COMPLETION"],
  "return_type": "List[SearchResult]",
  "source_file": "cognee/api/v1/search/search.py",
  "source_line": 27,
  "confidence": "T1",
  "extraction_method": "ast-grep",
  "ast_node_type": "function_definition",
  "signature_source": "T1"
}
```

The snippet above follows the `search` entry in [`forge-data/oms-cognee/1.0.0/provenance-map.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.0.0/provenance-map.json), shortened to its first two parameters (the real entry lists all 20). It points at the exact line where `search` is defined, states its confidence tier, and names how it was found: a T1 entry comes from ast-grep reading the code structure, and an entry found by plain source reading is T1-low.

### 3. Visit the upstream repo at the pinned commit

Open `{source_repo}` at `{source_commit}`, jump to `{source_file}` line `{source_line}`. The signature in `SKILL.md` should match what you see in the source.

If it doesn't, **that's a bug**. For a skill you built, Test Skill (`@Ferris TS`) rates a signature mismatch as a High-severity gap, and Update Skill (`@Ferris US`) with `--from-test-report` repairs the gaps a test report lists. If you think SKF extracted it wrong, [open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). Falsifiability isn't a feature. It's the whole deal.

### Workflow-time enforcement

SKF checks the same anchor while it works, so a skill and its citations always describe one commit.

- **Update Skill (`@Ferris US`)**, for a skill built from a remote repository, reads the source in a private checkout at the commit that the skill's `source_ref` (or the `--target-ref` you pass) points to now. When it writes, it records that commit as the new `source_commit`. If it could not move SKF's shared clone to that commit, its report says why and how to move it.
- **Test Skill (`@Ferris TS`)**, and **Update Skill with `--from-test-report`** (a repair driven by a test report's gaps), first compare the commit your local source is on (`git rev-parse HEAD`) with `metadata.source_commit`. If they differ, they stop before reading any source: Test Skill with `workspace-drift`, Update Skill with `halted-for-workspace-drift`. The message names the commit to check out, so a spot-check never quietly reads the wrong tree.
- To read the current commit anyway, pass `--allow-workspace-drift`. The final report records the override. In Test Skill, a pass under this override is recorded as `pass-with-drift`, and SKF recommends Update Skill instead of export.

---

## Where to look for what

Every file in the per-skill output carries a specific job. Here's the lookup table for the really skeptical:

| Question | File |
|---|---|
| What commit was the source pinned to? | `skills/{name}/{version}/{name}/metadata.json` → `source_commit` |
| Which symbols are documented and where did each come from? | `forge-data/{name}/{version}/provenance-map.json` |
| What AST patterns were used for extraction? | `forge-data/{name}/{version}/extraction-rules.yaml` |
| What signatures, types, and examples did the extractor actually capture? | `forge-data/{name}/{version}/evidence-report.md` |
| How was the skill scored? Show me the math. | `forge-data/{name}/{version}/test-report-{name}-{run_id}.md` (one report per run, named with the run ID; the newest one counts. Older reports, like the oh-my-skills ones linked below, are named `test-report-{name}.md`) |
| How was the skill scoped, and what was deliberately left out? | `forge-data/{name}/skill-brief.yaml` |

Everything a reader needs to reconstruct the compilation is in the two sibling directories: `skills/` ships to consumers, `forge-data/` is the audit trail.

---

## The scores, including the ones we lose

The [scoring formula](#how-the-score-is-computed) is deterministic and the pass threshold is **80%**. Every test report also logs the specific edges where a skill falls short, so the numbers aren't marketing.

Take oh-my-skills' four reference skills as an example. Their scores range from **99.0% to 99.49%**. None is perfect, and every test report names the specific drift it found:

| Skill | Score | What the report discloses |
|---|---|---|
| [oms-cocoindex](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cocoindex/0.3.37/test-report-oms-cocoindex.md) | **99.0%** | 114/114 provenance entries; 55 public-API denominator from `__init__.py` `__all__`; 20/20 sampled signatures matched. Two denominators (barrel vs. full surface) both disclosed with rationale. |
| [oms-cognee](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.0.0/test-report-oms-cognee.md) | **99.0%** | 34/34 exports documented; denominator is the `cognee/__init__.py` barrel (61 lines, 34 public re-exports) at pinned commit `3c048aa4` (v1.0.0). |
| [oms-storybook-react-vite](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-storybook-react-vite/10.3.5/test-report-oms-storybook-react-vite.md) | **99.49%** | 215/216 documented. **GAP-004** logs the one-count gap openly: all 215 exports in the provenance map are documented, and the 216th is a stale count in `metadata.json`, not a missing export. |
| [oms-uitripled](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-uitripled/0.1.0/test-report-oms-uitripled.md) | **99.45%** | 34-entry denominator (not 11, not 25) with the full reconciliation reasoning in the report. |

Perfection is suspicious. Visible fallibility is trustworthy. SKF writes down the edges it can't score cleanly, so you can read them and decide for yourself whether the remaining coverage is enough for your use case.

### GAP-004: a worked example of a logged gap

The [`oms-storybook-react-vite` test report](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-storybook-react-vite/10.3.5/test-report-oms-storybook-react-vite.md) scores Export Coverage at **215/216**, not 216/216. The report logs the gap as **GAP-004**: once duplicate entries are folded, the provenance map holds 215 unique exports, all documented, while `metadata.json` still states a denominator of 216. The report names the gap, shows the math, and leaves the drift visible for the next recompilation pass. Nothing was hidden.

That's the pattern SKF asks you to trust: when scoring can't reach 100%, the report says so, cites the line, and leaves a fingerprint for the next audit.

---

## How the Score Is Computed

The Test Skill workflow (`@Ferris TS`) calculates the completeness score: a weighted measure of how thoroughly and accurately a skill documents its target. This score is the quality gate. A pass means the skill is ready for export. A fail routes it to Update Skill for repair. When there is too little evidence to grade the skill, the result is INCONCLUSIVE, and SKF asks you to review it by hand.

### Categories and weights

The score is a weighted sum of up to five categories. The weights below are the starting point. No single run scores all five: naive mode drops Coherence, and contextual mode drops Signature Accuracy and Type Coverage.

| Category | Weight | What it measures |
|---|---|---|
| **Export Coverage** | 36% | Percentage of source exports documented in `SKILL.md` |
| **Signature Accuracy** | 22% | Documented function signatures match actual source signatures (parameter names, types, order, return types) |
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

The weight redistribution and score aggregation are computed by a deterministic Python script ([`compute-score.py`](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-test-skill/scripts/compute-score.py)). The LLM extracts category scores from the test report, constructs a JSON input, invokes the script, and uses its output for the final score. Same inputs always produce the same score. If the script is unavailable, the LLM falls back to manual calculation using the same formulas.

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
| **Source not on disk** (Test Skill works from the saved provenance map) | Signature Accuracy, Type Coverage | Names can be matched, but signatures cannot be re-checked without the source |
| **Stack skill**, any tier | Signature Accuracy, Type Coverage | The signatures and types belong to the libraries the stack combines |
| **Reference-app skill**, any tier | Signature Accuracy, Type Coverage | It documents how parts are wired together, not a library's exports |
| **Forge / Forge+ / Deep** individual skill with its source on disk | None | Full AST-backed scoring |

When categories are skipped, their combined weight is redistributed proportionally to the remaining active categories. A Quick-tier skill and a Deep-tier skill both pass at the same 80% threshold. The score reflects what your tier can actually measure.

### Hard gate

Before scoring, a hard gate scans all findings for **Critical** and **High** severity. If any are present, Test Skill stops there: no score is computed, the result is FAIL whatever the coverage, and SKF recommends Update Skill. Medium, Low, and Info findings pass through to scoring.

### Pass/fail

```
threshold = --threshold=<N> if you passed it, else the pipeline default, else default_threshold (80 unless your team changed it)

score >= threshold  →  PASS  →  Recommend export-skill
score <  threshold  →  FAIL  →  Recommend update-skill
too little evidence  →  INCONCLUSIVE  →  Review by hand
```

INCONCLUSIVE means fewer than two categories were left to score, or a Quick-tier skill had only Export Coverage to go on. It is neither a pass nor a fail: SKF does not export the skill or retry, and it leaves the decision to you. To get a verdict, add evidence and test again: install skill-check so `npx skill-check` runs without a download, or install ast-grep and re-run `@Ferris SF` to move up a tier.

The default threshold is **80%**. Pipeline aliases declare their own defaults: `forge-auto` targets **90%**, `forge` and `forge-quick` target **80%**. To set the threshold for one run, pass `--threshold=85` to Test Skill, or write `TS[min:85]` inside a pipeline sequence. To change the default for your whole team, set `default_threshold` in `_bmad/custom/skf-test-skill.toml`. That file is read only in a project where the BMAD Method installer has added its customization script. With SKF installed alone, pass `--threshold` on each run instead (see [Customizing a Workflow](/docs/workflows.md#customizing-a-workflow)).

Two caps turn a pass into a fail. If a helper that Test Skill needs is missing, such as `uv` or `python3`, the run is marked `degraded` and cannot pass until you install it. A docs-only stack skill that neither skill-check nor Tessl Review scored is capped the same way, because too little is left to grade it. A docs-only individual skill in that state has only Export Coverage left, so it ends INCONCLUSIVE instead. When your target is above 80%, the fallback below still accepts a capped run whose score is 80% or more.

When a skill scores between 80% and its target threshold (for example, 82% against a 90% target), it still passes at the 80% floor, and Test Skill writes an evidence report to `forge-data/{skill}/{version}/evidence-report-fallback.md` that records the shortfall.

A run that found drift and went on under `--allow-workspace-drift` ends **pass-with-drift**, not PASS, when it reaches the threshold. It read a different commit than the skill cites, so test again on the pinned commit before you export.

### Gap severities

When the score is calculated, each finding is classified by severity to guide remediation:

| Severity | Examples |
|---|---|
| **Critical** | Missing exported function/class documentation |
| **High** | Signature mismatch between source and `SKILL.md` |
| **Medium** | Missing type/interface documentation; scripts/assets directory inconsistencies |
| **Low** | Missing optional metadata or examples; description optimization opportunities |
| **Info** | Style suggestions; discovery testing recommendations |

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

The report also records `analysisConfidence` (full, degraded, provenance-map, metadata-only, remote-only, or docs-only) and includes a degradation notice when source access was limited.

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

Every example in this page points at [**oh-my-skills**](https://github.com/armelhbobdad/oh-my-skills), the SKF reference portfolio. Four Deep-tier skills (cocoindex, cognee, Storybook v10, uitripled), each shipping its full audit trail alongside the compiled skill. Both the worked example for this page and the continuing proof that the pipeline does what it says. If you want to see what SKF produces when you run it on real libraries, that's the answer.
