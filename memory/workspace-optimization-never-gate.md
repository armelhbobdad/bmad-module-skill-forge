---
created: "2026-04-09 21:47"
session: "3e281d7e-1ec7-479a-91be-63b3bc827798"
source: claude-mem
source_table: session_summaries
source_ids: [1524, 1525, 1531]
---

# Workspace clone cache is an optimization, never a gate

The persistent clone cache at `~/.skf/workspace/repos/{host}/{owner}/{repo}/` (override `SKF_WORKSPACE`; `src/skf-create-skill/references/source-resolution-protocols.md` §Forge/Deep) is an optimization, never a gate: any workspace failure — auth, disk full, corrupt state, timeout — falls back to ephemeral cloning (§5 'Ephemeral fallback (on any workspace failure)'), the checkout is ground truth, and every CCC/QMD index built on it is regenerable. The cache is deliberately invisible in user-facing `docs/` — the only surface is the one-line first-use message `Caching source at {workspace_repo_path} (saves time on re-forges)` — until a `skf workspace` CLI subcommand ships (`tools/cli/commands/` still has only install, status, uninstall, update). Do not add workspace-management docs or make a step depend on the workspace being present.
