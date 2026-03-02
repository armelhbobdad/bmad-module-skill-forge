# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# SKF Knowledge Folder — Implementation Plan

## Context

The SKF module has 10 workflows with 19 operational `data/` files embedded in workflow step directories, but **no agent-level knowledge folder**. The TEA reference module demonstrates the pattern: a `knowledge/` folder with standalone reference documents that the agent consults just-in-time during workflow execution, indexed via a CSV file.

Knowledge files are **cross-cutting principles and patterns** th...

### Prompt 2

update the @README.md the same way we have @temp/bmad-method-test-architecture-enterprise/README.md

### Prompt 3

give me a commit message for everything ready to be committed.

### Prompt 4

run test from @package.json

### Prompt 5

yes

### Prompt 6

update the @package.json

### Prompt 7

commit everything with this message: feat(skf): add complete SKF module with agent, workflows, knowledge base, and docs

Add full Skill Foundry (SKF) module implementation:

- Introduce Ferris agent persona with progressive capability tiers:
  Quick, Forge, and Deep
- Implement sidecar state management and Just-in-Time (JiT) knowledge loading
- Add 10 end-to-end workflows covering full skill lifecycle:
  - setup-forge
  - analyze-source
  - brief-skill
  - create-skill
  - quick-skill
  - cre...

