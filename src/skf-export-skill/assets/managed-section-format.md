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

## IDE → Context File Mapping (config.yaml `ides` list)

The installer writes IDE identifiers to `config.yaml` under the `ides` key. Any workflow that rebuilds context files from `config.yaml` MUST map each entry to its context file and skill root using this table — it is the **single source of truth**.

Each IDE has two independent properties:

- **Context File** — the file the IDE reads for passive skill context
- **Skill Root** — the directory where the installer places skill files (matches `target_dir` in `platform-codes.yaml`)

### Dedicated context file IDEs

| config.yaml IDE value | Context File | Skill Root         |
|-----------------------|--------------|--------------------|
| `claude-code`         | CLAUDE.md    | `.claude/skills/`  |
| `cursor`              | .cursorrules | `.cursor/skills/`  |

### AGENTS.md context file IDEs

All other IDEs use AGENTS.md as the context file, each with its own skill directory:

| config.yaml IDE value | Context File | Skill Root           |
|-----------------------|--------------|----------------------|
| `github-copilot`      | AGENTS.md    | `.github/skills/`    |
| `codex`               | AGENTS.md    | `.agents/skills/`    |
| `windsurf`            | AGENTS.md    | `.windsurf/skills/`  |
| `cline`               | AGENTS.md    | `.cline/skills/`     |
| `roo`                 | AGENTS.md    | `.roo/skills/`       |
| `auggie`              | AGENTS.md    | `.augment/skills/`   |
| `antigravity`         | AGENTS.md    | `.agent/skills/`     |
| `codebuddy`           | AGENTS.md    | `.codebuddy/skills/` |
| `crush`               | AGENTS.md    | `.crush/skills/`     |
| `gemini`              | AGENTS.md    | `.gemini/skills/`    |
| `iflow`               | AGENTS.md    | `.iflow/skills/`     |
| `junie`               | AGENTS.md    | `.junie/skills/`     |
| `kilo`                | AGENTS.md    | `.kilocode/skills/`  |
| `kiro`                | AGENTS.md    | `.kiro/skills/`      |
| `ona`                 | AGENTS.md    | `.ona/skills/`       |
| `opencode`            | AGENTS.md    | `.opencode/skills/`  |
| `pi`                  | AGENTS.md    | `.pi/skills/`        |
| `qoder`               | AGENTS.md    | `.qoder/skills/`     |
| `qwen`                | AGENTS.md    | `.qwen/skills/`      |
| `rovo-dev`            | AGENTS.md    | `.rovodev/skills/`   |
| `trae`                | AGENTS.md    | `.trae/skills/`      |
| `other`               | AGENTS.md    | `.agents/skills/`    |
| _(any unknown value)_ | AGENTS.md    | `.agents/skills/`    |

### Resolution rules

**Deduplication:** When multiple IDE entries map to the same context file, deduplicate so each context file is processed exactly once. Use the **first configured IDE's** skill root for that context file's snippet root paths. Report the deduplication to the user: "Multiple IDEs target AGENTS.md — using {first IDE}'s skill root (`{skill_root}`). Each IDE's skills are installed to its own directory."

**Missing `ides` key:** If the `ides` key is absent from `config.yaml`, treat it as an empty list. If the resulting set is empty (no recognized entries), fall back to AGENTS.md with `.agents/skills/` as the skill root.

**Unknown IDE values:** Warn: "Unknown IDE '{value}' in config.yaml — defaulting to AGENTS.md with `.agents/skills/`"

**`snippet_skill_root_override` (optional):** Authoring repos where all skills live under one shared on-disk directory (e.g. `skills/`) that does not match any per-IDE skill root may set `snippet_skill_root_override: skills/` in `config.yaml`. When set:

- `export-skill/step-03` §2.7 uses the override as `{skill_root}` for snippet generation instead of the IDE-mapped value
- `export-skill/step-04` §4d (and its equivalents in `drop-skill/step-02` and `rename-skill/step-02`) treat the override as the effective target prefix for the managed-section rebuild: snippets whose prefix already matches the override pass through unchanged, and any other prefix — including per-IDE prefixes carried by sibling snippets that were exported before the override was adopted, and legacy `skills/` drafts — is rewritten to the override so the rebuilt managed section uniformly references the real on-disk location

Consuming projects (the common case) omit the field and keep the default IDE-mapping behavior. The override is a narrow escape hatch for repos that author skills into `{skills_output_folder}` and never duplicate them into `.claude/skills/`-style directories.

### Consumers

This mapping is the single source of truth. Workflows that need it: `export-skill/step-01` (resolves `target_context_files` from config.yaml IDE list), `export-skill/step-04` (applies four-case logic and rewrites root paths when writing managed sections), `drop-skill/step-02` and `rename-skill/step-02` (rebuild context files after a management operation).

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

1. Read `{skills_output_folder}/.export-manifest.json` (v2 schema — see `knowledge/version-paths.md`) to determine which skills have been explicitly exported and their `active_version` (if no manifest exists, only the current export target qualifies)
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
