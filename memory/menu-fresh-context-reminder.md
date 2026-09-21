---
created: "2026-04-06 15:45"
session: "84555cd7-d955-4ef1-a202-5669ff25ae90"
source: claude-mem
source_table: observations
source_ids: [4453, 4454]
---

# Menu must end with the fresh-context reminder

User rule (2026-04-06): "Every time we should the command menu, explicitly show this message: "Run each workflow in a fresh context window for best results." . For example, After SF, Redisplay menu . This extends the feat from the commit 469fb994". It was implemented in commit 3085fb7c as a menu rule in `tools/cli/lib/compiler.js` (`Always end the menu with: "Run each workflow in a fresh context window for best results."`), but commit 6320b577 two days later (migration to the BMad skill-driven standard) deleted `compiler.js` and turned the agent into `src/skf-forger/SKILL.md`, which carries no such line: `grep -rn "fresh context window" src` returns nothing. Only the docs still carry the underlying tip (`README.md:84` "Start a fresh conversation before each workflow…", `docs/getting-started.md:129` "One workflow per session"), not what Ferris displays. Any edit to the "On Activation" greeting or the re-present-menu wording in `src/skf-forger/SKILL.md` should restore the sentence verbatim on every menu display, including redisplay after a workflow such as SF.
