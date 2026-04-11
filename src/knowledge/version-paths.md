# Version-Aware Paths

## Principle

Skills are stored in a version-nested directory structure that allows multiple versions to coexist. Each version directory contains a self-contained agentskills.io-compliant skill package. All workflows resolve skill paths through canonical templates defined here, ensuring consistency across the pipeline and compatibility with `skill.sh` / `npx skills` distribution tooling.

## Rationale

Without version-aware paths:
- Updating a skill for cognee v0.6.0 overwrites the v0.5.0 skill — users pinned to v0.5.0 lose their instructions
- Audit and provenance comparisons cannot span version boundaries
- Skills cannot be distributed to registries that serve multiple versions

With version-aware paths:
- Multiple versions coexist under `{skill-name}/` — no data loss on update
- Provenance, evidence, and test reports are preserved per-version
- The inner `{skill-name}/` directory is a standalone agentskills.io package, directly installable via `npx skills add`

## Path Templates

All workflows MUST use these templates when constructing paths. Never hardcode paths to skill artifacts.

### skills_output_folder (Deliverables)

| Template | Resolves To | Usage |
|----------|------------|-------|
| `{skill_package}` | `{skills_output_folder}/{skill-name}/{version}/{skill-name}/` | Skill package root — where SKILL.md, metadata.json, context-snippet.md, references/, scripts/, assets/ live |
| `{skill_group}` | `{skills_output_folder}/{skill-name}/` | Parent directory for all versions of a skill |
| `{active_skill}` | `{skills_output_folder}/{skill-name}/active/{skill-name}/` | Resolved via `active` symlink — stable path to the current version |

### forge_data_folder (Workspace Artifacts)

| Template | Resolves To | Usage |
|----------|------------|-------|
| `{forge_version}` | `{forge_data_folder}/{skill-name}/{version}/` | Version-specific workspace artifacts — provenance-map.json, evidence-report.md, extraction-rules.yaml, test-report |
| `{forge_group}` | `{forge_data_folder}/{skill-name}/` | Parent directory — contains skill-brief.yaml (version-independent) and version subdirectories |

### IDE Skill Root Paths (Unchanged — Flat)

Each IDE has its own skill root path derived from its `target_dir` in `platform-codes.yaml`. The snippet `root:` line uses this path. Examples:

| IDE | Root Path |
|-----|-----------|
| `claude-code` | `.claude/skills/{skill-name}/` |
| `cursor` | `.cursor/skills/{skill-name}/` |
| `github-copilot` | `.github/skills/{skill-name}/` |
| `windsurf` | `.windsurf/skills/{skill-name}/` |
| _(draft/legacy)_ | `skills/{skill-name}/` |

See `skf-export-skill/assets/managed-section-format.md` for the complete IDE → Context File Mapping table with all 23 IDE root paths.

IDE skill root paths are **not versioned**. The export workflow resolves the active version from the manifest and references its `{skill_package}` when building the managed section. The snippet `root:` always uses the flat IDE skill root path.

## Directory Structure

### skills_output_folder

```
{skills_output_folder}/
  .export-manifest.json
  {skill-name}/
    active -> {version}
    {version}/
      {skill-name}/
        SKILL.md
        metadata.json
        context-snippet.md
        references/
        scripts/
        assets/
    {older-version}/
      {skill-name}/
        ...
  {project}-stack/
    active -> {version}
    {version}/
      {project}-stack/
        SKILL.md
        metadata.json
        context-snippet.md
        references/
          integrations/
```

The inner `{skill-name}/` directory IS the agentskills.io-compliant skill package. The version directory is an organizational wrapper. The `name` field in SKILL.md frontmatter matches the inner directory name — spec compliance is preserved.

### forge_data_folder

```
{forge_data_folder}/
  {skill-name}/
    skill-brief.yaml
    {version}/
      provenance-map.json
      evidence-report.md
      extraction-rules.yaml
      test-report-{skill-name}.md
```

`skill-brief.yaml` stays at `{forge_group}` level — the brief is a workflow input that defines extraction scope, not a versioned output.

## Version Resolution

### Writing Workflows (CS, QS, SS, US)

When writing artifacts, resolve `{version}` from the skill brief's `version` field (CS, SS), the extraction inventory (QS), or the updated metadata (US). Then:

1. Create `{skill_group}` if it does not exist
2. Create `{skill_package}` (including all parent directories)
3. Write all deliverables to `{skill_package}`
4. Create `{forge_version}` if it does not exist
5. Write all workspace artifacts to `{forge_version}`
6. Create or update the `active` symlink at `{skill_group}/active` pointing to `{version}`

### Reading Workflows (EX, AS, TS, VS, RA)

When reading artifacts, resolve the skill path using the export manifest:

1. Read `{skills_output_folder}/.export-manifest.json`
2. Look up the skill name in `exports`
3. Read `active_version` to get the target version
4. Resolve to `{skill_package}` using the active version
5. If manifest does not contain the skill: check for `active` symlink at `{skill_group}/active`
6. If neither manifest nor symlink: fall back to flat-path resolution (migration — see below)

### Manifest-Driven Snippet Scanning (EX Step-04)

Replace the glob-based snippet scan (`{skills_output_folder}/*/context-snippet.md`) with manifest-driven resolution:

1. Read export manifest
2. For each skill in the exported skill set: resolve `active_version` to get `{skill_package}`
3. Read `{skill_package}/context-snippet.md`
4. Filter and assemble as before

## Export Manifest v2

The export manifest gains version awareness:

```json
{
  "schema_version": "2",
  "exports": {
    "skill-name": {
      "active_version": "0.6.0",
      "versions": {
        "0.5.0": {
          "ides": ["claude-code"],
          "last_exported": "2026-03-15",
          "status": "archived"
        },
        "0.6.0": {
          "ides": ["claude-code", "github-copilot"],
          "last_exported": "2026-04-04",
          "status": "active"
        }
      }
    }
  }
}
```

**Fields:**
- `schema_version`: `"2"` — enables v1-to-v2 migration detection
- `active_version`: The version whose `{skill_package}` supplies the context snippet for the managed section. Must match exactly one version with `status: "active"`
- `versions.{v}.status`: `"active"` (currently exported), `"archived"` (previously exported, retained on disk), `"deprecated"` (dropped via drop-skill workflow, excluded from all exports), `"draft"` (created but never exported)
- `versions.{v}.ides`: Array of IDE identifiers from `config.yaml.ides` whose context file this version was last exported to (e.g. `["claude-code", "cursor"]`). NOT context file names, NOT skill root paths — the canonical IDE identifier used by the installer. Pre-rename manifests used `platforms` for this field; `skf-manifest-ops.py` silently upgrades them on read
- `versions.{v}.last_exported`: ISO date of the last export

**Only one version per skill can have `status: "active"` at any time.**

## Skill Management Operations

Two workflows operate on the version-aware structure for skill lifecycle management:

### Rename (RS - Rename Skill)

Renames a skill across all versions. Because the agentskills.io spec requires `name` to match parent directory name, a rename is a coordinated move across:
1. Outer `{skill_group}` directory: `{skills_output_folder}/{old-name}/` → `{skills_output_folder}/{new-name}/`
2. Inner `{skill-name}/` directories inside each version: `{version}/{old-name}/` → `{version}/{new-name}/`
3. `SKILL.md` frontmatter `name:` field (in every version)
4. `metadata.json` `name` field (in every version)
5. `context-snippet.md` root paths and display name (in every version)
6. `provenance-map.json` `skill_name` field (in every version under `{forge_group}`)
7. `{forge_group}` directory: `{forge_data_folder}/{old-name}/` → `{forge_data_folder}/{new-name}/`
8. Export manifest: remove old key, add new key with same version data
9. Platform context files (CLAUDE.md, AGENTS.md, .cursorrules): rebuild managed sections

Rename is transactional — copy-verify-delete pattern. If any step fails, old skill remains intact. See `skf-rename-skill/`.

### Drop (DS - Drop Skill)

Drops a specific version or the entire skill with two modes:

**Soft drop (default):** Sets version status to `"deprecated"` in the export manifest. Files remain on disk. Export-skill excludes deprecated versions from all platform context files. Reversible by manually editing manifest back to `"active"`/`"archived"`.

**Hard drop (`--purge`):** Same as soft drop, plus deletes the version directory (`{skill_package}`) and forge data directory (`{forge_version}`). Irreversible.

**Active version guard:** Cannot drop the active version when other versions exist. The user must either switch active to another version first, or drop all versions at once.

**Skill-level drop:** Removes the entire `{skill_group}` from the manifest. If purge, also deletes `{skill_group}` and `{forge_group}` directories.

See `skf-drop-skill/`.

## Version Sanitization

Directory names use the semver version with `+{build}` metadata stripped:

| Source Version | Directory Name | Rule |
|---------------|---------------|------|
| `1.0.0` | `1.0.0` | Clean — no transformation |
| `0.5.0-beta.1` | `0.5.0-beta.1` | Pre-release preserved |
| `1.0.0-rc.2+build.456` | `1.0.0-rc.2` | Build metadata stripped per semver spec |
| `2.0.0+20260404` | `2.0.0` | Build metadata stripped |

Build metadata does not affect version precedence per the semver specification and is stripped to avoid filesystem issues with the `+` character.

## Migration: Flat to Versioned

When a reading workflow encounters a skill at the flat path (`{skills_output_folder}/{skill-name}/SKILL.md` exists directly — no version subdirectory), it auto-migrates:

1. Read `metadata.json` from the flat path to get the `version` field
2. Create the versioned directory: `{skill_group}/{version}/{skill-name}/`
3. Move all package files (SKILL.md, metadata.json, context-snippet.md, references/, scripts/, assets/) into the versioned location
4. Create the `active` symlink: `{skill_group}/active -> {version}`
5. If `{forge_data_folder}/{skill-name}/` contains provenance artifacts at the flat level (not in a version subdirectory):
   - Create `{forge_version}`
   - Move provenance-map.json, evidence-report.md, extraction-rules.yaml, test-report into `{forge_version}`
   - Leave skill-brief.yaml at `{forge_group}` (it is already version-independent)
6. If `.export-manifest.json` exists and lacks `schema_version`:
   - Migrate to v2 schema: wrap existing entries with `active_version` and `versions` structure
   - Set `schema_version: "2"`
7. Report migration to user: "Migrated {skill-name} from flat to versioned layout ({version})"

**Migration preserves all content** — [MANUAL] sections, provenance, evidence reports, and scripts/assets are moved, not re-generated.

## Anti-Patterns

- Hardcoding `{skills_output_folder}/{skill-name}/SKILL.md` without version resolution — always use `{skill_package}` template
- Storing `skill-brief.yaml` inside a version directory — the brief is version-independent
- Versioning platform root paths — platform paths stay flat, version lives in the forge workspace
- Using glob patterns to discover snippets across all versions — use the export manifest to resolve the active version
- Creating version directories with `+` in the name — strip build metadata

## Related Fragments

- [agentskills-spec.md](agentskills-spec.md) — the format that `{skill_package}` contents must comply with
- [skill-lifecycle.md](skill-lifecycle.md) — how versioned artifacts flow through the pipeline
- [provenance-tracking.md](provenance-tracking.md) — provenance is version-bound and stored per-version in `{forge_version}`
