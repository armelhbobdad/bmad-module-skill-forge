---
created: "2026-10-04 14:22"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Isolating live qmd runs from the maintainer's qmd index

To keep the maintainer's `~/.cache/qmd/index.sqlite`, `~/.config/qmd/index.yml` and `trusted.json` unchanged during a live check of SKF's qmd commands (qmd 2.8.3, the v3.0.0 pre-release tool check on 2026-10-04), point `XDG_CACHE_HOME`, `QMD_CONFIG_DIR` and `XDG_CONFIG_HOME` at a scratch folder. That moves the index, config, `trusted.json`, model cache and PID files there, since qmd's `dist/store.js`, `dist/collections.js`, `dist/trust.js` and `dist/llm.js` read those variables. `--index <name>` does not isolate: it writes `<name>.sqlite` and `<name>.yml` next to the maintainer's own files in `~/.cache/qmd` and `~/.config/qmd`, and SKF's command lines pass no `--index` anyway. `qmd embed`, `qmd vsearch` and `qmd query` download models when none is cached (embeddinggemma-300M-Q8_0, a 1.7B model and a reranker), so skip them unless the download is wanted. This serves the rule that verification runs leave the host unchanged (memory/live-claude-p-runs-leak-into-tmp-and-claude-projects).
