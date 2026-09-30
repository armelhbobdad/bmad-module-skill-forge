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

`skf-rebuild-managed-sections.py` writes this section for export-skill, drop-skill and rename-skill. Its `assemble` action builds the body between the markers, and its `insert` and `replace` actions write both markers and the `updated:` date around that body, so the three skills write the same bytes for the same manifest and snippets.

## IDE → Context File Mapping (config.yaml `ides` list)

The installer writes IDE identifiers to `config.yaml` under the `ides` key. The helper's `resolve-targets` action maps each one to its context file and skill root from `shared/data/ide-context-files.json`, the one mapping export-skill, drop-skill and rename-skill read. The tables below show that file for readers, and a test keeps them equal to it.

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

`resolve-targets` returns one target per context file, with the warnings and notes to show: IDEs that share a context file take the first configured IDE's skill root, and an absent, empty or unknown IDE resolves to AGENTS.md with `.agents/skills/`. To add an IDE, add it to the shared mapping; no workflow setting changes the mapping.

**`snippet_skill_root_override` (optional):** Authoring repos where all skills live under one shared on-disk directory (e.g. `skills/`) that does not match any per-IDE skill root may set `snippet_skill_root_override: skills/` in `config.yaml`. When set:

- `export-skill/step 3` §2.7 uses the override as `{skill_root}` for snippet generation instead of the IDE-mapped value
- export-skill, drop-skill and rename-skill pass it to `assemble` as `--skill-root-override`, which makes it the `root:` prefix of every row it writes: a snippet whose prefix already matches passes through unchanged, and any other prefix (a per-IDE prefix on a snippet exported before the override was adopted, or a legacy `skills/` draft) is rewritten to it, so the section uniformly references the real on-disk location

Consuming projects (the common case) omit the field and keep the default IDE-mapping behavior. The override is a narrow escape hatch for repos that author skills into `{skills_output_folder}` and never duplicate them into `.claude/skills/`-style directories.

### Consumers

Workflows that resolve context files through `resolve-targets`: `export-skill/step 1` (the target context files), `drop-skill/step 1` (the confirmation's context-file count) and step 2, and `rename-skill/step 2` (the rebuild after a management operation).

## Four-Case Logic

`skf-rebuild-managed-sections.py <context-file> check` reports the case of each context file as `case`, and the case picks the write. Both writes take only the body between the markers, as `assemble` stages it:

- **Create** (no file): `insert`, which creates the file with the section.
- **Append** (a file with no `<!-- SKF:BEGIN` marker): `insert`, which adds the section at the end of the file.
- **Regenerate** (a file with a section): `replace`, which swaps the old section for the new one and writes both markers itself.
- **Malformed** (a `<!-- SKF:BEGIN` with no `<!-- SKF:END -->` closing it): HALT and leave the file untouched. `check` names the line; the user restores the end marker, or deletes the stray begin marker, and re-runs.

drop-skill and rename-skill rewrite only a section that exists: they leave a missing file, or one with no section, as it is (export-skill adds the section on its next run), and report a malformed file as failed while they rebuild the others.

## Regeneration: Full Index Rebuild

`skf-rebuild-managed-sections.py assemble` builds the body from the **exported skill set** only: the skills of `{skills_output_folder}/.export-manifest.json` whose active version is not deprecated, plus the skills an export names with `--include`. Its docstring lists the rules it applies (where it reads each snippet, the rows of skills the manifest does not know, the sort and the counts).

**Rationale:** create-skill and update-skill also write `context-snippet.md` as a build artifact, but only export-skill is the publishing gate (ADR-K). The `.export-manifest.json` file tracks which skills have passed through export-skill, preventing draft skills from leaking into the agent's passive context.

## Safety Rules

Only the bytes between the `<!-- SKF:BEGIN` and `<!-- SKF:END -->` markers are SKF's to rewrite. Everything above and below them is the user's own file (their CLAUDE.md, AGENTS.md or .cursorrules) and must survive byte-for-byte. Route every write through `skf-rebuild-managed-sections.py`: it writes atomically and reads the file back to check the markers and the bytes outside them, so no separate hand-check is needed. On a write failure, report and stop.
