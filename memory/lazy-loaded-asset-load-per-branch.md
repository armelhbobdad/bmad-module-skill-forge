---
created: "2026-05-02 21:11"
session: "802545bc-7c1c-48c9-ae99-7638e53036b3"
source: claude-mem
source_table: observations
source_ids: [8344, 8345]
---

# Lazy-loaded asset Load directive per branch

In `src/skf-brief-skill/references/gather-intent.md` §7b the description-voice examples live in a lazy-loaded asset (`{descriptionVoiceExamplesPath}` → `assets/description-voice-examples.md`). When the examples were first extracted from the step prose only the interactive branch said `load {descriptionVoiceExamplesPath}`; the headless branch read "run the same synthesis" and code review flagged that the load was only implicit at the point of use. Every branch that consumes a lazy-loaded reference must state its own `load {file}` (interactive, headless `intent`, GitHub-description seed), and a branch that does not need it says so explicitly ("the generic fallback does not need the asset"). The same shape now runs through the file (portfolio-similarity, draft-checkpoint, headless source-authority: each branch either loads or says "skip the load"), so when moving prose into an asset, walk each branch instead of relying on "the same as above".
