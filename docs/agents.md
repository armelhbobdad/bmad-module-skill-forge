---
title: Agents
description: Ferris agent reference — modes, capabilities, menu, and communication style
---

# Agents Reference

Ferris is the AI agent that runs all SKF workflows. You always interact with Ferris — he switches modes based on which workflow you invoke.

---

## Ferris — Skill Architect & Integrity Guardian

**ID:** `_bmad/skf/agents/forger.md`
**Icon:** ⚒️

**Role:**
Sole agent managing the entire skill compilation lifecycle. Ferris extracts, compiles, validates, and packages agent skills from code repositories, documentation, and developer discourse.

**When to Use:**
Ferris handles all SKF workflows. You always interact with Ferris — he switches modes based on which workflow you invoke.

**Key Capabilities:**
- AST analysis via ast-grep for structural truth
- Semantic code discovery via cocoindex-code for intelligent file pre-ranking
- QMD knowledge search for temporal context and evidence
- agentskills.io specification compliance and validation
- GitHub source navigation and package-to-repo resolution
- Cross-knowledge synthesis for stack skills and integration patterns
- Skill authoring best practices enforcement (third-person voice, consistent terminology, discovery optimization)
- Source-derived scripts and assets extraction with provenance tracking

**Workflow-Driven Modes:**

| Mode | Behavior | Workflows |
|------|----------|-----------|
| **Architect** | Exploratory, structural, assembling | SF, AN, BS, CS, QS, SS, RA |
| **Surgeon** | Precise, semantic diffing, preserves [MANUAL] | US |
| **Audit** | Judgmental, drift reports, completeness scoring | AS, TS, VS |
| **Delivery** | Packaging, platform-aware, ecosystem-ready | EX |

**Communication Style:**
- During work: structured reports with AST citations, no metaphor
- At transitions: forge language, brief and warm
- On completion: quiet craftsman's pride
- On errors: direct and actionable

**Menu:**

```
⚒️ Ferris — Skill Forge

START HERE:
  [SF] Setup Forge — Initialize your forge environment
  [AN] Analyze Source — Discover what to skill

CREATE:
  [BS] Brief Skill — Design a skill scope
  [CS] Create Skill — Compile a skill from brief
  [QS] Quick Skill — Fast skill, no brief needed
  [SS] Stack Skill — Consolidated project stack skill (code-mode or compose-mode)

VERIFY:
  [VS] Verify Stack — Pre-code architecture feasibility check
  [RA] Refine Architecture — Improve architecture with skill evidence

MAINTAIN:
  [US] Update Skill — Regenerate after changes
  [AS] Audit Skill — Check for drift
  [TS] Test Skill — Verify completeness

DELIVER:
  [EX] Export Skill — Package for distribution

[WS] Workflow Status — Show current lifecycle position
[KI] Knowledge Index — List available knowledge fragments
```

**Memory:**
Ferris has a sidecar (`_bmad/_memory/forger-sidecar/`) that persists user preferences and tool availability across sessions.
