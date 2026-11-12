---
created: "2026-11-09 11:03"
session: "77252030-8c80-4285-b88e-c15f43930eb7"
---

# Unproven live security-scan checks without a Snyk token

The maintainer has no Snyk key, and `SNYK_TOKEN` needs a Snyk Enterprise plan (docs/getting-started.md), so a "Done when" item that needs a real scan cannot be done here. An example is #892's runs of Quick Skill, Create Skill, Update Skill and Create Stack Skill through `src/shared/scripts/skf-security-scan.py` on a risky and a clean package. Asked on 2026-11-09 whether to set a token or leave #892 open, the maintainer answered "Set it unproven, I don't have a key". So land the code fix and mark the live check unproven in the PR and in a comment on the issue, as PR #1052 (its "Unproven" section) and #892's closing comment ("Unproven: ...") did. Do not ask for a token or block on one: prove what can be proven with the recorded snyk-agent-scan 0.6.11 outputs in `test/fixtures/security-scan/`, a local stand-in for Snyk's analysis server, and state the rest as unproven.
