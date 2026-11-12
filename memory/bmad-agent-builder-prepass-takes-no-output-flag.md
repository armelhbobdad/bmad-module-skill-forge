---
created: "2026-10-02 22:38"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# bmad-agent-builder prepass takes no output flag

For skf-forger's quality analysis the prepass is `.claude/skills/bmad-agent-builder/scripts/prepass.py`, which takes only the positional `agent_dir` and prints its JSON to stdout, while the bmad-workflow-builder scanners used for the 15 workflows (such as `prepass-prompt-metrics.py`) take `--output`/`-o`. A batch prepass loop that passes `-o` to every skill exits 2 for the forger with `usage: prepass.py [-h] agent_dir` and `prepass.py: error: unrecognized arguments: -o`, and writes no `prepass.json` (hit on 2026-10-02). Redirect stdout instead: `uv run .claude/skills/bmad-agent-builder/scripts/prepass.py src/skf-forger > skills/reports/skf-forger/quality-analysis/<TS>/prepass/prepass.json`. Otherwise an all-skills re-analysis silently loses the forger's prepass data.
