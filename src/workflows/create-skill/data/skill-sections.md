# SKILL.md Section Structure

## agentskills.io Compliant Format

### Frontmatter (Required — agentskills.io Compliance)

```yaml
---
name: {skill-name}
description: >
  {Trigger-optimized description of what the skill does and when to use it.
  Include specific keywords for agent discovery.
  Mention what NOT to use it for if applicable.
  1-1024 characters.}
---
```

**Frontmatter rules (agentskills.io specification):**

- `name`: 1-64 characters, lowercase alphanumeric + hyphens only, must match parent directory name
- `description`: 1-1024 characters, trigger-optimized for agent matching
- Only 6 fields permitted: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`
- `version` and `author` belong in metadata.json, NOT in frontmatter

### Section Order

1. **Overview** — What this skill provides, source repo, version, tier used
2. **Quick Start** — Most common 3-5 functions with minimal examples
3. **API Reference** — Grouped by module/file, each function with:
   - Signature with types
   - Parameters table
   - Return type
   - Usage example (from source tests/docs if available)
   - Provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`
4. **Type Definitions** — Exported types, interfaces, enums
5. **Integration Patterns** — Co-import patterns detected by ast_bridge (Forge/Deep only)
6. **Manual Sections** — Seeded with `<!-- [MANUAL] -->` markers for update-skill

### Provenance Citation Format

| Tier | Format | Example |
|------|--------|---------|
| T1 (AST) | `[AST:{file}:L{line}]` | `[AST:src/auth/index.ts:L42]` |
| T1-low (Source) | `[SRC:{file}:L{line}]` | `[SRC:src/auth/index.ts:L42]` |
| T2 (QMD) | `[QMD:{collection}:{doc}]` | `[QMD:project:CHANGELOG.md]` |
| T3 (External) | `[EXT:{url}]` | `[EXT:docs.example.com/api]` |

### [MANUAL] Section Markers

Seed empty manual sections for future update-skill compatibility:

```markdown
<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->
```

Place after Quick Start and after API Reference sections.

---

## context-snippet.md Format

Compressed 2-line-per-skill format for CLAUDE.md managed section:

```markdown
{skill-name} -> skills/{skill-name}/
  exports: {comma-separated top 10 function names}
```

---

## metadata.json Structure

```json
{
  "name": "{skill-name}",
  "version": "{source-version}",
  "skill_type": "single",
  "source_authority": "{official|community|internal}",
  "source_repo": "{github-url}",
  "source_commit": "{commit-hash}",
  "confidence_tier": "{Quick|Forge|Deep}",
  "spec_version": "1.3",
  "generation_date": "{ISO-8601}",
  "exports": [],
  "tool_versions": {
    "ast_grep": "{version-or-null}",
    "qmd": "{version-or-null}",
    "skf": "1.0.0"
  },
  "stats": {
    "exports_documented": 0,
    "exports_total": 0,
    "coverage": 0.0,
    "confidence_t1": 0,
    "confidence_t2": 0,
    "confidence_t3": 0
  },
  "dependencies": [],
  "compatibility": "{semver-range}"
}
```

---

## references/ Directory Structure

One file per major function group or type:

```
references/
├── {function-group-a}.md    — Detailed reference with full examples
├── {function-group-b}.md    — Detailed reference with full examples
└── {type-name}.md           — Type definition details
```

Each reference file includes:
- Full function signatures
- Detailed parameter descriptions
- Return value details
- Complete usage examples
- Related functions cross-references
- Temporal annotations (Deep tier: T2-past, T2-future)

---

## provenance-map.json Structure

```json
{
  "skill_name": "{name}",
  "source_repo": "{url}",
  "source_commit": "{hash}",
  "generated_at": "{ISO-8601}",
  "entries": [
    {
      "claim": "getToken accepts userId and optional TokenOptions",
      "source_file": "src/auth/index.ts",
      "source_line": 42,
      "confidence": "T1",
      "extraction_method": "ast_bridge.scan_definitions",
      "ast_node_type": "export_function_declaration"
    }
  ]
}
```

---

## evidence-report.md Structure

```markdown
# Evidence Report: {skill-name}

**Generated:** {date}
**Forge Tier:** {tier}
**Source:** {repo} @ {commit}

## Tool Versions
- ast-grep: {version}
- QMD: {version}
- SKF: 1.0.0

## Extraction Summary
- Files scanned: {count}
- Exports found: {count}
- Confidence: T1={n}, T2={n}, T3={n}

## Validation Results
- Schema: {pass/fail}
- Frontmatter: {pass/fail}

## Warnings
- {any warnings from extraction or validation}
```
