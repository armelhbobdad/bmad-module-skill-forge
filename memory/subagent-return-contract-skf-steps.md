---
created: "2026-05-16 00:52"
session: "368f6026-a320-4e3c-ab70-9bedb28ba90c"
source: claude-mem
source_table: observations
source_ids: [9939, 9940, 9941, 9952]
---

# Subagent return contract in skf step files

Every subagent delegation in an skf-* step file states the exact JSON shape inline and says the worker "returns only this JSON shape — no prose, no commentary, no markdown fences", with the parent stripping wrapping fences before parsing and a main-thread fallback when subagents are unavailable; current instances are `src/skf-test-skill/references/coverage-check.md` §2, `coherence-check.md` §3-4, `src/skf-analyze-source/references/map-and-detect.md` §2, `src/skf-update-skill/references/detect-changes.md` and `re-extract.md`. The convention replaced "DO NOT BE LAZY" admonishments with the technical instruction; some older delegations still say "launch a subprocess" (scan-project.md, re-index.md, re-extract.md §1) without the contract. Copy the full contract for any new delegation — without it workers return prose the parent must re-read, and the workflow-builder quality scan flags it.
