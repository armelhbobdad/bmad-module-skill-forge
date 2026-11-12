---
created: "2026-11-09 12:03"
session: "77252030-8c80-4285-b88e-c15f43930eb7"
---

# Shipping Test Skill fixes on test evidence

Test Skill fixes may merge, close their issues and ship in a release on test evidence alone, without waiting for a live Test Skill run, even when the issue (such as #997) lists a live run under "Done when". Told on 2026-11-09 that most of these fixes change LLM-followed step prose that only a real run proves, the maintainer decided: "We can ship the next release after all, oh-my-skills repo has an open issue and it is our testing repo. If anything goes wrong, we will file a new issue anyway." oh-my-skills, the testing repository, runs the live check after the release, and whatever it finds is filed as a new issue here. Each PR still names the "Done when" live runs it left unproven. This narrows memory/step-file-bugs-invisible-to-tests ("run the workflow live against a real repository ... before calling it done") for backlog sweeps: the live run follows the release instead of gating the merge.
