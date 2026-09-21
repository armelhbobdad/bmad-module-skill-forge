---
created: "2026-05-27 01:50"
session: "ebf02137-199b-44c4-afac-ca85f47ff9ef"
source: claude-mem
source_table: observations
source_ids: [13818]
---

# yml/no-empty-mapping-value on commented YAML placeholders

`npm run lint` runs `eslint . --ext .js,.cjs,.mjs,.yaml --max-warnings=0` (package.json:43) with `yml.configs['flat/recommended']` enabled (eslint.config.mjs:54), and `yml/no-empty-mapping-value` is switched off only for `.github/**/*.yaml`, so every YAML file under `src/` is checked. A template key such as `targets:` followed only by commented example entries fails with `yml/no-empty-mapping-value`: comments are not values, so the key parses as an empty mapping. Give the key an explicit empty value (`targets: []`, `""`, or `null`) and keep the example entry structure as standalone comment lines next to it, as `src/skf-campaign/templates/campaign-brief-template.yaml` does for `targets`. Do not silence the rule for `src/` — CONTRIBUTING.md forbids disabling a rule to make the linter pass.
