---
created: "2026-10-13 18:30"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# Path.resolve link-loop RuntimeError on Python 3.11 and 3.12

On Python 3.11 and 3.12, `Path.resolve(strict=True)` on a link loop raises `RuntimeError: Symlink loop from '<path>'` rather than the `OSError` that 3.13 and later raise. CI's `python` job in `.github/workflows/quality.yaml` runs on 3.11 (the minimum in `src/shared/tool-requirements.yaml`) on ubuntu and windows. A local `uv run` picks the newest managed interpreter instead, so a helper catching only `OSError` passes locally and prints a traceback on CI or on a user's 3.11. Catch `(OSError, RuntimeError)` around `resolve(strict=True)`, as `read_link_target` in `src/shared/scripts/skf-update-active-symlink.py`, `skf-skill-inventory.py` and `skf-enumerate-stack-skills.py` do. `_active_target` in `src/shared/scripts/skf-update-run-state.py` still catches only `OSError`, so a looping `active` link crashes Update Skill's rollback on 3.11; the gap is logged only in the gitignored `_bmad-output/implementation-artifacts/deferred-work.md`. To test such a site, run `uv run --python 3.11`, or monkeypatch `Path.resolve` to raise the `RuntimeError`, as `test/test-skf-update-active-symlink.py` does for #735.
