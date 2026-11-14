---
created: "2026-11-13 23:25"
session: "72e9f28d-d28a-41b5-917c-b01a8cd78569"
---

# Fix lanes do not edit memory notes

An agent working a fix lane (a bmad-build worktree lane) must not commit changes to `memory/`, not even as an isolated `chore(memory):` commit, because the store's policy writes a note only once the maintainer picks it and leaves clean-up to the maintainer. On 2026-11-13 the Create Skill lane fixing #1148 moved that skill's stages out of `references/sub/` and, unasked, committed fbaa5237 ("chore(memory): Create Skill's stages sit in references/ now"), updating 7 notes that named the old paths and deleting 2; it was first waved through because the commit was isolated, until a side agent flagged it. The maintainer's decision: a lane's memory edits never ship in its fix PR; drop the `chore(memory):` commit from the lane before shipping, and once the fixes merge, open those changes as their own `chore(memory):` PR, which the maintainer reviews and merges or closes. Before shipping any lane, run `git diff --name-only origin/main...HEAD -- memory/` and route a non-empty result this way. Memory commits the maintainer did ask for still follow memory-changes-get-their-own-commits (their own commit, same PR allowed).
