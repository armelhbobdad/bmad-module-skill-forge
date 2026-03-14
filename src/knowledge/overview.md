# SKF Knowledge Overview

## Principle

Agent-level knowledge files capture cross-cutting principles and patterns that Ferris applies across multiple workflows. They are distinct from workflow `data/` files, which contain step-specific operational artifacts. Knowledge is loaded just-in-time when a workflow step directs — never preloaded into context.

## Rationale

The SKF module has 10 workflows containing 19 operational `data/` files embedded in step directories. These data files define schemas, templates, scoring formulas, and extraction rules tightly coupled to individual steps. But several principles — zero hallucination, confidence tiers, provenance — cut across multiple workflows and need a single authoritative source rather than fragmented repetition.

Without a knowledge folder:
- Cross-cutting principles get duplicated across workflow steps
- Updates to foundational rules require changes in multiple locations
- Ferris has no centralized reference for judgment calls that span workflows

With knowledge files:
- Each principle has one canonical definition
- Workflow steps reference knowledge files instead of re-stating rules
- Ferris loads only the knowledge relevant to the current task

## Knowledge Map

| File                                                       | Purpose                                                           | Key Workflows                      |
|------------------------------------------------------------|-------------------------------------------------------------------|------------------------------------|
| [zero-hallucination.md](zero-hallucination.md)             | Every claim traces to source; uncitable content excluded          | AN, BS, CS, QS, SS, US, AS, TS     |
| [confidence-tiers.md](confidence-tiers.md)                 | T1/T1-low/T2/T3 trust model and citation formats                  | AN, BS, CS, QS, SS, US, AS, TS, EX |
| [progressive-capability.md](progressive-capability.md)     | Quick/Forge/Deep tier philosophy and behavior adaptation          | All 10                             |
| [agentskills-spec.md](agentskills-spec.md)                 | agentskills.io output format principles and compliance            | CS, QS, SS, US, TS, EX             |
| [skill-lifecycle.md](skill-lifecycle.md)                   | End-to-end pipeline, artifact flow, workflow selection            | All 10                             |
| [provenance-tracking.md](provenance-tracking.md)           | Provenance-map.json, evidence reports, claim traceability         | CS, QS, SS, US, AS, TS             |
| [manual-section-integrity.md](manual-section-integrity.md) | \[MANUAL\] marker preservation and merge algorithm                | CS, US, AS, TS, EX                 |
| [qmd-registry.md](qmd-registry.md)                         | Progressive QMD collection registry and collection gate principle | SF, BS, CS, US, AS                 |

## JiT Loading Protocol

1. Ferris receives a task or workflow activation
2. Consult `skf-knowledge-index.csv` to identify relevant knowledge fragments by tags or description
3. Load only the files needed for the current task — never bulk-load all knowledge
4. Apply knowledge principles during workflow execution alongside step-specific `data/` files

## Knowledge vs. Data

| Aspect    | Knowledge Files (`knowledge/`)       | Data Files (`data/`)                    |
|-----------|--------------------------------------|-----------------------------------------|
| Scope     | Cross-cutting, multi-workflow        | Single workflow, single step            |
| Content   | Principles, patterns, judgment rules | Schemas, templates, scoring formulas    |
| Loading   | JiT via index lookup                 | JiT via step instruction                |
| Examples  | Zero hallucination, confidence tiers | skill-brief-schema.md, scoring-rules.md |
| Stability | Rarely changes                       | Changes with workflow evolution         |

## Related Fragments

- [confidence-tiers.md](confidence-tiers.md) — the trust model that underpins extraction and scoring
- [skill-lifecycle.md](skill-lifecycle.md) — the end-to-end pipeline connecting all workflows
- [progressive-capability.md](progressive-capability.md) — tier philosophy that affects every workflow

_Source: synthesized from module.yaml, README.md, and workflow README_
