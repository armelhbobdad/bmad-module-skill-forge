# agentskills.io Specification

## Principle

Skills produced by Skill Forge comply with the agentskills.io specification — a format designed for agent consumption through progressive disclosure. The format prioritizes discoverability at low token cost, deterministic procedural instructions, and just-in-time resource loading.

## Rationale

Agent skills are not documentation for humans. They are instructions consumed by AI agents that treat every statement as actionable truth. The agentskills.io format was designed around this constraint: minimal metadata for discovery, structured instructions for activation, and on-demand resources for execution.

Without format compliance:
- Skills are not portable across agent platforms
- Discovery requires loading full skill content, wasting context tokens
- Agents cannot distinguish skills from general documentation

With format compliance:
- Skills are discoverable from ~100 tokens of frontmatter metadata
- Full activation loads < 500 lines of structured instructions
- Resources load on demand, keeping context lean during execution

## Format Structure

### Required: SKILL.md

The minimum viable skill is a single `SKILL.md` file containing:

**Frontmatter** (YAML between `---` markers):
```yaml
---
name: library-name
description: >
  What the skill does and when to use it. Include specific keywords
  for agent discovery. Mention what NOT to use it for.
---
```

**Frontmatter constraints:**
- `name`: 1-64 characters, lowercase alphanumeric + hyphens, must match parent directory name
  - **Naming convention:** Prefer gerund form (verb + -ing) for clarity: `processing-pdfs`, `analyzing-spreadsheets`, `managing-databases`. Noun phrases (`pdf-processing`) and action-oriented forms (`process-pdfs`) are acceptable alternatives. Avoid vague names (`helper`, `utils`, `tools`).
- `description`: 1-1024 characters, trigger-optimized for agent matching
  - **MUST use third-person voice.** The description is injected into the system prompt; inconsistent point-of-view causes discovery problems. Write "Processes Excel files and generates reports" — never "I can help you process Excel files" or "You can use this to process Excel files."

**Body:** Free-form markdown — no structural restrictions, but Skill Forge follows a consistent section order (see skill-sections.md in create-skill/assets/).

### Optional: Supporting Directories

```
skill-name/
├── SKILL.md              # Instructions and API reference
├── scripts/              # Executable automation
├── references/           # Detailed reference material
└── assets/               # Templates, schemas, configs
```

All subdirectories are exactly one level deep. Files are loaded on demand when SKILL.md directs — never automatically.

**Version-aware storage:** Skill Forge stores skills in a version-nested layout: `{skill-name}/{version}/{skill-name}/`. The inner `{skill-name}/` directory is the agentskills.io-compliant package shown above. The outer `{skill-name}/` and `{version}/` directories are organizational wrappers managed by the forge — they are not part of the skill package structure. The "one level deep" subdirectory rule applies to the skill package root (the inner directory), not the forge's storage hierarchy. See [version-paths.md](version-paths.md) for full path resolution rules.

Scripts and assets extracted by Skill Forge inherit provenance from their source repository. Each file receives a `[SRC:{source_path}:L1]` citation (T1-low confidence) and a SHA-256 content hash for drift detection. Scripts must follow the quality principles in the Script Quality section below. Assets are static files loaded on demand — agents use them as directed by SKILL.md instructions.

## Progressive Disclosure Model

The format implements a three-phase loading model:

| Phase | What Loads | Token Cost | When |
| --- | --- | --- | --- |
| Discovery | `name` + `description` from frontmatter | ~50-100 tokens | Agent startup, all skills |
| Activation | Full `SKILL.md` body | < 5000 tokens (~500 lines guideline) | Task matches skill description |
| Execution | Files from `scripts/`, `references/`, `assets/` | Variable | SKILL.md directs agent to load |

## Pattern Examples

### Example 1: Trigger-Optimized Description

**Context:** Writing a skill description that agents can match to user tasks.

**Implementation:**
```yaml
description: >
  Extract and transform data from PostgreSQL databases using pg client.
  Use for database queries, schema inspection, connection management,
  and migration execution. NOT for: MongoDB, Redis, or other non-SQL stores.
  NOT for: ORM-level abstractions (use typeorm-skill or prisma-skill instead).
```

**Key Points:**
- Leads with what the skill does (positive triggers)
- Includes negative triggers to prevent false matches
- References alternative skills for excluded use cases
- Specific keywords: "PostgreSQL", "pg client", "schema inspection"

### Example 2: Just-in-Time Resource Loading

**Context:** A skill needs to reference a complex schema during execution.

**Implementation:**
```markdown
## Configuration

The library accepts a configuration object matching the schema in
`references/config-schema.md`. Load that file now to validate
the user's configuration against the expected structure.
```

**Key Points:**
- The directive is explicit: "Load that file now"
- Agents do not pre-load reference files — they follow the instruction when they reach it
- Relative paths use forward slashes, one level deep only

### Example 3: Procedural Instructions for Agents

**Context:** Writing skill instructions that agents execute deterministically.

**Implementation:**
```markdown
## Setup

1. Check if `pg` is installed: run `npm list pg` in the project directory.
2. If not installed, run `npm install pg`.
3. Locate the database configuration:
   - Check `src/config/database.ts` first
   - If not found, check environment variables: `DATABASE_URL`, `PG_HOST`
   - If neither exists, ask the user for connection details
4. Validate the connection by running the health check in `scripts/health-check.sql`.
```

**Key Points:**
- Step-by-step numbering with decision trees
- Third-person imperative voice ("Check if..." not "You should check...")
- Concrete file paths and commands, not vague guidance
- Fallback paths explicitly mapped

### Example 4: Skill Forge Compliance Checks

**Context:** The validate step in create-skill checks agentskills.io compliance.

**Implementation:** Validation covers:
1. Frontmatter present with required `name` and `description` fields
2. `name` matches parent directory name and formatting rules
3. `description` length within 1-1024 characters
4. SKILL.md body under 500 lines (warning, not failure)
5. All relative paths resolve to existing files
6. No deeply nested subdirectories (max one level)

**Key Points:**
- Compliance is checked during create-skill, not as a post-hoc audit
- Line count is a guideline — exceeding 500 lines produces a warning
- Path validation prevents broken references in the published skill

## MCP Tool References

If a skill references MCP (Model Context Protocol) tools, always use fully qualified names to avoid "tool not found" errors: `ServerName:tool_name` (e.g., `BigQuery:bigquery_schema`, `GitHub:create_issue`). Without the server prefix, agents may fail to locate the tool when multiple MCP servers are available.

## Script Quality

Skills that include executable scripts in `scripts/` must follow these principles:

- **Solve, don't punt.** Scripts handle errors explicitly rather than failing and leaving the agent to figure it out. Provide fallback behavior, descriptive error messages, and recovery paths.
- **No voodoo constants.** Every magic number or configuration value must be justified with a comment explaining why that value was chosen. If you don't know the right value, the agent won't either.
- **Descriptive error output.** Write error messages to stdout/stderr that enable agents to self-correct without user intervention (e.g., "Field 'signature_date' not found. Available fields: customer_name, order_total").

## Development Methodology

- **Evaluation-driven development.** Define 2-3 concrete use cases and realistic test prompts before building the skill. Build evaluations before writing extensive documentation — this ensures the skill solves real problems rather than documenting imagined ones.
- **Realistic test prompts.** Test with prompts the way real users actually talk — with typos, casual abbreviations, and incomplete context. A skill tested only with clean prompts will break in unexpected ways in production.
- **Iterative refinement.** Observe how agents navigate and use the skill. Watch for unexpected exploration paths, missed references, overreliance on certain sections, and ignored content. Iterate based on observed behavior, not assumptions.

## Anti-Patterns

- Writing skills as documentation (README-style) instead of procedural agent instructions
- Deeply nested directory structures — one level maximum from skill root
- Vague descriptions ("helps with databases") — descriptions must be specific and trigger-optimized
- Including redundant content that duplicates what the agent already knows (standard language features, basic CLI commands)
- Bundling large library code inside skills — skills reference existing tools, not replace them
- Time-sensitive instructions ("If before August 2025, use the old API") — use versioned sections instead
- Offering too many tool/library options without a clear default — provide one recommended approach with escape hatches for edge cases
- Inconsistent terminology — mixing synonyms ("API endpoint", "URL", "route") confuses agent execution

## Related Fragments

- [skill-lifecycle.md](skill-lifecycle.md) — where agentskills.io compliance fits in the pipeline
- [confidence-tiers.md](confidence-tiers.md) — how citations appear within the formatted output
- [zero-hallucination.md](zero-hallucination.md) — the integrity principle that shapes skill content
- [version-paths.md](version-paths.md) — version-aware storage layout and path resolution templates

_Source: synthesized from agentskills.io specification, what-are-skills.mdx, integrate-skills.mdx, and Best Practices for Creating Agent Skills_
