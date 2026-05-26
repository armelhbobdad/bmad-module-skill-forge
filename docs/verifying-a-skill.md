---
title: Verifying a Skill
description: How to audit any SKF-compiled skill — walk every instruction back to an upstream commit and line number in under 60 seconds.
---

**Nothing is made up.** Every instruction in every skill traces back to a specific file, a specific line, and a specific commit in the upstream source. If a skill claims a function exists, you can open the real source tree at the pinned commit and see it with your own eyes. If the claim and the source disagree — that's a bug, and SKF treats it as one.

---

## The three-step audit

Pick any symbol in any SKF-compiled skill. You can trace it to the exact line of upstream source in under 60 seconds.

### 1. Open the skill's `metadata.json`

Every skill ships a `metadata.json` next to its `SKILL.md`. Note two fields:

- `source_commit` — the exact commit SHA the skill was compiled from
- `source_repo` — the upstream repository

This is the anchor. Everything else traces back to this commit.

### 2. Open the skill's `provenance-map.json`

Provenance maps live in `forge-data/{skill}/{version}/provenance-map.json` alongside each compiled skill. Find your symbol. Every entry carries its own `source_file` and `source_line`:

```json
{
  "export_name": "search",
  "export_type": "function",
  "params": ["query_text: str", "query_type: SearchType = GRAPH_COMPLETION", "top_k: int = 10"],
  "return_type": "List[SearchResult]",
  "source_file": "cognee/api/v1/search/search.py",
  "source_line": 27,
  "confidence": "T1",
  "extraction_method": "ast-grep"
}
```

The snippet above is a real entry from [`forge-data/oms-cognee/1.0.0/provenance-map.json`](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.0.0/provenance-map.json). Line number is not rounded. Confidence tier is explicit. Extraction method is named. Nothing is paraphrased.

### 3. Visit the upstream repo at the pinned commit

Open `{source_repo}` at `{source_commit}`, jump to `{source_file}` line `{source_line}`. The signature in `SKILL.md` should match what you see in the source.

If it doesn't, **that's a bug**. [Open an issue](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/new/choose). SKF will republish the skill with a new commit SHA and a new provenance map. Falsifiability isn't a feature — it's the whole deal.

### Workflow-time enforcement

The same anchor is enforced automatically by `skf-test-skill` and by gap-driven `skf-update-skill`. Before either workflow reads source at a recorded `source_line`, it runs `git rev-parse HEAD` on the local workspace and compares it to `metadata.source_commit`. If the workspace has drifted, the workflow halts with a `halted-for-workspace-drift` status and tells you the exact `git checkout {source_ref}` to re-sync — so spot-checks can never silently verify against the wrong tree. Pass `--allow-workspace-drift` to opt in to reading the current HEAD anyway; the override is recorded in the final report rather than hidden.

---

## Where to look for what

Every file in the per-skill output carries a specific job. Here's the lookup table for the really skeptical:

| Question | File |
|---|---|
| What commit was the source pinned to? | `skills/{name}/{version}/{name}/metadata.json` → `source_commit` |
| Which symbols are documented and where did each come from? | `forge-data/{name}/{version}/provenance-map.json` |
| What AST patterns were used for extraction? | `forge-data/{name}/{version}/extraction-rules.yaml` |
| What signatures, types, and examples did the extractor actually capture? | `forge-data/{name}/{version}/evidence-report.md` |
| How was the skill scored? Show me the math. | `forge-data/{name}/{version}/test-report-{name}.md` |
| How was the skill scoped, and what was deliberately left out? | `forge-data/{name}/skill-brief.yaml` |

Everything a reader needs to reconstruct the compilation is in the two sibling directories: `skills/` ships to consumers, `forge-data/` is the audit trail.

---

## The scores, including the ones we lose

Completeness scoring is never 100%. The [scoring formula](#how-the-score-is-computed) is deterministic and the pass threshold is **80%** — but every test report also logs the specific edges where a skill falls short, so the numbers aren't marketing.

Take oh-my-skills' four reference skills as an example. Their scores range from **99.0% to 99.49%** — none are perfect, and every test report names the specific drift it found:

| Skill | Score | What the report discloses |
|---|---|---|
| [oms-cocoindex](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cocoindex/0.3.37/test-report-oms-cocoindex.md) | **99.0%** | 114/114 provenance entries; 55 public-API denominator from `__init__.py` `__all__`; 20/20 sampled signatures matched. Two denominators (barrel vs. full surface) both disclosed with rationale. |
| [oms-cognee](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-cognee/1.0.0/test-report-oms-cognee.md) | **99.0%** | 34/34 exports documented; denominator is the `cognee/__init__.py` barrel (61 lines, 34 public re-exports) at pinned commit `3c048aa4` (v1.0.0). |
| [oms-storybook-react-vite](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-storybook-react-vite/10.3.5/test-report-oms-storybook-react-vite.md) | **99.49%** | 215/216 documented — the missing 1 entry is logged openly as **GAP-004**, a canonical surface count drift from the stated denominator. |
| [oms-uitripled](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-uitripled/0.1.0/test-report-oms-uitripled.md) | **99.45%** | 34-entry denominator (not 11, not 25) with the full reconciliation reasoning in the report. |

Perfection is suspicious. Visible fallibility is trustworthy. SKF writes down the edges it can't score cleanly — so you can read them and decide for yourself whether the remaining coverage is enough for your use case.

### GAP-004: a worked example of the 1% that fails

The [`oms-storybook-react-vite` test report](https://github.com/armelhbobdad/oh-my-skills/blob/main/forge-data/oms-storybook-react-vite/10.3.5/test-report-oms-storybook-react-vite.md) scores **215/216** — not 216/216. The missing 1 entry is logged as **GAP-004**: a canonical export surface count (via the provenance map) diverges from the stated denominator in metadata.json. The report names the gap, shows the math, and leaves the drift visible for the next recompilation pass. Nothing was hidden.

That's the pattern SKF asks you to trust: when scoring can't reach 100%, the report says so, cites the line, and leaves a fingerprint for the next audit.

---

## How the Score Is Computed

The Test Skill workflow (`@Ferris TS`) calculates the completeness score — a weighted measure of how thoroughly and accurately a skill documents its target. This score is the quality gate: pass and the skill is ready for export; fail and it routes to update-skill for remediation.

### Categories and weights

The score is the weighted sum of five categories:

| Category | Weight | What it measures |
|---|---|---|
| **Export Coverage** | 36% | Percentage of source exports documented in `SKILL.md` |
| **Signature Accuracy** | 22% | Documented function signatures match actual source signatures (parameter names, types, order, return types) |
| **Type Coverage** | 14% | Types and interfaces referenced in exports are fully documented |
| **Coherence** | 18% | Cross-references resolve, integration patterns are complete (contextual mode only) |
| **External Validation** | 10% | Average of skill-check quality score (0–100) and tessl content score (0–100%) |

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

**External validation** averages the two tools when both are available. When only one tool is available, that tool's score is used. When neither is available, the 10% weight is redistributed proportionally to the other active categories.

### Deterministic scoring

The weight redistribution and score aggregation are computed by a deterministic Python script ([`compute-score.py`](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-test-skill/scripts/compute-score.py)). The LLM extracts category scores from the test report, constructs a JSON input, invokes the script, and uses its output for the final score. Same inputs always produce the same score. If the script is unavailable, the LLM falls back to manual calculation using the same formulas.

### Naive vs contextual mode

Test Skill runs in one of two modes, detected automatically:

- **Contextual mode** (stack skills) — all five categories scored with the default weights above.
- **Naive mode** (individual skills) — Coherence is not scored. Its 18% weight is redistributed:

| Category | Naive Weight |
|---|---|
| Export Coverage | 45% |
| Signature Accuracy | 25% |
| Type Coverage | 20% |
| External Validation | 10% |

### Tier adjustments

Your forge tier determines which categories can be scored:

| Tier | Skipped Categories | Reason |
|---|---|---|
| **Quick** | Signature Accuracy, Type Coverage | No AST parsing available |
| **Docs-only** | Signature Accuracy, Type Coverage | No source code to compare against |
| **Provenance-map** (State 2) | Signature Accuracy, Type Coverage | String comparison only, no semantic AST verification |
| **Forge / Forge+ / Deep** | None | Full AST-backed scoring |

When categories are skipped, their combined weight is redistributed proportionally to the remaining active categories. A Quick-tier skill and a Deep-tier skill both pass at the same 80% threshold — the score reflects what your tier can actually measure.

### Hard gate

Before scoring, a hard gate scans all findings for **Critical** and **High** severity. If any are present, the pipeline blocks immediately — no score is computed and the skill cannot pass regardless of coverage percentage. Medium, Low, and Info findings pass through to scoring.

### Pass/fail

```
threshold = pipeline_default OR custom_threshold OR 80% (default)

score >= threshold  →  PASS  →  Recommend export-skill
score <  threshold  →  FAIL  →  Recommend update-skill
```

The default threshold is **80%**. Pipeline aliases declare their own defaults: `deepwiki` targets **90%**, `forge` and `forge-quick` target **80%**. You can override any default with a custom threshold (e.g., `TS[min:85]`).

When a skill scores between 80% and its target threshold (e.g., 82% against a 90% target), the soft gate falls back to the 80% floor — the skill passes, but an evidence report is written to `forge-data/{skill}/{version}/evidence-report-fallback.md` documenting the quality compromise.

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

The test report includes a score breakdown table showing each category's raw score, weight, and weighted contribution:

| Category | Score | Weight | Weighted |
|---|---|---|---|
| Export Coverage | 92% | 36% | 33.1% |
| Signature Accuracy | 85% | 22% | 18.7% |
| Type Coverage | 100% | 14% | 14.0% |
| Coherence | 80% | 18% | 14.4% |
| External Validation | 78% | 10% | 7.8% |
| **Total** | | **100%** | **88.0%** |

The report also records `analysisConfidence` (full, provenance-map, metadata-only, remote-only, or docs-only) and includes a degradation notice when source access was limited.

---

## Build-time drift detection (for docs themselves)

The SKF docs you're reading right now are themselves verified against oh-my-skills. A `docs/_data/pinned.yaml` anchor file records the exact version, commit SHA, and confidence tier of every reference skill. A Node validator (`tools/validate-docs-drift.js`) runs as part of `npm run quality` and:

1. **Confirms canonical truth** — every anchor in `pinned.yaml` is cross-checked against the actual `metadata.json` in oh-my-skills. Version, commit, tier, and authority must match.
2. **Scans docs for stale prose** — every `.md` file is grepped for `<library> v?<x.y.z>` patterns and any version that disagrees with `pinned.yaml` is flagged with file + line number.

If the validator flags drift, the CI fails before the docs get merged. It's the same "nothing is made up" contract SKF applies to skills, applied to the docs that describe SKF. When the anchor file is updated to reflect a new oh-my-skills release, the prose must update too — otherwise `npm run docs:validate-drift` blocks the merge.

You can run it yourself from the SKF repo root:

```bash
npm run docs:validate-drift
```

Or point it at a different local copy of oh-my-skills:

```bash
OMS=/path/to/your/oh-my-skills npm run docs:validate-drift
```

Clean output looks like this:

```
OK: 4 skills checked against /home/you/oh-my-skills, no drift.
```

Dirty output cites exact file:line locations so the fix is mechanical.

---

## Reference output: oh-my-skills

Every example in this page points at [**oh-my-skills**](https://github.com/armelhbobdad/oh-my-skills), the SKF reference portfolio. Four Deep-tier skills (cocoindex, cognee, Storybook v10, uitripled), each shipping its full audit trail alongside the compiled skill. Both the worked example for this page and the continuing proof that the pipeline does what it says. If you want to see what SKF produces when you run it on real libraries, that's the answer.
