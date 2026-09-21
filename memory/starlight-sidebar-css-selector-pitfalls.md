---
created: "2026-04-17 22:52"
session: "32e9eb66-b5be-4352-bf0c-d38d8793dc64"
source: claude-mem
source_table: session_summaries
source_ids: [1852, 1855]
---

# Starlight sidebar and table CSS selector pitfalls

In the docs site (`website/`, Starlight 0.37) `.sidebar-content > ul > li` matches nothing: Starlight renders `.sidebar-content` (PageFrame.astro:14) -> `<sl-sidebar-state-persist>` (SidebarPersister.astro:34) -> `ul.top-level` (SidebarSublist.astro:16), so a child combinator never reaches the list, and `website/src/styles/custom.css:269-275` still carries that dead selector. Group-header styling must target descendants (`.sidebar-content summary .large`) and needs `!important` (custom.css:234) to beat the component-scoped `.large` rule in SidebarSublist.astro:80. An unscoped `tbody tr:last-child` rule once bled into every table on the site; the fix scopes it under a `.comparison-table` wrapper (custom.css:170-185, commit 42b2ed9c). Verify sidebar CSS against the rendered DOM (`npm run dev` in `website/`), not against the sidebar config in astro.config.mjs.
