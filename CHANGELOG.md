# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - Unreleased

### Initial Release

Skill Forge (SKF) — an agent skill compiler that transforms code repositories, documentation, and developer discourse into [agentskills.io](https://agentskills.io)-compliant agent skills with AST-backed provenance.

### Highlights

- **1 agent** — Ferris (Skill Architect & Integrity Guardian) with 4 workflow-driven modes
- **12 workflows** — full lifecycle from source analysis to ecosystem-ready export, with pre-code architecture verification
- **Progressive capability model** — Quick (gh), Forge (+ast-grep), Forge+ (+ccc), Deep (+QMD)
- **Zero hallucination tolerance** — every instruction traces to source code with provenance citations
- **Dual-output strategy** — active skills (SKILL.md) + passive context (context-snippet.md) in ADR-L v2 format
- **CLI installer** — `npx bmad-module-skill-forge install` with IDE command generation for 7 IDEs
- **13 knowledge fragments** — curated cross-cutting principles loaded just-in-time by workflows

### Workflows

| Trigger | Name | Purpose |
|---------|------|---------|
| SF | Setup Forge | Initialize forge environment, detect tools, set tier |
| AN | Analyze Source | Discover what to skill in a large repo |
| BS | Brief Skill | Design a skill scope through guided discovery |
| CS | Create Skill | Compile a skill from brief with AST extraction |
| QS | Quick Skill | Fast skill from package name or GitHub URL |
| SS | Stack Skill | Consolidated project stack skill with integration patterns |
| US | Update Skill | Smart regeneration preserving manual sections |
| AS | Audit Skill | Drift detection between skill and current source |
| TS | Test Skill | Cognitive completeness verification |
| VS | Verify Stack | Pre-code stack feasibility verification against architecture |
| RA | Refine Architecture | Improve architecture doc using verified skill data |
| EX | Export Skill | Package for distribution, inject into CLAUDE.md |

### Confidence Tiers

- **T1** — AST-verified structural truth (Forge/Forge+/Deep)
- **T1-low** — Source reading without structural verification (Quick)
- **T2** — QMD-enriched temporal context (Deep)
- **T3** — External documentation, quarantined as untrusted

### IDE Support

Claude Code, Cursor, Cline, Codex, GitHub Copilot, Roo Code, Windsurf

### Links

- Documentation: <https://armelhbobdad.github.io/bmad-module-skill-forge>
- npm: <https://www.npmjs.com/package/bmad-module-skill-forge>
