---
created: "2026-10-02 07:49"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# nvm node missing from the Bash tool PATH

Node and npm exist only through nvm (`~/.nvm/versions/node/v24.21.0/bin`, loaded from `~/.bashrc`; `.nvmrc` says 24), and a Bash tool shell can start without that directory on PATH, as on 2026-10-02 when PATH began at `~/.local/go/bin` and `~/.cargo/bin`. Then `npm run changes:pr` and `node tools/validate-no-em-dash.js` exit 127 (command not found), which a script testing only for a nonzero exit reads as a failed check. Worse, the `needs_node` tests in `test/test-release-workflow.py` skip silently (`skipif(shutil.which("node") is None ...)`), so a pytest-only gate passes without them. When `which node` prints nothing or a check exits 127, prefix the command with `export PATH=$HOME/.nvm/versions/node/v24.21.0/bin:$PATH` and re-run. Read an exit of 127 as "did not run", never as a result.
