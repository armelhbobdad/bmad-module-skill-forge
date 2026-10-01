# Coverage Patterns

## Purpose

Rules for finding the technologies, libraries and frameworks an architecture document references, and for matching each one to a generated skill. The coverage stage (`coverage.md`) applies them.

---

## Skills the Document Names

The shared mentions helper (`skf-comention-pairs.py mentions`) finds every skill the document names, so no stage scans the document for skill names by hand. It matches each skill's name and aliases case-insensitively at word boundaries and reads each occurrence as the longest term that matches there: when both `react` and `react-dom` are skills, the text `react-dom` names `react-dom` only. A skill's aliases are:

1. the repository and the folder it was built from (`source_repo_basename` and `source_root_basename` in the inventory), so the document's "Cognee" names a skill called `oms-cognee`;
2. every other name a persistent fact gives it. Add a fact such as "Our documents call the postgresql skill Postgres or PG." to the workflow's `persistent_facts` (`customize.toml` says where a team or personal override goes): coverage passes both names to the helper, so the document's "PG" covers the skill, and the integrations stage pairs it;
3. the document's own name for a skill the model matched under a common alias (below): coverage runs the helper a second time with that name added, so the integrations stage pairs that skill too.

## Other Technologies

The model finds the rest, the technologies whose name is no skill's name or alias, so a Missing technology still shows:

### Section-Based Detection

Parse document section headers for technology groupings:
- `## Desktop App` → technologies listed under this section
- `## Backend Core` → technologies in backend layer
- `## AI Layer` → AI-related technologies

### Common Aliases

A technology the model finds this way still matches a skill under a common alias of the skill's name: "ReactJS" or "react.js" for a `react` skill, "PostgreSQL" for a `postgres` skill, "React Query" for a `react-query` skill, a framework name for the skill of a library it encompasses (e.g., "Tauri" encompasses the Tauri ecosystem). The term, as the document writes it, then becomes one of that skill's aliases (item 3 above).

## Fenced Code

Coverage reads only the document's prose (headings, paragraphs, lists, tables). The mentions helper skips every fenced block, so a skill the document names only inside one is in its `fenced_only` list, not `mentioned`: a Mermaid diagram (`graph`, `flowchart`, `sequenceDiagram`, etc.), and also any other code fence, such as an install command. The model's own detection skips fenced code too. When a `fenced_only` skill ends up Extra, the coverage results name it as a detection limitation and recommend listing them in prose; the helper's `fenced_blocks[]` (an `info` string of `mermaid` marks a diagram) says whether a Mermaid diagram is the cause.
