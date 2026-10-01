---
languageCorporaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-language-corpora.py'
  - '{project-root}/src/shared/scripts/skf-language-corpora.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1a §6b: Seed Companion Corpora (whole-language references only)

Loaded by `step-auto-scope.md` §6 only when §3 classified the repo as `language-reference` **via a whole-language signal**: its `signals` array holds a `grammar_file:` or `tree_triad:` entry (a compiler, interpreter or grammar repo such as rust-lang/rust, TypeScript or CPython). A `language-reference` that fired only from `parser_producer:` or `parser_dep:` signals (a parser *library* such as pest or lalrpop) never loads it: there the code **is** the product, so no companion prose is needed and no caveat applies.

A whole-language skill's value is in the language's **prose** (the guide or Book, the standard and library API docs, idioms), not the compiler internals. Seed those canonical corpora so the forged skill teaches the language rather than its implementation. This file sets `{corpus_seeds}`, `{corpus_caveat}` and the Companion Corpora subsection, then returns to §6. It never halts: the lookup is best-effort.

## MANDATORY SEQUENCE

### 1. Look Up the Canonical Corpora

**Resolve `{languageCorporaHelper}`** from `{languageCorporaProbeOrder}` (first existing path wins). When neither path exists, record the warning `language_corpora_unavailable: skf-language-corpora.py is missing` with `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '<the warning>'` and treat `{corpus_seeds}` as empty.

1. **The corpus language key `{corpus_language}`** ← `{detected_language}` from §5, which a manifest-less toolchain such as CPython or Ruby gets from its source files.
2. **Look up canonical corpora:**
   ```bash
   uv run {languageCorporaHelper} --language {corpus_language}
   ```
   - exit 0: parse the `[{url, label, source}]` array (each seed carries `source: language-registry`); these are `{corpus_seeds}`.
   - exit 1: no registry entry (a long-tail language), so `{corpus_seeds}` is empty (README detection in brief-skill remains the only source).
   - exit 2: record the warning `language_corpora_failed: <its first stderr line>` the same way and treat it as empty.
3. Record `{N}` = the number of seeds and `{corpus_labels}` = their labels, comma-joined.

### 2. Build the Caveat and the Brief's Doc URLs

`{corpus_caveat}`, which §6 appends to `scope.notes`, tells the operator that a code-only whole-language skill is low-value:

- `{N}` ≥ 1: `" LANGUAGE-REFERENCE CAVEAT: this skill's value is the {corpus_language} prose (guide/Book + std/library docs), not compiler internals. Seeded {N} corpus URL(s): {corpus_labels}. create-skill foregrounds this registry prose as the skill's Language Guide and demotes compiler-internal signatures to a reference-only section: review the forged skill if compiler internals still dominate."`
- `{N}` == 0: `" LANGUAGE-REFERENCE CAVEAT: no canonical corpora were found for {corpus_language} (README detection and the registry both came up empty). This skill is LOW-VALUE as code-only: attach the {corpus_language} guide + std/library docs manually (re-run with a doc URL, or enrich via US) before forging."`

`{corpus_doc_urls}`, which §8 writes as the brief's `doc_urls`: one `{"url": "{seed.url}", "label": "{seed.label}", "source": "{seed.source}"}` per seed (its `source` is `language-registry`), so the language's prose is fetched and assembled alongside the code (brief-skill's README detection then merges more docs on top, existing entries winning); null when `{N}` is 0.

### 3. The Companion Corpora Subsection

§7 appends this to the report, so the operator sees whether the skill has the prose that makes it useful. The status comes from the **final** brief `doc_urls` (the entries that will actually be fetched), not the seed count alone:

```markdown
## Companion Corpora (language-reference)

**Why:** A whole-language skill's value is its prose (guide/Book, std/library docs, idioms), not compiler internals.
**Corpora in brief doc_urls:** {final_doc_urls_count}
  - {label}: {url}   # one line per doc_urls entry
**Status:** {ATTACHED: canonical corpora present | DEGRADED: code-only, no canonical corpora; attach the {corpus_language} guide + std/library docs before forging}
```

Then return to `step-auto-scope.md` §6.
