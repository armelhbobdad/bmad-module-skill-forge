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
| Copilot | `copilot` (default) | AGENTS.md |
| Claude | `claude` | CLAUDE.md |
| Cursor | `cursor` | .cursorrules |

## IDE → Platform Mapping (config.yaml `ides` list)

The installer writes installer-specific IDE identifiers to `config.yaml` under the `ides` key (not platform values). Any workflow that rebuilds platform context files from `config.yaml` MUST map each entry to a platform before looking up its target file.

| config.yaml IDE value | Platform | Target File | Rationale |
|----------------------|----------|-------------|-----------|
| `claude-code` | `claude` | CLAUDE.md | native — reads `CLAUDE.md` and `.claude/skills/` |
| `cursor` | `cursor` | .cursorrules | native — reads `.cursorrules` and `.cursor/skills/` |
| `github-copilot` | `copilot` | AGENTS.md | native — reads `AGENTS.md` and `.agents/skills/` |
| `codex` | `copilot` | AGENTS.md | OpenAI Codex reads `AGENTS.md` (same convention as copilot) |
| `cline` | `copilot` | AGENTS.md | uses `AGENTS.md` as fallback context file |
| `roo` | `copilot` | AGENTS.md | uses `AGENTS.md` as fallback context file |
| `windsurf` | `copilot` | AGENTS.md | uses `AGENTS.md` as fallback context file |
| `other` | `copilot` | AGENTS.md | generic AGENTS.md fallback |
| _(any unknown value)_ | `copilot` | AGENTS.md | warn: "Unknown IDE '{value}' in config.yaml — defaulting to copilot" |

**Deduplication:** When multiple IDE entries map to the same platform (e.g. `codex` and `cline` both → `copilot`), deduplicate so each platform is processed exactly once. Report the deduplication to the user.

**Missing `ides` key:** If the `ides` key is absent from `config.yaml`, treat it as an empty list. If the resulting platform set is empty (no recognized entries), fall back to `["copilot"]`.

This mapping is the single source of truth. Workflows that need it: `export-skill/step-01` (resolves `target_platforms` for the export), `drop-skill/step-02` and `rename-skill/step-02` (rebuild platform context files after a management operation).

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

When regenerating (Case 3) or creating/appending (Cases 1-2), rebuild the skill index from the **exported skill set** only:

1. Read `{skills_output_folder}/.export-manifest.json` (v2 schema — see [knowledge/version-paths.md](../../../knowledge/version-paths.md)) to determine which skills have been explicitly exported and their `active_version` (if no manifest exists, only the current export target qualifies)
2. For each skill in the exported set, resolve the snippet at `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md` (i.e., `{skill_package}/context-snippet.md`). Do NOT use glob patterns across version directories — always resolve via manifest `active_version` or `active` symlink
3. Count total skills and stack skills (from filtered set only)
4. Assemble filtered snippets into managed section
5. Sort alphabetically by skill name
6. Update the header line with correct counts

**Rationale:** create-skill and update-skill also write `context-snippet.md` as a build artifact, but only export-skill is the publishing gate (ADR-K). The `.export-manifest.json` file tracks which skills have passed through export-skill, preventing draft skills from leaking into the agent's passive context.

## Safety Rules

- NEVER modify content outside the `<!-- SKF:BEGIN/END -->` markers
- ALWAYS preserve existing file content above and below markers
- ALWAYS verify file was written correctly after write
- If write fails, report error — do not attempt partial writes
