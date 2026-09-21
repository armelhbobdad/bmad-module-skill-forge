---
created: "2026-05-26 12:39"
session: "d3f0694b-da9a-40e4-9a86-7baaa7e3f97d"
source: claude-mem
source_table: observations
source_ids: [13105, 13107, 13157]
---

# Story-automator artifact-count collision on reused story prefixes

`bmad-story-automator`'s create-step verifier (`create_story_artifact` in `src/story_automator/core/success_verifiers.py` of the locally installed, gitignored `.claude/skills/bmad-story-automator`) globs `_bmad-output/implementation-artifacts/{story_prefix}-*.md` and expects exactly one match, so any leftover story file sharing the numeric prefix makes it return `verified=false reason=unexpected_story_artifact_count` even though the create session itself succeeded. This repo reuses story numbers across planning cycles: the April release-pipeline epic left `1-2-create-release-github-environment-with-required-reviewer.md` and `1-3-register-npm-trusted-publisher-for-release-yaml-workflow.md`, and on 2026-05-26 the source-intelligence epic's `1-2-doc-detection-chain-shared-module.md` and `1-3-doc-tracking-at-compile-time.md` both collided with them. Before starting a new epic cycle, move the previous cycle's same-prefix story files into `_bmad-output/implementation-artifacts/archive/` (where the April ones now live). `_bmad-output/` is gitignored, so this is per-clone hygiene that nothing in git records.
