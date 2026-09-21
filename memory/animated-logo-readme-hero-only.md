---
created: "2026-04-25 01:41"
session: "7cda5ae2-db1d-4021-955f-3657b5d0b923"
source: claude-mem
source_table: session_summaries
source_ids: [2210]
---

# Animated logo only in the README hero

`website/public/img/skf-logo-animated.svg` is used only in the README hero (`README.md:5`, `width="120"`); the docs site header keeps the static `skf-logo.svg` (`website/astro.config.mjs`, Starlight `logo.src`). The header renders the logo at roughly 28px, where the animation's details collapse to sub-pixel movement and only distract, so the split is deliberate. Do not swap the header to the animated file to "match" the README; the animation earns its place only at hero scale.
