---
created: "2026-03-21 18:24"
session: "f2ad790b-1d74-4c13-b83e-7656902ab042"
source: claude-mem
source_table: observations
source_ids: [2017, 2018, 2022, 2024, 2026, 2032, 2033]
---

# Mermaid click-to-expand lightbox on the website

Mermaid diagrams on the docs site (rendered by the `astro-mermaid` integration in `website/astro.config.mjs`) get a zero-dependency click-to-expand lightbox instead of pan/zoom: `website/public/js/mermaid-lightbox.js`, loaded by a deferred script tag in `astro.config.mjs`, delegates clicks on `pre.mermaid`, clones the rendered `svg` into a fullscreen overlay styled by the `.mermaid-lightbox*` rules in `website/src/styles/custom.css` (`#f5f5f5` backdrop in light mode, `#111` under `:root[data-theme='dark']`), and closes on backdrop click, the close button or Escape. Pan/zoom was rejected because astro-mermaid documents no zoom, pan or click option, Mermaid's default `securityLevel: 'strict'` disables click handlers, and real pan/zoom would need a library such as `svg-pan-zoom` plus a looser security level. The user chose this path: "commit the previous work first then implement the simplest high-value option (click-to-expand)". The script depends on the svg being in the light DOM under `pre.mermaid`; an astro-mermaid upgrade that changes that wrapper breaks it silently.
