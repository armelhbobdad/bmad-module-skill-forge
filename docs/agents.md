---
title: Agents
description: Ferris agent reference covering modes, capabilities, menu, and communication style
---

## Ferris: Skill Architect & Integrity Guardian

**ID:** `skf-forger`
**Icon:** ⚒️

**Role:**
The only agent in SKF. Manages the entire skill compilation lifecycle. Ferris extracts, compiles, validates, and packages agent skills from code repositories, documentation, and developer discourse.

**When to Use:**
Start Ferris with his skill command: `/skf-forger` in Claude Code, Cursor and most other IDEs, `$skf-forger` in Codex, or `/skill:skf-forger` in Pi. In an IDE with no skill command, such as GitHub Copilot, ask your assistant to talk to Ferris. The installer prints the right command for each IDE you picked, and these docs write a request to Ferris as `@Ferris <code>`. He is the front door to every SKF workflow: pick one from his menu, or name it in the same message (`@Ferris QS cognee`), and he switches to the mode that fits it. You can also run a workflow skill directly by name, such as `/skf-setup`, without opening Ferris first.

**Key Capabilities:**
- Code extraction with ast-grep, which reads source code as a syntax tree (AST) so each extracted function cites its real file and line (Forge tier and up)
- Semantic code search with cocoindex-code (ccc), which ranks the most relevant files before extraction starts (Forge+ tier, or Deep tier when ccc is installed)
- Knowledge search with QMD, a local search tool, over the source repo's issues, pull requests, changelogs and release notes, for history and evidence (Deep tier)
- Checks against the agentskills.io specification, the open format agent skills follow
- GitHub source navigation and package-to-repo resolution
- Cross-library synthesis for stack skills and integration patterns
- Skill authoring best practices enforcement (third-person voice, consistent terminology, discovery optimization)
- Source-derived scripts and assets extraction with provenance tracking
- **Pipeline orchestration:** chain several workflows in one command; each workflow's output feeds the next, and the chain stops when a step fails its quality check
- **Headless mode:** run without stopping for confirmations, taking the default answer at each one, for power users and batch runs (`--headless` or `-H`)

The first three depend on your capability tier, which Setup Forge sets from the tools you have installed. See [Capability Tiers](/docs/concepts.md#capability-tiers-quickforgeforgedeep).

**Workflow-Driven Modes:**

| Mode | Behavior | Workflows |
|------|----------|-----------|
| **Architect** | Exploratory, structural, assembling | SF, AN, BS, CS, QS, SS, RA |
| **Surgeon** | Precise; finds what changed in the source, regenerates only that, and keeps the sections you wrote by hand (marked `[MANUAL]`) | US |
| **Audit** | Judgmental, drift reports, completeness scoring | AS, TS, VS |
| **Delivery** | Packaging, platform-aware, ecosystem-ready | EX |
| **Management** | Safe renames (copy, check, then delete the old name) and drops, both of which refresh your platform context files (CLAUDE.md, AGENTS.md, .cursorrules), plus campaigns that build many skills across sessions | RS, DS, Campaign |

**Communication Style:**
- During work: structured reports with AST citations, no metaphor
- At transitions: forge language, brief and warm
- On completion: quiet craftsman's pride
- On errors: direct and actionable

**Menu:**

Ferris shows his menu as a numbered table and waits for your choice. Pick a row by its code (for example `QS`), its number, or a plain request such as "quick skill".

| # | Code | What it does | Skill |
|---|------|--------------|-------|
| 1 | SF | Set up the forge: detect your tools and set your capability tier | `skf-setup` |
| 2 | AN | Find what to turn into skills in a large repo, and write recommended skill briefs | `skf-analyze-source` |
| 3 | BS | Design a skill's scope through guided questions | `skf-brief-skill` |
| 4 | CS | Compile a skill from a brief (`--batch` compiles several briefs) | `skf-create-skill` |
| 5 | QS | Build a skill fast from a package name or GitHub URL, no brief needed | `skf-quick-skill` |
| 6 | SS | Build one skill for your project's stack that shows how its libraries connect | `skf-create-stack-skill` |
| 7 | US | Regenerate a skill after its source changes, keeping your hand-written `[MANUAL]` sections | `skf-update-skill` |
| 8 | AS | Check a skill for drift from the current source code | `skf-audit-skill` |
| 9 | VS | Before you write code, check that your chosen libraries can deliver your architecture and product requirements (PRD) | `skf-verify-stack` |
| 10 | RA | Improve your architecture document with verified skill data and the VS findings | `skf-refine-architecture` |
| 11 | TS | Test a skill for completeness, the quality gate before export | `skf-test-skill` |
| 12 | EX | Package a skill and add its context to CLAUDE.md, AGENTS.md or .cursorrules | `skf-export-skill` |
| 13 | RS | Rename a skill across all its versions, all or nothing | `skf-rename-skill` |
| 14 | DS | Drop a skill: deprecate it (soft) or purge it (hard) | `skf-drop-skill` |
| 15 | (none) | Run a campaign that builds many coordinated skills across sessions; start it with `@Ferris campaign` | `skf-campaign` |
| 16 | KI | List the knowledge fragments, short reference notes that workflows load when a step needs them | built into Ferris |
| 17 | WS | Show your current lifecycle position, active skill briefs and forge tier | built into Ferris |

On your first run, before Setup Forge has set a capability tier, Ferris points you to four places to start: **SF** (run this first), **QS** (the fastest trial: give it a GitHub URL or package name), **BS** (the guided path to a high-quality skill) and **KI**. If your project also has the BMAD Method installed, you can ask for the `bmad-help` skill at any time for advice on what to do next. A project with SKF alone does not have it. Say "dismiss" or "exit persona" to leave Ferris.

**Pipeline Aliases:**

Ferris can run several workflows in one command. Type their codes in order, such as `QS TS EX`, or use a named alias: `forge-auto`, `forge`, `forge-quick` or `maintain`. Each workflow's output feeds the next one, the chain stops when a step fails its quality check, and every step runs in headless mode because you already chose the whole sequence. Example: `@Ferris forge-quick cognee` chains Quick → Test → Export. [Workflows → Pipeline Aliases](/docs/workflows.md#pipeline-aliases) has the full alias table and what each alias needs as its target.

`campaign` is not a chaining alias. It is a separate workflow (`@Ferris campaign`) that runs its own pipeline for many skills, builds them in the order their dependencies need, and can resume where it stopped. See the [Campaign](/docs/campaign.md) page.

**Memory:**
Ferris keeps a memory folder, called the sidecar, at `_bmad/_memory/forger-sidecar/`, so he remembers your setup between sessions. It holds `forge-tier.yaml` (the tools Setup Forge found and your capability tier), `preferences.yaml` (your settings) and the result of your last pipeline run. If that pipeline stopped partway, Ferris offers to resume it the next time you open him. In `preferences.yaml`, set `headless_mode: true` to make headless the default, or `compact_greeting: true` to get a short greeting without the full menu table (ask for the menu when you want it). [Getting Started → Configuration](/docs/getting-started.md#configuration) lists more preferences.
