---
created: "2026-10-13 08:11"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# bmad-build specs over the token target kept whole

bmad-build's SCOPE STANDARD in `_bmad/render/bmad-build/<snapshot>/workflow.md` targets 900 to 1600 tokens per spec and says "Neither limit is a gate." Even so, step 6 of `step-02-plan.md` asks whether to split or keep any spec above 1600 tokens (the comment in `spec-template.md` targets 900 to 1300). In every run that asked, from 2026-10-11 to 2026-10-13 (issues between #711 and #750, the last run eleven specs of about 1670 to 2560 tokens), the maintainer answered "Keep full specs (Recommended)". Each time the excess was exact commands, real-data paths and cross-spec agreements rather than extra goals, so each issue kept one spec and one PR. Offer keeping such a spec whole as the recommended option, and propose a split only when the spec holds two independently shippable goals by the SCOPE STANDARD's single-goal rule.
