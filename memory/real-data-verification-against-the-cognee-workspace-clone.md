---
created: "2026-10-09 12:21"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# Real-data verification against the cognee workspace clone

The maintainer's rule for fix batches: "Verify each fix on real data where the issue came from it". The data is oh-my-skills at `~/Projects/OSS/oh-my-skills` (skill `oms-cognee`, `forge-data/oms-cognee/{0.5.8,1.0.0,1.6.2}` and its `skill-brief.yaml`) and the cognee source in SKF's workspace clone `~/.skf/workspace/repos/github.com/topoteretes/cognee` (v1.0.0 = `3c048aa4`, v1.6.2 = `ba3631f2`). Extract a version with `git -C <clone> archive <commit> | tar -x -C <scratch dir>`, in the maintainer's words "use git archive into a scratch folder, never checkout". The clone is the persistent cache SKF's own workflows reuse, so a checkout moves the tree other runs read; run nothing else there either, since even `git status --short` can refresh its index. Copy a brief or provenance map into the scratch folder before editing it for a test case, and treat the oh-my-skills checkout as read only. Extracts are large (about 8,400 files for one cognee copy), so reuse one whose pyproject version matches and delete it after use.
