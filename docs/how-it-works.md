---
title: How It Works
description: A plain-English walkthrough of Skill Forge compiling one skill from a real library, end to end.
---

Skill Forge reads your code, extracts what your AI agents actually need, and compiles it into instructions with citations. This page walks through what that looks like end-to-end. For the machinery behind it, see [Architecture](/docs/architecture.md). For what ships inside a skill, see [Skill Model](/docs/skill-model.md).

---

## A walkthrough: building a cognee skill

Your AI agent keeps hallucinating cognee API calls. You run one command:

```
@Ferris QS https://github.com/topoteretes/cognee
```

In under a minute, plus one preview for you to approve, you get a `SKILL.md` your agent can load. Its content comes from cognee's own source code and README. Here's what happens between those two moments.

### 1. Ferris picks a workflow

`QS` is a trigger, short for *Quick Skill*. Ferris is the single AI agent that runs every Skill Forge workflow. He reads the trigger, loads the Quick Skill workflow, and prepares the context he needs to do the job.

### 2. The workflow resolves your target

Ferris turns your input into a GitHub repository. A GitHub URL is used as given. A package name is looked up on every registry of npm, PyPI and crates.io (a language hint asks only that language's registry), with a web search as the last resort. When more than one registry answers, an interactive run lists every candidate and asks which project you mean, and a headless run keeps the first registry's pick (npm, then PyPI, then crates.io) and records an `also_found_in` warning in its result envelope. He then detects the main language from the repository's files, starting with its manifest (`pyproject.toml`, `package.json`, etc.). By default Quick Skill reads the repository's default branch. To pin a release, add it to the command (`@Ferris QS cognee@1.0.0`): Ferris checks that the matching git tag exists, stops if it doesn't, and reads everything from that tag.

Quick Skill has a step that checks for an official skill before it reads any code, but it skips that check until agentskills.io offers a registry API to ask, so Ferris goes straight on to extraction.

### 3. He extracts the API

He reads cognee's README, its manifest (`pyproject.toml` for a Python project) and its top-level entry file (the package's `__init__.py`). From these he takes the version, the dependencies and the list of public exports: each export's name, its kind (function, class and so on) and a short description. Usage examples come from the README. Quick Skill reads the source as plain text, without AST parsing (a structural parse of the code), and does the same job whatever tools you have installed. It does not pull out signatures, parameter types or return types. If the repository looks like something other than a library, such as a docs site or a curated link list, he asks before going on. If he finds no exports, the skill falls back to the README and is marked low confidence. Nothing is invented: every line comes from the source, the README or you.

### 4. You review the skill before it is written

Ferris assembles three files: `SKILL.md` (an overview, a description, the key exports and usage patterns), `context-snippet.md` and `metadata.json`. He shows you all three and waits. You can continue, edit the description, change the scope and extract again, or quit without writing anything. When you continue, he writes the files and checks them against the agentskills.io format (with `skill-check` when it is installed). Anything that check finds is reported as advice and does not stop the run.

Quick Skill output carries no per-line receipts. Its `metadata.json` counts every export as T1-low: read from the source, but not structurally verified. Line-level receipts come from the brief-driven path described below.

### 5. You get a skill package

Ferris writes a `SKILL.md` (the instructions your agent loads on demand) and a `context-snippet.md` (an index of about 80 to 120 tokens) next to it. With the default settings they land in `skills/cognee/<version>/cognee/`, and `skills/cognee/active` points at that version. The snippet is the always-on reminder: it tells your agent the skill exists and to read `SKILL.md` before writing cognee code instead of relying on training data. It isn't wired in automatically. When you run `export-skill` (`@Ferris EX`), the snippet goes into the context file of each IDE you set up (`CLAUDE.md`, `AGENTS.md`, or `.cursorrules`). Both halves are load-bearing; see the [Dual-Output Strategy](/docs/skill-model.md#dual-output-strategy) for why.

### 6. The audit trail stays on disk

Alongside the skill, Ferris leaves a `metadata.json` (the source repository, the version, the git tag when you pinned one, and the list and count of exports) and a record of the run (`quick-skill-result-<timestamp>.json`, plus a `quick-skill-result-latest.json` copy) that lists exactly which files were written. Commit these with the skill so any teammate (or any skeptic) can see what it was built from. To tie that record to an exact release, pin a version as shown in step 2 above.

That's the whole pipeline. One trigger in, one reviewed skill out, built from cognee's own source and README. Next, run `@Ferris TS` to score the skill, then `@Ferris EX` to export it.

Quick Skill is the fastest path, not the most thorough one. When you want every instruction tied to a file and a line, use the brief-driven [`create-skill`](/docs/workflows.md#create-skill-cs) path instead: describe the skill's scope with `@Ferris BS`, which writes a `skill-brief.yaml`, then compile it with `@Ferris CS`. That path records the exact commit it read, and with ast-grep installed each export an ast-grep rule matches carries a receipt like this one:

```python
await cognee.search(  # [AST:cognee/api/v1/search/search.py:L27]
    query_text="What does Cognee do?"
)
```

The `AST` tag means *ast-grep matched this definition in this exact file at this exact line.* An export ast-grep cannot match is read by eye and carries an `[SRC:...]` receipt instead, with a lower confidence label (T1-low), so you can tell which receipts the code's structure backs. The same run writes a `provenance-map.json` that lists every receipt and the tool that read it, and an `evidence-report.md` build log, so you can open the upstream file at the pinned commit and check it yourself.

---

## Next

- **[Architecture](/docs/architecture.md)**: how Ferris loads workflows, how sub-agents handle large extractions, the 7 tools and which one wins when they disagree, and where artifacts land on disk
- **[Skill Model](/docs/skill-model.md)**: what a skill contains, confidence tiers (T1, T1-low, T2, T3), capability tiers (Quick, Forge, Forge+, Deep), and the dual-output strategy
- **[Verifying a Skill](/docs/verifying-a-skill.md)**: the 60-second audit recipe and how completeness scoring works
- **[BMAD Synergy](/docs/bmad-synergy.md)**: how SKF fits alongside BMAD Method, TEA, BMB, and other modules
