---
created: "2026-04-19 16:51"
session: "4125f6a8-222c-4739-9ed7-b0612704757b"
source: claude-mem
source_table: observations
source_ids: [6298, 6300, 6277]
---

# Newbie-readable prose for SKF marketing and docs hooks

Public-facing SKF prose — announcement articles, the `docs/index.md` and `docs/why-skf.md` hooks, landing copy — must be understandable by a newbie as well as a skeptic. The user rejected a jargon-heavy article hook: "I am not really getting "The afternoon you'll recognise" section. Even newbie will be lost. Rework it". The accepted rework set the pattern: state the plain-English task before showing any code, translate jargon inline in parentheticals (`**kwargs`, embedding API, token spend), summarise parameter lists instead of enumerating them, and keep sentences short. No style guide in `docs/` or `CONTRIBUTING.md` records this (docs/why-skf.md has only a 'The skeptic' persona), so apply it when writing or reviewing any public copy.
