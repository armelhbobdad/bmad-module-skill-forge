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

**Mermaid Diagram Handling:** Do NOT parse Mermaid diagram syntax (`graph`, `flowchart`, `sequenceDiagram`, etc.) for technology detection. Only use prose text (headings, paragraphs, lists, tables) for detection. If the architecture document appears to list technologies exclusively inside Mermaid diagrams, note this in the coverage results as a detection limitation and recommend the user add prose-based technology listings.

### Coverage Verdict

The coverage matrix renders two verdict tokens per referenced technology: **Covered** and **Missing**. Extra skills (skills present in the inventory but NOT referenced by the architecture document) are tracked in a separate informational subdivision — they are not coverage verdicts and do not appear in the primary `Technology → Skill Match → Verdict` column. See step 2 §4 for the Extra-skill subdivision output.

| Verdict     | Meaning                                                          |
|-------------|------------------------------------------------------------------|
| **Covered** | A generated skill exists in `skills/` for this technology        |
| **Missing** | Technology is referenced in architecture doc but no skill exists |

**Informational — Extra skills subdivision (not a verdict; rendered in a separate section per step 2 §4):**

| Label                                  | Meaning                                                                                                                          |
|----------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| **Extra (unreferenced)**               | Skill exists with a resolvable `source_repo` / `source_root`, but no architecture tech token matches it                          |
| **Orphan (source_repo unresolvable)**  | Skill's `source_repo` is empty, malformed, or its basename cannot be extracted — cross-reference against architecture impossible |

## Output Format

When presenting coverage results, use the following structure:

```
| Technology | Source Section | Skill Match | Verdict |
|------------|---------------|-------------|---------|
| {tech_name} | {section_heading} | {skill_name or '—'} | Covered / Missing |
```

Include a summary line: `Coverage: {covered_count}/{total_count} ({percentage}%)`
