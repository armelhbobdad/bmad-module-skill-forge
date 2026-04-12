# Session Context

## User Prompts

### Prompt 1

Base directory for this skill: /home/armel/Projects/OSS/bmad-module-skill-forge/.claude/skills/bmad-workflow-builder

# Workflow & Skill Builder

## Overview

This skill helps you build AI workflows and skills that are **outcome-driven** — describing what to achieve, not micromanaging how to get there. LLMs are powerful reasoners. Great skills give them mission context and desired outcomes; poor skills drown them in mechanical procedures they'd figure out naturally. Your job is to help users ...

### Prompt 2

What if 1k users executing the @src/shared/health-check.md workflow hit the same problem and create the same issue? We will end up with 1k similar issues. I propose, before someone submit and issue, we should check if similar open issue already exists, if yes, just add a comment on that same issue. Activate party mode and/or advanced elicitation more multiple perspectives

### Prompt 3

Base directory for this skill: /home/armel/Projects/OSS/bmad-module-skill-forge/.claude/skills/bmad-party-mode

Follow the instructions in ./workflow.md.


ARGUMENTS: Topic: health-check.md creates one GitHub issue per finding with no dedup. At scale (1k users, same bug), we get 1k duplicate issues. Proposal: before `gh issue create`, search for a similar open issue and comment on it instead of creating a new one. Debate viability, risks (false-positive dedup, comment spam, rate limits, priva...

### Prompt 4

do what is the best move of a long term, robust and stable approach

### Prompt 5

commit first

### Prompt 6

Next actions worth considering can it be applied now?

