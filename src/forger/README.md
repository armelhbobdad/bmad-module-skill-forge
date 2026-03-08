# forger-sidecar

This folder stores persistent memory for the **Ferris** agent (Skill Architect & Integrity Guardian).

## Purpose

Cross-session state for the SKF module's skill compilation lifecycle.

## Files

- `preferences.yaml` — User preferences: language defaults, output format settings
- `forge-tier.yaml` — Tool availability (ast-grep, gh, QMD) and derived capability tier

## Runtime Access

After BMAD installation, this folder will be accessible at:
`{project-root}/_bmad/_memory/forger-sidecar/`
