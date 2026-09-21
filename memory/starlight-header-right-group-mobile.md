---
created: "2026-04-04 22:13"
session: "7070fa3d-9a71-4237-8b63-c0f357f172e0"
source: claude-mem
source_table: session_summaries
source_ids: [1293, 1294]
---

# Starlight header right-group is hidden on phones

In `website/src/components/Header.astro` the right-hand utility cluster is `<div class="sl-hidden md:sl-flex print:hidden right-group">` (line 43), so anything placed there (social icons, theme and language selects, or a new control) is not rendered below Starlight's `md` breakpoint; the npm version badge was invisible on phones when it first lived there. The site overrides both `Header` and `MobileMenuFooter` in `website/astro.config.mjs` (lines 145-146), and `website/src/components/MobileMenuFooter.astro` is the phone-side counterpart that re-renders the version badge, social icons, theme and language selects. The version link now sits in `.title-wrapper` next to `SiteTitle` (moved by commit bdc77a65) so it shows on every width, but any control added to the right-group must still be mirrored into `MobileMenuFooter.astro` or it will silently disappear on mobile.
