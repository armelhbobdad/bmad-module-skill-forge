---
created: "2026-05-15 23:49"
session: "368f6026-a320-4e3c-ab70-9bedb28ba90c"
source: claude-mem
source_table: observations
source_ids: [9878, 9879, 9973, 9980]
---

# Subagents cannot write findings.md report files

Background subagents told to write a quality-scan report to `src/{skill}/.analysis/{timestamp}/findings.md` refuse: the Claude Code subagent system prompt forbids writing report/summary/findings/analysis `.md` files, and the task returns "The harness rejected the file write. Per harness rules, I must return findings as text rather than write a report file." (sometimes reported as "system policy blocked"). In two runs on 2026-05-15, 3 of 5 parallel skf-* scan agents left no `findings.md` while their JSON prepass files were written, and the parent had to recover each report from the task output and persist it itself with a heredoc (`cat > .../findings.md <<'EOF'`) before aggregating. `.analysis/` is still the gitignored home for these artifacts (`.gitignore`: `**/.analysis`). When fanning out scans, tell subagents to return the report as text, have the parent write the file, and verify with `find src -path '*/.analysis/*/findings.md'` before aggregating.
