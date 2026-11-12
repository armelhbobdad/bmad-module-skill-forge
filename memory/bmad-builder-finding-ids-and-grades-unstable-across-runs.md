---
created: "2026-09-30 15:31"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# BMad Builder finding ids and grades unstable across runs

Two BMad Builder quality analyses of the same skill (bmad-workflow-builder, or bmad-agent-builder for skf-forger, reports under `skills/reports/<skill>/quality-analysis/<timestamp>/`) cannot be compared by finding id or by grade. Ids such as `leanness-1` or `determinism-6` restart on every run, and severities change on text nobody touched. In the wave-1 re-check (`2026-09-30-1222-w1` against the `2026-09-29-2226` baseline), skf-export-skill's high count rose from 8 to 13, four of them unchanged findings re-graded up from medium, and five skills dropped from fair to poor. Content matching plus an adversarial verifier traced only two findings to wave 1. Match findings to a baseline by title, location and evidence, never by id, and verify every critical and high finding against the code before counting it. Until both are done, treat a grade drop as unproven, in any before-and-after quality gate and in any issue whose acceptance criteria cite a baseline finding id.
