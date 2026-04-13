# Session Context

## User Prompts

### Prompt 1

Base directory for this skill: /home/armel/Projects/OSS/bmad-module-skill-forge/.claude/skills/bmad-help

# BMad Help

## Purpose

Help the user understand where they are in their BMad workflow and what to do next. Answer BMad questions when asked.

## Desired Outcomes

When this skill completes, the user should:

1. **Know where they are** — which module and phase they're in, what's already been completed
2. **Know what to do next** — the next recommended and/or required step, with clear rea...

### Prompt 2

advanced elicitation

### Prompt 3

Base directory for this skill: /home/armel/Projects/OSS/bmad-module-skill-forge/.claude/skills/bmad-advanced-elicitation

# Advanced Elicitation

**Goal:** Push the LLM to reconsider, refine, and improve its recent output.

---

## CRITICAL LLM INSTRUCTIONS

- **MANDATORY:** Execute ALL steps in the flow section IN EXACT ORDER
- DO NOT skip steps or change the sequence
- HALT immediately when halt-conditions are met
- Each action within a step is a REQUIRED action to complete that step
- Sect...

### Prompt 4

1-5

### Prompt 5

y pick a

### Prompt 6

x

### Prompt 7

# Feature Development

You are helping a developer implement a new feature. Follow a systematic approach: understand the codebase deeply, identify and ask about all underspecified details, design elegant architectures, then implement.

## Core Principles

- **Ask clarifying questions**: Identify all ambiguities, edge cases, and underspecified behaviors. Ask specific, concrete questions rather than making assumptions. Wait for user answers before proceeding with implementation. Ask questions e...

### Prompt 8

update the @ROADMAP.md with what we did in @_bmad-output/brainstorming

### Prompt 9

commit

### Prompt 10

update the @ROADMAP.md with what we did in @_bmad-output/brainstorming

### Prompt 11

commit

