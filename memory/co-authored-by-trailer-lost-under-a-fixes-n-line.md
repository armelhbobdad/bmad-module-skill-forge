---
created: "2026-11-09 14:10"
session: "77252030-8c80-4285-b88e-c15f43930eb7"
---

# Co-Authored-By trailer lost under a Fixes #N line

When a commit message ends with `Fixes #892` (or `Refs #N`) directly followed by `Co-Authored-By: Claude ...` with no blank line between, git parses no trailer, because `Fixes #N` is not a `Key: value` line and the whole paragraph reads as body text. `git log -1 --format='%(trailers:key=Co-Authored-By)' 0c453015` then prints nothing and GitHub drops the co-author credit, though the `Fixes` keyword still closes the issue. Eleven commits merged to main on 2026-11-09 through #1052, #1053 and #1054 (0c453015, 072c34fe and e8f5c6fa among them) lost their co-author this way, which only rewriting main could repair. Put a blank line between the `Fixes #N` or `Refs #N` lines and `Co-Authored-By:`, as main's other commits do. Before pushing, check `git log --format='%h %(trailers:key=Co-Authored-By,valueonly)' origin/main..HEAD` for an empty value (`git interpret-trailers --parse` on a draft shows the same), and reword unpushed commits with their trees unchanged.
