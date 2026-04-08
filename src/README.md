# SKF Module Source

This directory contains the **Skill Forge (SKF)** BMAD module — the files that get installed into a BMAD project under `_bmad/skf/` when a user runs the installer.

For user-facing documentation (what SKF does, how to install it, how to use it), see the [repository README](../README.md) and the published docs at [armelhbobdad.github.io/bmad-module-skill-forge](https://armelhbobdad.github.io/bmad-module-skill-forge/).

## Layout

```
src/
├── skf-forger/               # Agent skill — Ferris persona
│   ├── SKILL.md              # Agent identity, principles, menu of triggers
│   └── bmad-skill-manifest.yaml
├── skf-setup/                # Setup skill (forge initialization)
│   ├── SKILL.md
│   └── ...
├── skf-{name}/               # 13 workflow skills (one directory each)
│   ├── SKILL.md              # Skill entry point
│   ├── workflow.md           # Human-readable workflow description
│   ├── steps-c/              # Sequential step files
│   ├── references/           # Rules, patterns, protocols (decision-making)
│   ├── assets/               # Schemas, output formats
│   └── templates/            # Output skeletons (used by some skills)
├── knowledge/                # Cross-cutting knowledge fragments (JiT loaded)
│   └── skf-knowledge-index.csv
├── forger/                   # Sidecar seed files (preferences, forge tier)
├── shared/                   # Cross-workflow resources
├── module.yaml               # Module metadata (code, name, config vars)
└── module-help.csv           # Skill menu for bmad-help integration
```

**Workflow skills:** setup, analyze-source, brief-skill, create-skill, quick-skill, create-stack-skill, verify-stack, refine-architecture, update-skill, audit-skill, test-skill, export-skill, rename-skill, drop-skill.

## Components

- **Agent:** [Ferris](skf-forger/SKILL.md) — single-persona module operating in five modes (Architect / Surgeon / Audit / Delivery / Management)
- **Workflow skills:** 14 `skf-{name}/` directories, each containing a SKILL.md, workflow.md, steps, references, and assets
- **Knowledge fragments:** cross-cutting principles Ferris consults via `knowledge/skf-knowledge-index.csv`

## Editing this module

- Agent edits — `skf-forger/SKILL.md`; validate with `bmad:bmb:agents:agent-validate`
- Workflow edits — each workflow skill in `skf-{name}/`; validate with `bmad:bmb:workflows:workflow-validate`
- Module-level edits — `module.yaml` and `module-help.csv`; validate with `bmad:bmb:modules:validate-module`

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the contribution workflow.
