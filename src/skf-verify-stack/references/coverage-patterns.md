# Coverage Patterns

## Purpose

Rules for detecting technology/library references in architecture and PRD documents, and matching them against generated skills.

---

## Technology Detection in Documents

### Direct Name Matching

Search the architecture document for exact mentions of:
1. Library names from generated skills (case-insensitive)
2. Common aliases (e.g., "React" also matches "ReactJS", "react.js")
3. Framework names that encompass libraries (e.g., "Tauri" encompasses the Tauri ecosystem)

### Section-Based Detection

Parse document section headers for technology groupings:
- `## Desktop App` → technologies listed under this section
- `## Backend Core` → technologies in backend layer
- `## AI Layer` → AI-related technologies

**Mermaid Diagram Handling:** Do not parse Mermaid diagram syntax (`graph`, `flowchart`, `sequenceDiagram`, etc.) for technology detection — use only prose text (headings, paragraphs, lists, tables). If the architecture document appears to list technologies exclusively inside Mermaid diagrams, note this in the coverage results as a detection limitation and recommend the user add prose-based technology listings.
