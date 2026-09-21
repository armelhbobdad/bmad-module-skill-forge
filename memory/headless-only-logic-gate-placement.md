---
created: "2026-05-02 21:36"
session: "802545bc-7c1c-48c9-ae99-7638e53036b3"
source: claude-mem
source_table: observations
source_ids: [8369, 8371, 8372]
---

# Headless-only detection belongs in the GATE section, not inside an interactive prompt

skf-brief-skill's `source_authority` auto-detection was first written inside the interactive §3.3 prompt of `src/skf-brief-skill/references/gather-intent.md`; an agent reading the step in order could run the `gh api user` probe right after the user had answered the maintainer/community question and overwrite their answer. The fix (e931d05, 2026-05) split it: the headless-only branch lives in the step's §8 GATE section, after the validator's `normalized` object is consumed (now `references/headless-source-authority-detection.md`, loaded only when `{headless_mode}` is true, `source_authority` is absent and the target is a GitHub URL), and the prompt carries an explicit guard — "**Interactive only** — skip this prompt entirely when `{headless_mode}` is true". Apply the same split to any future headless heuristic: guard the prompt, detect at the gate, and lower-case both sides before comparing GitHub logins because the API preserves case while owner matching is case-insensitive.
