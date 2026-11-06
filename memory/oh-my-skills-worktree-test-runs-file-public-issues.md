---
created: "2026-11-05 15:00"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# A live SKF test run in an oh-my-skills worktree files public health-check issues

Claude Code shares a repository's memory across its git worktrees, so a `claude -p` run in a worktree of `~/Projects/OSS/oh-my-skills` reads that project's memory note `skf-health-check-file-issues.md`. The note records the maintainer's 2026-11-02 instruction, "the health check should open the issue to the target repo. Do not store anything in the local queue", and overrides the headless [Q] default of `src/shared/health-check.md` §4. A run there therefore files its findings with `gh issue create` under the maintainer's account: the 6.0.0 validation pipeline `SF QS TS` opened #885 that way. The note is intended and stays as written. For verification runs started from this repo, use a separate `git clone` in the scratchpad, never `git worktree add`, so the run has its own memory folder and a headless finding is queued inside the clone and deleted with it (confirm on the first such run that the transcript never reads the note). Also pass `--no-health-check` where it exists: only `skf-test-skill` accepts it, while Setup, Quick Skill, the other workflows and Ferris pipelines have no such switch.
