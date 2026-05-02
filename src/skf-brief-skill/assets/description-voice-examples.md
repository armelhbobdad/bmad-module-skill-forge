# Description Voice Examples

Loaded by step-01 §7b only. The five examples below show the *range* of acceptable voices for the `description` field — they vary in lead, structure, and trigger phrasing on purpose. The point is to anchor the LLM to "two facts must come through (what the skill is, when to use it); everything else is voice — do not template-stamp."

## Examples

> Render Markdown to HTML using the marked library. Use when the user pastes raw Markdown and wants formatted output, or asks how to convert MD files in a build pipeline.

> Stripe API client for Node.js — payment intents, subscriptions, customer portal, webhooks. Triggers on tasks involving Stripe-managed payments, subscription billing, or webhook event handling.

> Charts and visualizations powered by D3.js. Reach for this when the user asks to plot data, build interactive graphs, or wants bare D3 control instead of a React-charts abstraction.

> Lint Python code with Ruff. Use when the user wants to add or configure Ruff in a Python project, debug rule selectors, or understand why a specific check fired.

> Date and time arithmetic via Luxon — parsing, formatting, time zones, durations, intervals. Use when working with dates in ways that exceed `Date.toISOString()` but you don't want a full Moment.js footprint.

## Notes on Voice

Each example leads differently (verb / noun / "Charts and..." / verb / noun-phrase) and matches the trigger phrasing ("Use when...", "Triggers on...", "Reach for this when...") to the voice rather than copy-pasting a single template. Compose in that spirit using the gathered material — the target repo, the user's intent, the version if set, and any scope hints — but **do not template-stamp**.
