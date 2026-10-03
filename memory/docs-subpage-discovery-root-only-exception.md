---
created: "2026-10-03 12:48"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Docs subpage discovery starts only from a root-like URL (accepted exception)

Create Skill's documentation fetch discovers subpages only from a page whose URL is root-like: no path segment or one, or a path ending in `/`, `/index` or `/index.html`. `skf-detect-docs.py page-metrics` computes `root_like` from the URL shape (`_root_like`) and both of its subpage triggers require it, so a link-index page at a deeper path such as `/sdk/python` is fetched as a content page and not crawled (`src/skf-create-skill/references/sub/fetch-docs.md`, the `discover_subpages` step). The rule is the maintainer's own: fetch-docs.md held it in prose ("Root page detection: apply only when the URL path ends in `/`, `/index`, `/index.html`, has no path component, or has 1 path segment. For deeper URL paths, skip this heuristic and keep the content as-is.") until 800e08c2 moved it into the script verbatim as the fix for #605 determinism-10, and `test/test-skf-detect-docs.py` (`test_a_deep_page_never_triggers`) pins it.

The maintainer accepted it on 2026-10-03 as a written exception for the step 5b quality gate: the BMad Builder finding that a deep link-index page never triggers subpage discovery (skf-create-skill determinism-2 in the 2026-10-03-0852-run2 run, verified real) is listed under `excluded_findings` with this note as its reason, not counted. A URL of two or more segments is the content page the brief author chose, and SKF does not crawl from it; to compile its subpages, list them in the brief's `doc_urls`.
