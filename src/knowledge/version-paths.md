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
      evidence-report-fallback.md
      extraction-snapshot.json
      .manual-inventory.json
      .test-skill.lock
      test-report-{skill-name}-{run_id}.md
      drift-report-{timestamp}.md
      {workflow}-result-{timestamp}.json
      {workflow}-result-latest.json
  _campaign/
  improvement-queue/
```

`skill-brief.yaml` stays at `{forge_group}` level — the brief is a workflow input that defines extraction scope, not a versioned output.

The brief's `.bak` copy and `.brief-draft.json` sit beside it, and a stack group also holds `create-stack-skill-result-latest.json`. Names holding `.skf-` (locks such as `.skf-update.lock`, and staging) and a stack's `*-tmp` staging folders are SKF's too; while a rename runs, its lock is `{forge_data_folder}/.skf-rename-{skill-name}.lock`. `_campaign/` and `improvement-queue/` are SKF's own folders, never a skill's. Older skills may still hold the provenance map, evidence report, extraction rules and test reports directly in `{skill-name}/` (the flat layout — see Migration).

## Version Resolution

### Writing Workflows (CS, QS, SS, US)

When writing artifacts, resolve `{version}` from the skill brief's `version` field (CS, SS), the extraction inventory (QS), or the updated metadata (US). Then:

0. **Ownership check (CS, QS, SS).** Before creating anything, run `uv run skf-skill-inventory.py {skills_output_folder} --skill {skill-name} --write-check --write-version {version} --forge-data-folder {forge_data_folder}` and continue only when `write_check.verdict` is `"ok"`; otherwise stop with that verdict as the halt reason (`not-skf-output` or `flat-layout`). Without the helper, write only when nothing exists at `{skill_group}`. See Ownership below.
1. Create `{skill_group}` if it does not exist
2. Create `{skill_package}` (including all parent directories)
3. Write all deliverables to `{skill_package}`
4. Create `{forge_version}` if it does not exist
5. Write all workspace artifacts to `{forge_version}`
6. Create or update the `active` symlink at `{skill_group}/active` pointing to `{version}`

### Reading Workflows (EX, AS, TS)

When reading artifacts, resolve the skill path using the export manifest:

1. Read `{skills_output_folder}/.export-manifest.json`
2. Look up the skill name in `exports`
3. Read `active_version` to get the target version
4. **Manifest-lag guard.** If the `active` symlink at `{skill_group}/active` resolves to a *different* version than the manifest's `active_version`, prefer the **symlink target** and emit an Info note. The manifest `active_version` only advances when `export-skill` runs, but the `active` symlink is flipped forward by every writing workflow (CS/QS/SS/US) the instant it commits a new version. So in the canonical SS→TS→EX order the manifest lags the just-forged version in the window between forge and export — a manifest-first read would otherwise resolve the *previously exported* version. Preferring the symlink target closes this gap (and, for `export-skill`, makes that export publish the forged version and reconcile the manifest). This guard never overrides legitimate state: `drop-skill` — the only workflow that switches the active version — repoints the symlink to the manifest's `active_version` (it never leaves them diverged), and no workflow flips the symlink *backward*, so the only divergence that can occur is exactly this forge→export lag.
5. Resolve to `{skill_package}` using the chosen version — the symlink target when it diverges per step 4, otherwise `active_version`
6. If manifest does not contain the skill: check for `active` symlink at `{skill_group}/active`
7. If neither manifest nor symlink: fall back to flat-path resolution, only behind the ownership gate (see Ownership and Migration below)

**Stack rosters (VS, RA, SS compose-mode)** read through `skf-enumerate-stack-skills.py` instead: for each skill folder it takes the version the `active` link names, else the highest version, else a flat root `SKILL.md` — only a package whose `metadata.json` carries an SKF marker counts (see Ownership) — and it never reads the export manifest.

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

## Ownership

The skills folder can hold skills SKF did not generate, such as a BMad module's own skills or skills installed from elsewhere. Before a workflow writes a new version into, moves or deletes a skill's folders, it asks `skf-skill-inventory.py` whether SKF generated them; it never decides by hand.

**Marker rules.** Only a `metadata.json` that carries an SKF marker proves that SKF generated a skill. Any one of these is a marker:

1. `generated_by` is `quick-skill`, `create-skill` or `create-stack-skill`
2. `tool_versions` is an object with an `skf` key
3. `skill_type` is `single`, `individual` or `stack`, together with `forge_tier` or `confidence_tier`

Every SKF writer has written at least one of them since the first release. The marker counts at the group root (flat layout) or at `{skill_group}/{version}/{skill-name}/metadata.json` (versioned layout). The versioned layout, an `active` link, a manifest key or a result file do not count on their own. Setup's ccc exclusions use the same rule, so ccc leaves out exactly the skill folders the workflows treat as SKF output.

**Verdicts.** The inventory adds these fields to each skill:

| Field | Meaning |
|---|---|
| `ownership` | `"skf"`: SKF evidence and nothing else in the folder or its marked version folders. `"mixed"`: SKF evidence plus entries SKF did not generate. `"foreign"`: no SKF evidence, or the folder is a link |
| `skf_skill` | A marked version, or a flat skill with a marked root `metadata.json` |
| `flat_skf` | A root `SKILL.md` beside a marked root `metadata.json` |
| `foreign_entries` | The entries SKF did not generate; directories end in `/`, a link is listed by its bare name, and an entry inside a marked version folder is listed as `{version}/<entry>` |

SKF evidence is a marked version, a marked root `metadata.json`, the `_batch` folder, or `.skf-` in the folder name. A version folder that is a link, or that holds its package through a link, is never SKF output: SKF only creates the `active` link. A marked version folder holds only the `{skill-name}/` package and `.skf-` staging names; anything else in it is an entry SKF did not generate. The top-level `not_skf_output` names the folders that hold a skill SKF did not generate. `not_skf_output` never lists `_batch` or a `.skf-` name.

A folder that holds no file (only neutral clutter, `.skf-` names or empty folders), which is what an interrupted run leaves before it writes `metadata.json`, is never an entry SKF did not generate.

**Forge folders.** With `--forge-data-folder`, the inventory also classifies `{forge_data_folder}/{skill-name}` for each skill it scans, in the top-level `forge_groups[]` (`name`, `path`, `ownership`, `foreign_entries`, `errors`). The forge folder has no marker file, so SKF evidence there is its own files: a brief (`skill-brief.yaml*`, `.brief-draft.json`) or a `*-result*.json` directly in the folder, or a provenance map, evidence report, extraction rules or `*-result*.json` file in a folder directly inside it; a linked folder never holds any. The other names SKF writes (the forge tree above) count only beside that evidence. Setup's ccc exclusions use the same evidence rule for the forge folder.

| `ownership` | Meaning |
|---|---|
| `"absent"` | Nothing at the path |
| `"skf"` | SKF evidence and nothing else |
| `"mixed"` | SKF evidence plus entries SKF did not write, in `foreign_entries` (a folder SKF wrote nothing in as `{version}/`, an entry inside a marked one as `{version}/<entry>`) |
| `"empty"` | No evidence and nothing SKF did not write: an empty folder, or only locks and staging |
| `"foreign"` | Entries SKF did not write and no evidence, or the path is a link, is not a folder, or SKF cannot list it (`errors` says which) |
| `"reserved"` | `improvement-queue` or `_campaign`: SKF's own folder, never a skill's |

When both settings name one folder, the result has `same_folder: true` and an empty `forge_groups`: each skill folder is classified once, and an entry either rule accepts is SKF output, as setup's ccc exclusions do; only the skill's own `{version}/{skill-name}/` package still needs its SKF marker.

**How workflows use it:**

- US, AS, TS and EX migrate a flat skill only when `flat_skf` is true; otherwise they stop with `not-skf-output` before anything moves (see Migration below).
- CS, QS and SS write a version only after `--write-check` returns `"ok"`: nothing is at the skill folder yet, it holds only what an interrupted run leaves, or SKF generated it and the target version folder is new or SKF's own. They stop with `not-skf-output` for a folder SKF did not generate (a link included) or a version folder SKF did not generate, and with `flat-layout` for an SKF skill still only in the flat layout. The name `improvement-queue` is refused.
- RS renames only an `"skf"` folder in the versioned layout; it refuses others with `not-skf-output` or `flat-layout`. It moves the forge folder only when it is `"skf"` or `"empty"`, refuses (`not-skf-output`) one that is `"mixed"`, or `"foreign"` with `errors` because it is a link, is not a folder, or cannot be listed, and leaves any other `"foreign"` or `"reserved"` one under the old name.
- DS offers a folder SKF did not generate only when the manifest lists it, and then only for deprecate. It purges a whole skill folder only when its `ownership` is `"skf"` (or nothing is on disk). Its forge folder is purged when `"skf"` or `"empty"`, refused when `"mixed"`, and left in place when `"foreign"` or `"reserved"`; a single-version purge applies the same test to `{version}/` in the forge folder.
- VS, RA and SS compose-mode read only the skills SKF generated: `skf-enumerate-stack-skills.py` applies the same marker rule, lists the other skill folders once in `not_skf_output`, and never counts them as warnings or pairs; a folder whose `metadata.json` it cannot read is named in one warning instead, because it cannot tell whether SKF generated it. TS's discovery catalog counts the folders that hold a skill.
- Without the inventory helper, none of them moves or deletes a folder, and a writer writes only into a skill folder that does not exist yet.

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
7. `{forge_group}` directory: `{forge_data_folder}/{old-name}/` → `{forge_data_folder}/{new-name}/`, only when SKF generated it (see Ownership; a forge folder SKF did not generate keeps the old name)
8. Export manifest: remove old key, add new key with same version data
9. Platform context files (CLAUDE.md, AGENTS.md, .cursorrules): rebuild managed sections

Rename is transactional — copy-verify-delete pattern. If any step fails, old skill remains intact. Because it moves the whole `{skill_group}`, rename refuses a folder SKF did not generate or one that also holds entries SKF did not generate (`not-skf-output`), and a skill still in the flat layout (`flat-layout`) — see Ownership. It also refuses a forge folder that holds entries SKF did not write, or that is a link, is not a folder, or cannot be listed. See `skf-rename-skill/`.

### Drop (DS - Drop Skill)

Drops a specific version or the entire skill with two modes:

**Soft drop (default):** Sets version status to `"deprecated"` in the export manifest. Files remain on disk. Export-skill excludes deprecated versions from all platform context files. Reversible by manually editing manifest back to `"active"`/`"archived"`.

**Hard drop (`--purge`):** Same as soft drop, plus deletes the version directory (`{skill_package}`) and forge data directory (`{forge_version}`, only when SKF generated it). Irreversible.

**Active version guard:** Cannot drop the active version when other versions exist. The user must either switch active to another version first, or drop all versions at once.

**Skill-level drop:** Removes the entire `{skill_group}` from the manifest. If purge, also deletes `{skill_group}` and `{forge_group}` directories (the forge one only when SKF generated it).

**Ownership guard:** A purge deletes only SKF output. A whole-skill purge needs `ownership` `"skf"` (or nothing on disk); a `"mixed"` folder allows only a single-version purge of a marked version that is not a link and holds nothing SKF did not generate, and a `"foreign"` folder no purge at all (`not-skf-output`). A folder SKF did not generate is offered only when the manifest lists it, and then only for deprecate. The forge folder follows the same test: a whole-skill purge is refused when it is `"mixed"` and leaves it in place when SKF did not generate it; a single-version purge leaves a forge `{version}/` SKF did not generate in place and refuses one that holds entries SKF did not write.

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

When US, AS, TS or EX encounters a skill at the flat path (`{skills_output_folder}/{skill-name}/SKILL.md` exists directly — no version subdirectory), it auto-migrates:

0. **Ownership gate.** Run `uv run skf-skill-inventory.py {skills_output_folder} --skill {skill-name}` and migrate only when `skills[0].flat_skf` is true: the root `metadata.json` carries an SKF marker (`generated_by`, `tool_versions.skf`, or `skill_type` with `forge_tier` or `confidence_tier` — see Ownership). Otherwise, or when the helper is missing, stop with `not-skf-output` before anything moves. The message says a shared skills folder is supported and SKF leaves the skills it did not generate alone, so the user manages that skill; it points to `skills_output_folder` in `{project-root}/_bmad/skf/config.yaml` only for a folder that holds a module's own source. Read-only modes never migrate. Export-skill `--dry-run` reads the flat package in place. Update-skill `--dry-run` and `--detect-only` stop instead (`blocked`, phase `init:read-only-flat-layout`), because its later steps need the versioned forge workspace: run US, AS, TS or EX once without a read-only flag to migrate, then re-run.
1. Read `metadata.json` from the flat path to get the `version` field. If it has none, use `1.0.0`. Either way, name the directory by the Version Sanitization rules above
2. Create the versioned directory: `{skill_group}/{version}/{skill-name}/`
3. Move the package files (SKILL.md, metadata.json, context-snippet.md, references/, scripts/, assets/) into the versioned location. Any other entry in the folder stays where it is
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
- Writing into, migrating, renaming or purging a skill folder without the ownership check — a folder in `{skills_output_folder}` is SKF output only when a `metadata.json` in it carries an SKF marker, and a folder in `{forge_data_folder}` only when it holds SKF's brief, a result file, or a version folder with a provenance map, evidence report or extraction rules file

## Related Fragments

- [agentskills-spec.md](agentskills-spec.md) — the format that `{skill_package}` contents must comply with
- [skill-lifecycle.md](skill-lifecycle.md) — how versioned artifacts flow through the pipeline
- [provenance-tracking.md](provenance-tracking.md) — provenance is version-bound and stored per-version in `{forge_version}`
