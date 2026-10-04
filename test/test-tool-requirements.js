/**
 * Tests for tools/tool-requirements.js
 *
 * `npm run validate:tool-requirements` runs this tool with --check in CI.
 * These tests pin each kind of mismatch it reports (the generated table, the
 * prose minimums and the README badge, engines.node, .nvmrc, the workflows'
 * node-version and python-version, written out or in a matrix, the
 * ast-grep-cli pin, the README Acknowledgements rows, the list's own schema),
 * --write, and the PEP 723 requires-python headers under src/.
 *
 * Each case copies the files the tool reads into a throwaway folder, changes
 * one thing and runs the tool there through --root. Expected line numbers are
 * looked up in the copy, so an unrelated docs edit does not break a test.
 */

const assert = require('node:assert');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const REPO = path.join(__dirname, '..');
const TOOL = path.join(REPO, 'tools', 'tool-requirements.js');
const {
  compareVersions,
  lowerBound,
  readRequiresPython,
  loadRequirements,
  renderTable,
  checkAll,
  REQUIREMENTS,
  PREREQUISITES_DOC,
  START,
} = require(TOOL);

const FIXTURE_FILES = [
  REQUIREMENTS,
  PREREQUISITES_DOC,
  'docs/index.md',
  'README.md',
  'CONTRIBUTING.md',
  'package.json',
  '.nvmrc',
  '.github/workflows/quality.yaml',
  '.github/workflows/release.yaml',
  '.github/workflows/install-smoke.yaml',
];

let passed = 0;
let failed = 0;
const tmpRoots = [];

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`\u001B[32m✓\u001B[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`\u001B[31m✗\u001B[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

/** A copy of the files the tool reads, with an empty folder per workflow. */
function makeRoot() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'toolreq-'));
  tmpRoots.push(root);
  for (const file of FIXTURE_FILES) {
    const target = path.join(root, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(REPO, file), target);
  }
  for (const entry of fs.readdirSync(path.join(REPO, 'src'), { withFileTypes: true })) {
    if (entry.isDirectory() && entry.name.startsWith('skf-')) fs.mkdirSync(path.join(root, 'src', entry.name), { recursive: true });
  }
  return root;
}

function read(root, file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

function write(root, file, body) {
  const target = path.join(root, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, body);
}

/** Replace the first occurrence of `from`, which must exist. */
function edit(root, file, from, to) {
  const body = read(root, file);
  assert.ok(body.includes(from), `${file} holds no ${JSON.stringify(from)}`);
  write(root, file, body.replace(from, to));
}

/** The 1-based line of the first line of `file` holding `text`. */
function lineOf(root, file, text) {
  const index = read(root, file)
    .split('\n')
    .findIndex((line) => line.includes(text));
  assert.notStrictEqual(index, -1, `${file} holds no ${JSON.stringify(text)}`);
  return index + 1;
}

function run(root, flags = ['--check'], env = {}) {
  const childEnv = { ...process.env, ...env };
  if (!('GITHUB_ACTIONS' in env)) delete childEnv.GITHUB_ACTIONS;
  const result = spawnSync(process.execPath, [TOOL, '--root', root, ...flags], { encoding: 'utf8', env: childEnv });
  return { status: result.status, out: result.stdout + result.stderr };
}

/** Run --check and expect exit 1 with a finding at file:line. */
function expectFinding(root, file, line, pattern) {
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  const finding = out.split('\n').find((text) => text.startsWith(`${file}:${line}: `));
  assert.ok(finding, `no finding at ${file}:${line} in:\n${out}`);
  if (pattern) assert.match(finding, pattern);
}

// --- Pure helpers ---

test('compareVersions reads missing parts as 0', () => {
  assert.strictEqual(compareVersions('22', '22.0.0'), 0);
  assert.strictEqual(compareVersions('3.10', '3.11'), -1);
  assert.strictEqual(compareVersions('0.45', '0.45.3'), -1);
  assert.strictEqual(compareVersions('0.46.0', '0.45.3'), 1);
});

test('lowerBound takes the >= clause of a requires-python specifier', () => {
  assert.strictEqual(lowerBound('>=3.10'), '3.10');
  assert.strictEqual(lowerBound('>=3.11,<4'), '3.11');
  assert.strictEqual(lowerBound('<4, >= 3.9'), '3.9');
  assert.strictEqual(lowerBound('==3.12'), null);
});

test('readRequiresPython reads the # /// script block, not a docstring that quotes one', () => {
  const header = readRequiresPython(['# /// script', '# requires-python = ">=3.11"', '# dependencies = []', '# ///', '"""x"""']);
  assert.deepStrictEqual(header, { spec: '>=3.11', line: 2 });
  assert.strictEqual(readRequiresPython(['"""', 'requires-python = ">=3.10"', '"""']), null);
});

test('renderTable: one row per tool with its minimum and tested versions, then the fixed rows', () => {
  const tools = loadRequirements(REPO).data.tools;
  const table = renderTable(tools);
  assert.match(table[0], /^\| Tool +\| Used for +\| Minimum +\| Tested on +\| Install +\|$/);
  assert.match(table[1], /^\| -+ \| -+ \| -+ \| -+ \| -+ \|$/);
  assert.strictEqual(table.length, 2 + Object.keys(tools).length + 2);
  const astGrep = table.find((row) => row.startsWith('| `ast-grep` (CLI'));
  assert.match(astGrep, /\| 0\.45\.3 +\| 0\.45\.3 +\|/);
  // No minimum reads `none`, and no tested version `not recorded`.
  const unrecorded = renderTable({ ...tools, qmd: { ...tools.qmd, minimum: null, tested: [] } });
  assert.match(
    unrecorded.find((row) => row.startsWith('| `qmd`')),
    /\| none +\| not recorded +\|/,
  );
  for (const name of ['`git`', '`tessl`', '`skill-check`']) {
    assert.ok(
      table.some((row) => row.startsWith(`| ${name}`)),
      `no ${name} row`,
    );
  }
  assert.match(table.at(-1), /SNYK_TOKEN/);
  assert.ok(new Set(table.map((row) => row.length)).size === 1, 'rows are not padded to the same width');
});

// --- The repository and a clean copy ---

test('the repository agrees with its tool list', () => {
  const { status, out } = run(REPO);
  assert.strictEqual(status, 0, out);
  assert.match(out, /Tool versions agree with src\/shared\/tool-requirements\.yaml/);
});

test('a copy of the repository passes', () => {
  const { status, out } = run(makeRoot());
  assert.strictEqual(status, 0, out);
});

// --- Prose minimums ---

test('the README install line: a Node.js minimum that differs', () => {
  const root = makeRoot();
  edit(root, 'README.md', '[Node.js](https://nodejs.org/) >= 22', '[Node.js](https://nodejs.org/) >= 20');
  expectFinding(root, 'README.md', lineOf(root, 'README.md', 'nodejs.org/) >= 20'), /says 20, but the Node\.js minimum .* is 22/);
});

test('the README Python badge', () => {
  const root = makeRoot();
  edit(root, 'README.md', 'python-%3E%3D3.11', 'python-%3E%3D3.10');
  expectFinding(root, 'README.md', lineOf(root, 'README.md', 'python-%3E%3D3.10'), /Python badge says >=3\.10/);
});

test('docs/index.md: a Python minimum that differs', () => {
  const root = makeRoot();
  edit(root, 'docs/index.md', '[Python](https://www.python.org/) >= 3.11', '[Python](https://www.python.org/) >= 3.10');
  expectFinding(root, 'docs/index.md', lineOf(root, 'docs/index.md', 'python.org/) >= 3.10'), /Python minimum .* is 3\.11/);
});

test('the docs/getting-started.md install line, written with ≥', () => {
  const root = makeRoot();
  edit(root, PREREQUISITES_DOC, 'Python ≥ 3.11', 'Python ≥ 3.12');
  expectFinding(root, PREREQUISITES_DOC, lineOf(root, PREREQUISITES_DOC, 'Python ≥ 3.12'), /"Python ≥ 3\.12" says 3\.12/);
});

test('CONTRIBUTING.md: a Node.js minimum that differs', () => {
  const root = makeRoot();
  edit(root, 'CONTRIBUTING.md', '[Node.js](https://nodejs.org/) >= 22', '[Node.js](https://nodejs.org/) >= 21');
  expectFinding(root, 'CONTRIBUTING.md', lineOf(root, 'CONTRIBUTING.md', 'nodejs.org/) >= 21'));
});

test('any other docs page: "Node ≥ 20"', () => {
  const root = makeRoot();
  write(root, 'docs/extra.md', '# Extra\n\nYou need Node ≥ 20.\n');
  expectFinding(root, 'docs/extra.md', 3, /"Node ≥ 20" says 20/);
});

test('an install line that no longer states the minimum in a form the check reads', () => {
  const root = makeRoot();
  edit(root, 'docs/index.md', '[Python](https://www.python.org/) >= 3.11', '[Python](https://www.python.org/) 3.11 or newer');
  expectFinding(root, 'docs/index.md', 1, /no copy of the Python minimum: the install line must say "Python >= 3\.11"/);
});

// --- Copies outside the docs ---

test('package.json engines.node', () => {
  const root = makeRoot();
  edit(root, 'package.json', '"node": ">=22.0.0"', '"node": ">=20.0.0"');
  expectFinding(root, 'package.json', lineOf(root, 'package.json', '"node": ">=20.0.0"'), /engines\.node is ">=20\.0\.0"/);
});

test('.nvmrc', () => {
  const root = makeRoot();
  write(root, '.nvmrc', '23\n');
  expectFinding(root, '.nvmrc', 1, /not a Node\.js tested version .* \(22, 24\)/);
});

test('the install smoke test runs the Node.js minimum', () => {
  const root = makeRoot();
  const file = '.github/workflows/install-smoke.yaml';
  edit(root, file, 'node-version: "22"', 'node-version: "20"');
  expectFinding(root, file, lineOf(root, file, 'node-version: "20"'), /runs the Node\.js minimum .* \(22\)/);
});

test('the install smoke test sets no node-version', () => {
  const root = makeRoot();
  const file = '.github/workflows/install-smoke.yaml';
  edit(root, file, '          node-version: "22"\n', '');
  expectFinding(root, file, 1, /no node-version: the install smoke test runs the Node\.js minimum \(22\)/);
});

test('another workflow: a node-version that is not a tested version', () => {
  const root = makeRoot();
  const file = '.github/workflows/extra.yaml';
  write(
    root,
    file,
    `name: Extra
"on": push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v6
        with:
          node-version: "20"
`,
  );
  expectFinding(root, file, lineOf(root, file, 'node-version: "20"'), /node-version 20 is not a Node\.js tested version .* \(22, 24\)/);
});

test('a CI python-version that is not a tested version', () => {
  const root = makeRoot();
  const file = '.github/workflows/quality.yaml';
  edit(root, file, 'python-version: "3.12"', 'python-version: "3.13"');
  expectFinding(
    root,
    file,
    lineOf(root, file, 'python-version: "3.13"'),
    /python-version 3\.13 is not a Python tested version .* \(3\.11, 3\.12\)/,
  );
});

test('the release workflow python-version', () => {
  const root = makeRoot();
  const file = '.github/workflows/release.yaml';
  edit(root, file, 'python-version: "3.12"', 'python-version: "3.10"');
  expectFinding(root, file, lineOf(root, file, 'python-version: "3.10"'));
});

test('no workflow runs the Python minimum', () => {
  const root = makeRoot();
  const file = '.github/workflows/quality.yaml';
  edit(root, file, 'python-version: "3.11"', 'python-version: "3.12"');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /no workflow runs Python 3\.11, the minimum/);
});

test('a matrix and a list are read item by item, each at its line and once; another expression is skipped', () => {
  const root = makeRoot();
  // The matrix below is left as the only run of the Python minimum.
  edit(root, '.github/workflows/quality.yaml', 'python-version: "3.11"', 'python-version: "3.12"');
  const file = '.github/workflows/extra.yaml';
  write(
    root,
    file,
    `name: Extra
"on": push
jobs:
  test:
    strategy:
      matrix:
        python: ["3.11", "3.10"]
        node: ["24"]
        include:
          - node: "20"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v6
        with:
          python-version: \${{ matrix.python }}
      - uses: astral-sh/setup-uv@v8.2.0
        with:
          python-version: \${{ matrix.python }}
      - uses: actions/setup-node@v6
        with:
          node-version: \${{ matrix.node }}
      - uses: actions/setup-python@v6
        with:
          python-version: ["3.12", "3.13"]
      - uses: actions/setup-python@v6
        with:
          python-version: \${{ inputs.python }}
`,
  );
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.deepStrictEqual(
    out.split('\n').filter((line) => /^\S+:\d+: /.test(line)),
    [
      `${file}:${lineOf(root, file, '- node: "20"')}: node-version 20 is not a Node.js tested version in ${REQUIREMENTS} (22, 24)`,
      `${file}:${lineOf(root, file, 'python: ["3.11", "3.10"]')}: python-version 3.10 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
      `${file}:${lineOf(root, file, '["3.12", "3.13"]')}: python-version 3.13 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
    ],
  );
});

test('a multi-line value, an alias and the with: of a reusable workflow call are read too', () => {
  const root = makeRoot();
  const file = '.github/workflows/extra.yaml';
  write(
    root,
    file,
    `name: Extra
"on": push
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      PYTHON: &python "3.8"
    steps:
      - uses: actions/setup-python@v6
        with:
          python-version: |
            3.12
            3.9
      - uses: astral-sh/setup-uv@v8.2.0
        with:
          python-version: *python
  call:
    uses: ./.github/workflows/reusable.yaml
    with:
      node-version: "21"
`,
  );
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.deepStrictEqual(
    out.split('\n').filter((line) => /^\S+:\d+: /.test(line)),
    [
      `${file}:${lineOf(root, file, 'node-version: "21"')}: node-version 21 is not a Node.js tested version in ${REQUIREMENTS} (22, 24)`,
      `${file}:${lineOf(root, file, 'python-version: |')}: python-version 3.9 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
      `${file}:${lineOf(root, file, '&python "3.8"')}: python-version 3.8 is not a Python tested version in ${REQUIREMENTS} (3.11, 3.12)`,
    ],
  );
});

test('a workflow that is not YAML: its versions cannot be read', () => {
  const root = makeRoot();
  const file = '.github/workflows/extra.yaml';
  write(root, file, 'jobs:\n  build: [\n');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /^\.github\/workflows\/extra\.yaml:\d+: not valid YAML: .+ \(its node-version and python-version are not checked\)$/m);
});

test('the ast-grep-cli pin in test:python', () => {
  const root = makeRoot();
  edit(root, 'package.json', 'ast-grep-cli==0.45.3', 'ast-grep-cli==0.45.2');
  expectFinding(
    root,
    'package.json',
    lineOf(root, 'package.json', '"test:python"'),
    /ast-grep-cli==0\.45\.2, which is not an ast-grep tested version/,
  );
});

test('a README Acknowledgements row for every tier and optional tool', () => {
  const root = makeRoot();
  const row = read(root, 'README.md')
    .split('\n')
    .find((line) => line.startsWith('| [QMD]('));
  edit(root, 'README.md', `${row}\n`, '');
  expectFinding(root, 'README.md', lineOf(root, 'README.md', '## Acknowledgements'), /no row for qmd \(a row whose link text is "QMD"/);
});

// --- The generated table and --write ---

test('a hand edit to the table is reported, and --write puts it back', () => {
  const root = makeRoot();
  edit(root, PREREQUISITES_DOC, '| 0.45.3  |', '| 0.42.0  |');
  expectFinding(root, PREREQUISITES_DOC, lineOf(root, PREREQUISITES_DOC, START), /run node tools\/tool-requirements\.js --write/);
  const wrote = run(root, ['--write']);
  assert.strictEqual(wrote.status, 0, wrote.out);
  assert.match(wrote.out, /Wrote the prerequisites table/);
  assert.strictEqual(read(root, PREREQUISITES_DOC), read(REPO, PREREQUISITES_DOC));
  const again = run(root, ['--write']);
  assert.strictEqual(again.status, 0, again.out);
  assert.match(again.out, /is up to date/);
});

test('a new minimum: --write regenerates the table, and every stale copy is still reported', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "3.11"\n    tested: ["3.11", "3.12"]', 'minimum: "3.12"\n    tested: ["3.12"]');
  const checked = run(root);
  assert.strictEqual(checked.status, 1, checked.out);
  assert.match(checked.out, /docs\/getting-started\.md:\d+: the prerequisites table differs/);
  const wrote = run(root, ['--write']);
  assert.strictEqual(wrote.status, 1, wrote.out);
  assert.doesNotMatch(wrote.out, /the prerequisites table differs/);
  assert.match(read(root, PREREQUISITES_DOC), /\| `Python` +\| .+ \| 3\.12 +\| 3\.12 +\|/);
  for (const [file, text] of [
    ['README.md', 'python-%3E%3D3.11'],
    ['docs/index.md', 'python.org/) >= 3.11'],
    [PREREQUISITES_DOC, 'Python ≥ 3.11'],
    ['CONTRIBUTING.md', 'python.org/) >= 3.11'],
    ['.github/workflows/quality.yaml', 'python-version: "3.11"'],
  ]) {
    assert.match(wrote.out, new RegExp(`${file.replaceAll('.', String.raw`\.`)}:${lineOf(root, file, text)}: `), `${file} not reported`);
  }
});

test('missing markers: --check and --write both report them', () => {
  const root = makeRoot();
  edit(root, PREREQUISITES_DOC, `${START}\n`, '');
  expectFinding(root, PREREQUISITES_DOC, 1, /no <!-- tool-requirements:start -->/);
  const wrote = run(root, ['--write']);
  assert.strictEqual(wrote.status, 1, wrote.out);
  assert.match(wrote.out, /add the two markers/);
});

// --- The list itself ---

test('schema: an unknown key, named at its line', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, '    upgrade: uv self update\n', '    upgrade: uv self update\n    minimun: "0.5"\n');
  expectFinding(root, REQUIREMENTS, lineOf(root, REQUIREMENTS, 'minimun:'), /tools\.uv: unknown key "minimun"/);
});

test('schema: a version written as a number', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "3.11"', 'minimum: 3.11');
  expectFinding(root, REQUIREMENTS, lineOf(root, REQUIREMENTS, 'minimum: 3.11'), /tools\.python\.minimum must be null or a quoted version/);
});

test('schema: a kind, a tier list and a workflow that do not exist', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'kind: optional', 'kind: required');
  edit(root, REQUIREMENTS, 'tiers: [Forge+]', 'tiers: [Forge Plus]');
  edit(root, REQUIREMENTS, 'workflows: [create-skill, test-skill]', 'workflows: [create-skill, test-skills]');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /tools\.tessl\.kind must be one of runtime, tier, optional/);
  assert.match(out, /tools\.ccc\.tiers must be a list of Quick, Forge, Forge\+, Deep/);
  assert.match(out, /tools\.tessl\.workflows names no src\/skf-<name> folder: test-skills/);
});

test('schema: a minimum above every tested version', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "0.45.3"', 'minimum: "0.46.0"');
  expectFinding(
    root,
    REQUIREMENTS,
    lineOf(root, REQUIREMENTS, 'minimum: "0.46.0"'),
    /minimum 0\.46\.0 is above every tested version \(0\.45\.3\)/,
  );
});

test('schema: Node and Python need a minimum, since the copy checks compare with it', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, 'minimum: "22"', 'minimum: null');
  edit(root, REQUIREMENTS, 'minimum: "3.11"', 'minimum: null');
  const lines = read(root, REQUIREMENTS).split('\n');
  const minimumLine = (key) => lines.findIndex((line, index) => index > lines.indexOf(`  ${key}:`) && line.startsWith('    minimum:')) + 1;
  expectFinding(root, REQUIREMENTS, minimumLine('node'), /tools\.node\.minimum must be a version: the copy checks need it/);
  expectFinding(root, REQUIREMENTS, minimumLine('python'), /tools\.python\.minimum must be a version: the copy checks need it/);
  assert.doesNotMatch(run(root).out, /null/);
});

test('schema: a tier tool with no Acknowledgements row name, and a tool the checks need', () => {
  const root = makeRoot();
  edit(root, REQUIREMENTS, '    acknowledged_as: QMD\n', '');
  edit(root, REQUIREMENTS, '  node:\n', '  nodejs:\n');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /tools\.qmd\.acknowledged_as is missing/);
  assert.match(out, /tools\.node is missing: the copy checks need it/);
});

test('a list that is not YAML, a missing list and no mode exit 2', () => {
  const root = makeRoot();
  write(root, REQUIREMENTS, 'tools: [\n');
  const broken = run(root);
  assert.strictEqual(broken.status, 2, broken.out);
  assert.match(broken.out, /not valid YAML/);
  fs.rmSync(path.join(root, REQUIREMENTS));
  const missing = run(root);
  assert.strictEqual(missing.status, 2, missing.out);
  assert.match(missing.out, /tool-requirements\.yaml not found/);
  const usage = run(makeRoot(), []);
  assert.strictEqual(usage.status, 2, usage.out);
});

test('in GitHub Actions each finding is also an error annotation', () => {
  const root = makeRoot();
  write(root, '.nvmrc', '23\n');
  const { status, out } = run(root, ['--check'], { GITHUB_ACTIONS: 'true' });
  assert.strictEqual(status, 1, out);
  assert.match(out, /^::error file=\.nvmrc,line=1::/m);
});

// --- requires-python headers ---

test('a requires-python header below the Python minimum, at its file and line; a docstring that quotes one is not read', () => {
  const root = makeRoot();
  const header = (spec) => `# /// script\n# requires-python = "${spec}"\n# dependencies = []\n# ///\n`;
  write(root, 'src/shared/scripts/old.py', `${header('>=3.9')}"""Quotes requires-python = ">=3.8" in its docstring."""\n`);
  write(root, 'src/skf-campaign/scripts/shebang.py', `#!/usr/bin/env python3\n${header('>=3.10')}import tomllib\n`);
  write(root, 'src/skf-setup/scripts/new.py', `${header('>=3.11,<4')}print("ok")\n`);
  write(root, 'src/shared/scripts/plain.py', 'print("no header")\n');
  expectFinding(root, 'src/shared/scripts/old.py', 2, /requires-python = ">=3\.9" is below the Python minimum .*: declare ">=3\.11"/);
  expectFinding(root, 'src/skf-campaign/scripts/shebang.py', 3, /requires-python = ">=3\.10"/);
  assert.deepStrictEqual(
    checkAll(root, loadRequirements(root)).map((finding) => `${finding.file}:${finding.line}`),
    ['src/shared/scripts/old.py:2', 'src/skf-campaign/scripts/shebang.py:3'],
  );
});

test('every requires-python header under src/ declares the Python minimum', () => {
  const minimum = loadRequirements(REPO).data.tools.python.minimum;
  const below = checkAll(REPO, loadRequirements(REPO)).filter((finding) => /requires-python/.test(finding.message));
  assert.deepStrictEqual(below, [], `headers below ">=${minimum}"`);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
