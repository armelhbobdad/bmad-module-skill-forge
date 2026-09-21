---
created: "2026-03-30 00:27"
session: "aca34707-85ad-497a-9123-a15069c33fc5"
source: claude-mem
source_table: observations
source_ids: [3527, 3531, 3537]
---

# Absent optional brief fields must be defaulted by the consuming step

Generated skills silently never got `scripts/` or `assets/`: `src/shared/scripts/skf-write-skill-brief.py` only writes `scripts_intent`/`assets_intent` into `skill-brief.yaml` when they differ from the default `detect`, and the create-skill extraction step's skip condition only mentioned an explicit `none`, so the executing LLM treated an absent field as "skip" — an LLM step does not infer that a missing field means its documented default. The explicit rule now lives in `src/skf-create-skill/references/extract.md` §4c and `extraction-patterns-tracing.md`: absent resolves to `detect`, only an explicit `none` disables that one category, and `skf-detect-scripts-assets.py` defaults both flags to `detect`. For any new optional brief field, either emit the default explicitly or spell out the absent case in every consuming step; the brief writer deliberately omits default values (same pattern for `source_authority`) to avoid false-drift diffs, so the consumer side is the only safety. User: "Do we really generate asset and scripts? I never got them during my multiple tests."
