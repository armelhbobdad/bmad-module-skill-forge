---
created: "2026-03-21 18:38"
session: "f2ad790b-1d74-4c13-b83e-7656902ab042"
source: claude-mem
source_table: both
source_ids: [2026, 2027, 2033]
---

# Website UI changes checked in both themes

The Starlight site under `website/` (`npm run docs:dev` → <http://localhost:4321>) offers Dark/Light/Auto themes, and `website/src/styles/custom.css` styles most elements twice: a base (light) rule plus a `:root[data-theme='dark']` override. The Mermaid diagram lightbox was verified only in dark mode before being committed, and the user's correction was "you did not test it in light mode": the close button and hint text were unreadable on the light backdrop and needed light-mode colours plus separate `:root[data-theme='dark'] .mermaid-lightbox*` overrides (custom.css lightbox block, around lines 536-620). Any website UI change is visually checked in both light and dark mode before it is committed or reported done.
