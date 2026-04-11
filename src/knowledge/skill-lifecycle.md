# Skill Lifecycle

## Principle

The 14 SKF workflows form an end-to-end pipeline from source discovery through verified export, with a pre-code architecture verification path and post-distribution management operations. Each workflow produces artifacts consumed by downstream workflows. Understanding the lifecycle enables Ferris to recommend the right workflow for a user's situation and to maintain artifact continuity across the pipeline.

## Rationale

Skills are not created in a single step — they move through discovery, design, compilation, verification, and distribution phases. Each phase has dedicated workflows with specific inputs and outputs. The lifecycle model prevents users from skipping critical steps and ensures artifacts flow cleanly between workflows.

Without lifecycle awareness:
- Users jump to create-skill without proper analysis or briefing
- Generated skills lack provenance because upstream artifacts were skipped
- Export packages reference stale or untested skills

With lifecycle awareness:
- Ferris recommends the appropriate entry point based on the user's context
- Artifact dependencies are explicit — each workflow declares its inputs
- The full pipeline produces verified, export-ready skills with complete provenance

## Pipeline Phases

| Phase | Workflows | Purpose | Artifacts Produced |
| --- | --- | --- | --- |
| Setup | SF (Setup Forge) | Detect environment and set capability tier | `forge-tier.yaml` |
| Discovery | AN (Analyze Source) | Scan project, identify skillable units | Analysis report, skill briefs |
| Design | BS (Brief Skill) | Interactive scope definition for one skill | `skill-brief.yaml` |
| Compilation | CS, QS, SS (Create/Quick/Stack) | Extract source and compile skill | `SKILL.md`, metadata, provenance, `scripts/`, `assets/` (when source contains them) — written to `{skill_package}` and `{forge_version}` (see [version-paths.md](version-paths.md)) |
| Architecture Verification | VS, RA (Verify Stack, Refine Architecture) | Pre-code feasibility check and architecture refinement | Feasibility report, refined architecture doc |
| Maintenance | US, AS (Update/Audit) | Detect drift and refresh skills | Updated `SKILL.md`, drift report |
| Verification | TS (Test Skill) | Quality gate — completeness scoring | Test report, pass/fail decision |
| Distribution | EX (Export Skill) | Package and inject into agent context | agentskills.io bundle, snippets |
| Management | RS, DS (Rename/Drop) | Rename or retire skills and versions | Renamed skill group, deprecated/purged versions |

## Typical Flows

### First-Time Setup (Brownfield Project)

```
SF → AN → CS (--batch) → TS → EX
```

1. **SF** detects tools, writes forge tier
2. **AN** scans the project, identifies skillable units, generates skill briefs
3. **CS** compiles skills from briefs (batch mode processes all briefs)
4. **TS** runs completeness verification on each skill
5. **EX** packages passing skills for distribution

### Single Skill (Full Quality)

```
SF → BS → CS → TS → EX
```

1. **SF** ensures environment is configured
2. **BS** guides the user through scope definition, produces a validated brief
3. **CS** compiles the skill with full provenance
4. **TS** verifies completeness
5. **EX** packages for distribution

### Single Skill (Fast)

```
SF → QS → EX
```

1. **SF** ensures environment is configured
2. **QS** resolves a package name or URL to source and compiles directly — no brief needed
3. **EX** packages for distribution (optional TS between QS and EX for quality assurance)

### Pre-Code Stack Verification

```
SF → CS×N (per library) → VS → RA → SS (compose) → TS → EX
```

1. **SF** ensures environment is configured
2. **CS** compiles individual skills for each library in the stack
3. **VS** cross-references skills against architecture and PRD — produces a feasibility report with verdicts
4. **RA** refines the architecture document using skill API evidence and VS findings
5. **SS** (compose-mode) synthesizes the stack skill from individual skills + refined architecture
6. **TS** verifies the composed stack skill
7. **EX** packages for distribution

### Maintenance

```
AS → US → TS → EX
```

1. **AS** detects drift between skill and current source
2. **US** re-extracts changed exports and merges, preserving \[MANUAL\] sections
3. **TS** re-verifies the updated skill
4. **EX** re-exports the updated package

### Management

```
RS or DS → EX
```

1. **RS** renames a skill across all versions (transactional copy-verify-delete), OR
2. **DS** drops a specific version (soft — deprecate, or hard — purge) or the entire skill
3. **EX** rebuilds platform context files (CLAUDE.md/AGENTS.md/.cursorrules) to reflect the management operation — deprecated versions are excluded, renamed skills appear under their new name

## Pattern Examples

### Example 1: Workflow Selection Decision

**Context:** A user asks Ferris to create a skill for a specific library.

**Implementation:** Ferris evaluates the situation:

| Condition | Recommended Flow |
| --- | --- |
| User knows exactly what to skill, has a brief | CS directly |
| User knows the library but needs scope guidance | BS → CS |
| User has a package name, wants fast results | QS |
| User wants to skill their entire project | AN → CS (batch) |
| User has an existing skill that may be outdated | AS → US |
| User wants to verify tech stack before building | CS×N → VS → RA → SS (compose) |

**Key Points:**
- SF is always prerequisite (but only needs to run once per project)
- Quick skill (QS) skips briefing — appropriate for well-known packages
- Analyze source (AN) is the brownfield entry point for large projects

### Example 2: Artifact Flow Between Workflows

**Context:** Tracking how artifacts flow through the pipeline.

**Implementation:**
```
SF → forge-tier.yaml
       ↓ (read by all subsequent workflows)
AN → analysis-report.md + skill-brief.yaml[]
       ↓ (briefs consumed by CS)
CS → {skill_package}/SKILL.md + metadata.json + {forge_version}/provenance-map.json + scripts/ + assets/ (when present) + evidence-report.md
       ↓ (skill consumed by TS — resolved via active version)
TS → {forge_version}/test-report.md (pass/fail gate)
       ↓ (passing skill consumed by EX — resolved via export manifest v2)
EX → agentskills.io bundle + context snippets (flat platform paths)

VS → feasibility-report-{project_name}.md (verdict + integration verdicts)
       ↓ (report consumed by RA)
RA → refined-architecture-{project_name}.md (gaps filled, issues flagged, improvements suggested)
       ↓ (refined doc consumed by SS compose-mode)
SS (compose) → SKILL.md (stack skill synthesized from individual skills + architecture)
```

**Key Points:**
- `forge-tier.yaml` is the universal dependency — all workflows read it
- Skill briefs are the handoff between discovery/design and compilation
- TS acts as a gate — failing skills do not proceed to EX
- VS/RA form a pre-code verification loop — rerun after architecture changes

### Example 3: Stack Skill vs. Individual Skills

**Context:** A user wants to document how multiple libraries work together in their project.

**Implementation:** Two approaches serve different needs:
- **Individual skills** (via CS or QS): One skill per library, each with its own provenance and lifecycle. Best for reusable skills that apply across projects.
- **Stack skill** (via SS): A single consolidated skill documenting how libraries connect. Detects co-import patterns and integration surfaces. Best for project-specific context.

**Key Points:**
- Stack skills and individual skills are complementary, not competing
- SS detects integration patterns (e.g., "express + passport always used together for auth routes")
- Individual skills track per-library provenance; stack skills track inter-library relationships

## Pipeline Invocation

Users can chain workflows by providing multiple codes to Ferris:

```
BS CS TS EX           — space-separated
forge                 — alias for BS CS TS EX
forge-quick           — alias for QS TS EX
onboard               — alias for AN CS TS EX
maintain              — alias for AS US TS EX
CS[cocoindex] TS[min:80] EX  — with arguments and circuit breakers
```

Pipelines automatically activate headless mode. The forger passes data between workflows using the artifact flow described above. Circuit breakers halt the pipeline when output quality falls below a threshold (e.g., TS score < 60 blocks EX). See `shared/references/pipeline-contracts.md` for the full specification.

## Integration Points

- **Setup Forge** must run before any other workflow — it establishes the tier
- **Analyze Source** and **Brief Skill** are alternative entry points to compilation
- **Test Skill** is optional but recommended — the quality gate before export
- **Audit Skill** and **Update Skill** form the maintenance loop
- **Verify Stack** and **Refine Architecture** form the pre-code verification path
- **Export Skill** is the terminal workflow — it produces the distributable artifact

## Related Fragments

- [progressive-capability.md](progressive-capability.md) — how the forge tier affects each pipeline phase
- [agentskills-spec.md](agentskills-spec.md) — the output format that export-skill packages
- [provenance-tracking.md](provenance-tracking.md) — how provenance flows through the pipeline
- [version-paths.md](version-paths.md) — version-aware storage layout, path templates, and migration rules

_Source: synthesized from all 14 SKILL.md files (including VS, RA, RS, DS) and module-help.csv_
