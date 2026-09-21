---
created: "2026-03-12 15:23"
session: "184c6ba9-5ed8-4549-8c05-d3635dfc1251"
source: claude-mem
source_table: observations
source_ids: [824, 825]
---

# /bmad-help mentions carry the standalone disclaimer

`/bmad-help` is provided by BMad Method (github.com/bmad-code-org/BMAD-METHOD), not by a standalone SKF install, so every mention of it in user-facing text must say so. The user set this rule: "We should precise it is only available when the module is installed along side the BMAD-METHOD ecosystem. The standalone installatino does not provide such command." The two current mentions comply — docs/getting-started.md:206 carries the italic disclaimer *Provided by the BMAD Method — not available in standalone SKF installations* and docs/troubleshooting.md:66 is phrased "If `/bmad-help` is installed (via full BMAD Method)"; README.md and docs/examples.md no longer mention it at all. Any new mention (README, website, workflow prose, help text) needs the same qualifier, or standalone users will try a command they do not have.
