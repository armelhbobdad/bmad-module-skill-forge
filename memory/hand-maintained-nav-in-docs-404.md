---
created: "2026-04-18 00:25"
session: "32e9eb66-b5be-4352-bf0c-d38d8793dc64"
source: claude-mem
source_table: observations
source_ids: [6253, 6254]
---

# Hand-maintained nav list in docs/404.md

`docs/404.md` (rendered by `website/src/pages/404.astro`) carries its own hard-coded Why / Try / Reference link list plus a deep anchor into `verifying-a-skill.md#build-time-drift-detection-for-docs-themselves`; nothing generates it from the sidebar in `website/astro.config.mjs`. It was forgotten in the IA restructure (user: "we forgot to rework the @docs/404.md page :(") and has drifted again since: the sidebar's Try group now has Forge-Auto and Campaign, and the 404 page lists neither. Whenever a docs page is added, renamed or regrouped, edit `docs/404.md` by hand in the same change; `npm run validate:docs-links` only proves its links resolve, not that the list is complete.
