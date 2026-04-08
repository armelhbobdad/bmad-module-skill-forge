# SKF Test Suite

Test coverage for the SKF module: schema validation, installation components, knowledge base integrity, and workflow state consistency.

## Overview

- **Agent Schema Validation** (`test/schema/agent.js`) — Zod-based validator ensuring `*.agent.yaml` files conform to the BMAD agent spec
- **Installation Components** (`test/test-installation-components.js`) — Module config, agent structure, path references, and step-file chain validation for all 14 skills (including VS, RA, and compose-mode)
- **Knowledge Base** (`test/test-knowledge-base.js`) — Fragment count, cross-references, and index integrity for the 14-entry knowledge base
- **Workflow State** (`test/test-workflow-state.js`) — Frontmatter field consistency, state file patterns, and confidence tier labels across VS, RA, and compose-mode workflows
- **CLI Integration** (`test/test-cli-integration.js`) — End-to-end CLI command validation

## Quick Start

```bash
# Run all tests
npm test

# Run CLI integration tests
node test/test-cli-integration.js

# Validate actual agent files
npm run validate:schemas
```
