# Manual Section Integrity

## Principle

Sections marked with `[MANUAL]` delimiters contain developer-authored content that the forge never modifies, regenerates, or removes. The merge algorithm treats \[MANUAL\] blocks as inviolable during updates — they are preserved in place, and any conflict between generated content and manual content is escalated to the user.

## Rationale

Generated skills cover what can be extracted from source code, but developers often need to add context that no tool can infer: architectural rationale, migration guides, team conventions, known gotchas. The \[MANUAL\] marker system gives developers a safe zone for hand-written content that survives regeneration cycles.

Without \[MANUAL\] preservation:
- Developer-authored content is overwritten on every update-skill run
- Users stop adding valuable context because it disappears
- Skills become purely mechanical extractions with no human insight

With \[MANUAL\] preservation:
- Hand-written content persists across unlimited regeneration cycles
- Developers invest in skill quality knowing their work is protected
- Skills combine machine-extracted precision with human-authored context

## Marker Format

\[MANUAL\] sections use HTML comment delimiters:

```markdown
<!-- [MANUAL:section-name] -->

Developer-authored content here. This content is never modified
by the forge during updates or regeneration.

<!-- [/MANUAL:section-name] -->
```

**Rules:**
- `section-name` must be unique within the file
- Opening and closing markers must match exactly
- Multiple \[MANUAL\] blocks allowed per file
- Nested \[MANUAL\] blocks are forbidden — trigger an ERROR if detected
- Markers apply to any output file: `SKILL.md`, `references/*.md`, integration files

### [MANUAL] Subdirectories

User-authored scripts and assets are placed in `scripts/[MANUAL]/` and `assets/[MANUAL]/` subdirectories within the skill package. These follow the same preservation principle as markdown `<!-- [MANUAL] -->` markers:

- Files in `[MANUAL]/` subdirectories are preserved unconditionally during `update-skill`
- Source-derived scripts/assets (outside `[MANUAL]/`) are refreshed from source during updates
- Conflicts (user file has same name as source file outside `[MANUAL]/`) are flagged as HIGH severity

## Pattern Examples

### Example 1: Adding Manual Context to a Generated Skill

**Context:** A developer wants to add migration notes to an API function that the forge generated.

**Implementation:**
```markdown
## `migrateDatabase(config: MigrateConfig): Promise<void>`

Runs pending database migrations in sequence.

**Parameters:**
| Name | Type | Required | Default |
| --- | --- | --- | --- |
| config | `MigrateConfig` | yes | — |

[AST:src/migrate.ts:L15]

<!-- [MANUAL:migrate-notes] -->

### Migration Gotchas

- Always run `backupDatabase()` before migration in production
- Migrations are not reversible after v2.3.0 — the rollback API was removed
- If using connection pooling, set `pool.max = 1` during migration to avoid lock conflicts

<!-- [/MANUAL:migrate-notes] -->
```

**Key Points:**
- The \[MANUAL\] block sits naturally within the generated skill structure
- Content inside the markers is entirely developer-controlled
- The forge regenerates everything outside the markers; the block is re-inserted in place

### Example 2: Merge Algorithm During Update

**Context:** The update-skill workflow needs to regenerate a skill while preserving \[MANUAL\] blocks.

**Implementation:** The merge follows this sequence:
1. **Extract** all \[MANUAL\] blocks from the existing skill, recording their section-name and parent section context
2. **Map** each block to its parent section in the document structure
3. **Regenerate** the skill content from fresh source extraction
4. **Re-insert** \[MANUAL\] blocks into their original positions relative to parent sections
5. **Flag conflicts** if any arise (see conflict types below)

**Key Points:**
- \[MANUAL\] blocks are extracted before regeneration and re-inserted after
- Position is determined by parent section, not absolute line number
- The merge is deterministic — same inputs always produce same output

### Example 3: Conflict Resolution

**Context:** Regeneration produces content that conflicts with existing \[MANUAL\] blocks.

**Implementation:** Four conflict severity levels:

| Severity | Condition | Resolution |
| --- | --- | --- |
| HIGH | Regenerated content overlaps \[MANUAL\] position | Present both versions, user chooses |
| HIGH | Parent section deleted, \[MANUAL\] block orphaned | Flag orphaned block, user decides to keep or remove |
| MEDIUM | \[MANUAL\] references a deleted export | Flag stale reference for user review |
| LOW | New export generated adjacent to \[MANUAL\] block | Auto-resolve: place new content before the block |

**Key Points:**
- HIGH conflicts always require user input — never auto-resolved
- MEDIUM conflicts are flagged but do not block the update
- LOW conflicts are auto-resolved with a deterministic rule (new content before block)

### Example 4: Orphan Detection

**Context:** An export that contained a \[MANUAL\] block has been removed from source.

**Implementation:**
```
WARNING: Orphaned [MANUAL] block detected

  Section: [MANUAL:migrate-notes]
  Previous parent: ## `migrateDatabase(config: MigrateConfig): Promise<void>`
  Status: Parent export removed from source

  Options:
  1. Keep block in a "Legacy Notes" section at end of skill
  2. Remove block (content will be shown for copy before deletion)
  3. Relocate to a different section (specify target)
```

**Key Points:**
- Orphaned blocks are never silently deleted
- The user always sees the content and chooses its fate
- Option 1 preserves the content without cluttering the active skill sections

## Audit Interaction

The audit-skill workflow detects \[MANUAL\] section integrity issues:
- **Malformed markers**: Missing closing tag, mismatched names
- **Nested markers**: \[MANUAL\] inside \[MANUAL\] — always an error
- **Stale references**: \[MANUAL\] content mentioning exports that no longer exist
- **Orphaned blocks**: Parent section no longer in the skill

These findings appear in the drift report with appropriate severity classifications.

## Anti-Patterns

- Modifying content inside \[MANUAL\] markers during automated updates — always preserve exactly
- Silently removing orphaned \[MANUAL\] blocks — always escalate to user
- Nesting \[MANUAL\] blocks — one level only, nesting is an error
- Using \[MANUAL\] markers in provenance-map.json or metadata.json — markers are for markdown content files only

## Related Fragments

- [provenance-tracking.md](provenance-tracking.md) — how \[MANUAL\] sections interact with provenance (no source location, author: "manual")
- [zero-hallucination.md](zero-hallucination.md) — \[MANUAL\] sections are the designated space for human-authored claims
- [skill-lifecycle.md](skill-lifecycle.md) — \[MANUAL\] preservation is critical in the update and audit phases

_Source: consolidated from manual-section-rules.md, merge-conflict-rules.md, and update-skill steps_
