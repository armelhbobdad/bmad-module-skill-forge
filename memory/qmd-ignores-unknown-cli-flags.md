---
created: "2026-05-02 22:06"
session: "802545bc-7c1c-48c9-ae99-7638e53036b3"
source: claude-mem
source_table: both
source_ids: [8408, 8409, 8410, 8435]
---

# qmd silently ignores unknown CLI flags

qmd's CLI parses with `parseArgs({ strict: false })` (`@tobilu/qmd` 2.8.3, `dist/cli/qmd.js:2668` — 'Allow unknown options to pass through'), so an invented flag such as `--query`, `--collections "*-brief"` or `--top 3` exits 0 and is simply dropped instead of erroring; qmd's own CHANGELOG (#536) records `--glob` being lost the same way. The portfolio-similarity check in `src/skf-brief-skill/references/portfolio-similarity-check.md` first shipped with exactly those fabricated flags and, behind its warn-and-continue wrapper, silently never ran until code review caught it. The real `qmd query` surface is positional search text, `-n <num>`, `--min-score <num>`, `-c/--collection <name>` (repeatable in 2.8.3), `--format json`, `--no-rerank`; there is no glob collection selection, so enumerate with `qmd collection list | awk '$1 ~ /-brief$/ {print $1}'` and query one collection per call. Check every qmd flag against `qmd --help` before trusting a zero exit code.
