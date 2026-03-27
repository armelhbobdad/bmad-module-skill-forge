# Managed Section Format (ADR-J)

## Marker Format

```markdown
<!-- SKF:BEGIN updated:{YYYY-MM-DD} -->
[SKF Skills]|{n} skills|{m} stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|{skill-snippet-1}
|
|{skill-snippet-2}
<!-- SKF:END -->
```

## Platform Target Files

| Platform | Flag Value | Target File |
|----------|-----------|-------------|
| Claude | `claude` (default) | CLAUDE.md |
| Cursor | `cursor` | .cursorrules |
| Copilot | `copilot` | AGENTS.md |

## Four-Case Logic

### Case 1: Create (No File Exists)

Target file does not exist. Create new file with managed section only.

```markdown
<!-- SKF:BEGIN updated:{date} -->
{managed section content}
<!-- SKF:END -->
```

### Case 2: Append (File Exists, No Section)

Target file exists but contains no `<!-- SKF:BEGIN` marker. Append managed section at end of file.

1. Read existing file content
2. Append two blank lines
3. Append managed section with markers
4. Write file

### Case 3: Regenerate (Existing Section)

Target file contains `<!-- SKF:BEGIN` and `<!-- SKF:END -->` markers. Replace content between markers.

1. Read existing file content
2. Find `<!-- SKF:BEGIN` line (preserve everything before it)
3. Find `<!-- SKF:END -->` line (preserve everything after it)
4. Replace everything between markers (inclusive) with new managed section
5. Write file

### Case 4: Malformed Markers (Halt)

Target file contains `<!-- SKF:BEGIN` but no matching `<!-- SKF:END -->` marker. This indicates a corrupted managed section.

1. Halt workflow with error: "Malformed managed section — `<!-- SKF:BEGIN` found but no `<!-- SKF:END -->`. Fix the markers manually before re-running export."
2. Do not modify the file

## Regeneration: Full Index Rebuild

When regenerating (Case 3), rebuild the COMPLETE skill index:

1. Scan `{skills_output_folder}/*/context-snippet.md` for all exported skills
2. Count total skills and stack skills
3. Assemble all snippets into managed section
4. Sort alphabetically by skill name
5. Update the header line with correct counts

## Safety Rules

- NEVER modify content outside the `<!-- SKF:BEGIN/END -->` markers
- ALWAYS preserve existing file content above and below markers
- ALWAYS verify file was written correctly after write
- If write fails, report error — do not attempt partial writes
