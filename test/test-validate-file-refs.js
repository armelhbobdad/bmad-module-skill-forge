/**
 * Tests for tools/validate-file-refs.js
 *
 * `npm run validate:refs` runs this tool with --strict in CI. These tests pin
 * the rule that every {project-root}/src/<path> is preceded by its installed
 * twin {project-root}/_bmad/skf/<path>: an installed project has no src/ tree,
 * so a src/ path with no installed path before it dangles there.
 *
 * The pure check is called directly; the exit-code and output tests drive the
 * tool against throwaway fixture trees through its --src-dir override.
 */

const assert = require('node:assert');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const TOOL = path.join(__dirname, '..', 'tools', 'validate-file-refs.js');
const { findSrcPathRefs } = require(TOOL);

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

const I = (p) => `{project-root}/_bmad/skf/${p}`;
const S = (p) => `{project-root}/src/${p}`;

/** [path, paired] for each src/ path found, in order. */
function pairs(text) {
  return findSrcPathRefs(text).map((r) => [r.path, r.paired]);
}

/**
 * Write a fixture src/ tree and run the tool on it.
 *
 * @param {Record<string,string>} files - Files by path relative to src/
 * @param {string[]} flags - Extra CLI flags
 * @param {Record<string,string>} env - Extra environment
 */
function runTool(files, flags = [], env = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vfr-'));
  tmpRoots.push(root);
  const srcDir = path.join(root, 'src');
  for (const [rel, body] of Object.entries(files)) {
    const full = path.join(srcDir, rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
  fs.mkdirSync(srcDir, { recursive: true });
  const childEnv = { ...process.env, ...env };
  // Never let a fixture run write annotations or the job summary of a real CI run
  if (!('GITHUB_ACTIONS' in env)) delete childEnv.GITHUB_ACTIONS;
  if (!('GITHUB_STEP_SUMMARY' in env)) delete childEnv.GITHUB_STEP_SUMMARY;
  const result = spawnSync(process.execPath, [TOOL, '--src-dir', srcDir, ...flags], { encoding: 'utf8', env: childEnv });
  return { root, status: result.status, out: result.stdout + result.stderr };
}

// --- findSrcPathRefs ---------------------------------------------------------

test('probe-order list: installed entry on the line before pairs the src entry', () => {
  const text = `x:\n  - '${I('shared/scripts/a.py')}'\n  - '${S('shared/scripts/a.py')}'\n`;
  assert.deepStrictEqual(pairs(text), [['shared/scripts/a.py', true]]);
});

test('same line, installed path first: paired', () => {
  assert.deepStrictEqual(pairs(`first of \`${I('shared/a.md')}\` then \`${S('shared/a.md')}\``), [['shared/a.md', true]]);
});

test('same line, src path first: unpaired (installed must come first)', () => {
  const text = `Try in order: \`${S('shared/a.md')}\`, then \`${I('shared/a.md')}\``;
  assert.deepStrictEqual(pairs(text), [['shared/a.md', false]]);
});

test('installed path only on the next line: unpaired', () => {
  assert.deepStrictEqual(pairs(`x:\n  - '${S('a.py')}'\n  - '${I('a.py')}'\n`), [['a.py', false]]);
});

test('installed path two lines up: unpaired', () => {
  assert.deepStrictEqual(pairs(`${I('a.py')}\n\n${S('a.py')}\n`), [['a.py', false]]);
});

test('a scalar with no twin at all (the frontmatter shape of the original defect): unpaired', () => {
  const text = `---\nnextStepFile: 'b.md'\nguard: '${S('shared/references/p.md')}'\n---\n`;
  assert.deepStrictEqual(findSrcPathRefs(text), [
    { line: 3, column: 8, token: S('shared/references/p.md'), path: 'shared/references/p.md', paired: false },
  ]);
});

test('a twin for a different path does not pair, even as a prefix match', () => {
  assert.deepStrictEqual(pairs(`${I('a.md')}x\n${S('a.md')}\n`), [['a.md', false]]);
  assert.deepStrictEqual(pairs(`${I('a.mdx')}\n${S('a.md')}\n`), [['a.md', false]]);
  assert.deepStrictEqual(pairs(`${I('b.md')}\n${S('a.md')}\n`), [['a.md', false]]);
});

test('fenced code is scanned: an unpaired command inside ```bash is reported', () => {
  const text = `Run:\n\n\`\`\`bash\nuv run ${S('shared/scripts/g.py')} \\\n    capture <p>\n\`\`\`\n`;
  assert.deepStrictEqual(pairs(text), [['shared/scripts/g.py', false]]);
});

test('fenced code is scanned: a paired diagnostic inside a fence passes', () => {
  const text = `\`\`\`\nError: at either of:\n  - ${I('shared/h.md')}\n  - ${S('shared/h.md')}\n\`\`\`\n`;
  assert.deepStrictEqual(pairs(text), [['shared/h.md', true]]);
});

test('a bare mention of the root is not a path', () => {
  assert.deepStrictEqual(pairs('# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during development)'), []);
  assert.deepStrictEqual(pairs('{project-root}/src/ during'), []);
});

test('sentence and list punctuation after a path is not part of it', () => {
  assert.deepStrictEqual(pairs(`Use ${I('a/b.md')}, else ${S('a/b.md')}.`), [['a/b.md', true]]);
  assert.deepStrictEqual(pairs(`- ${I('a/b.md')};\n- ${S('a/b.md')}:`), [['a/b.md', true]]);
});

test('CRLF line endings: pairing and paths are unaffected', () => {
  const text = `x:\r\n  - '${I('a.py')}'\r\n  - '${S('a.py')}'\r\n${S('c.py')}\r\n`;
  const refs = findSrcPathRefs(text);
  assert.deepStrictEqual(
    refs.map((r) => [r.line, r.path, r.paired]),
    [
      [3, 'a.py', true],
      [4, 'c.py', false],
    ],
  );
});

test('several paths on one line are judged one by one', () => {
  const text = `${I('x.py')} then ${S('x.py')}; and ${S('y.py')}`;
  assert.deepStrictEqual(pairs(text), [
    ['x.py', true],
    ['y.py', false],
  ]);
});

// --- The tool: exit codes, output, file types --------------------------------

test('--strict exits 1 on an unpaired src/ path and names it', () => {
  const { status, out } = runTool({ 'skf-a/references/s.md': `---\np: '${S('shared/p.md')}'\n---\n` }, ['--strict']);
  assert.strictEqual(status, 1, out);
  assert.match(out, /\[SRC-PATH\] Line 2: \{project-root\}\/src\/shared\/p\.md/);
  assert.match(out, /put \{project-root\}\/_bmad\/skf\/shared\/p\.md earlier on the line or on the line before/);
  assert.match(out, /Unpaired src\/ paths: 1/);
});

test('without --strict the same tree reports the path and exits 0', () => {
  const { status, out } = runTool({ 'skf-a/references/s.md': `${S('shared/p.md')}\n` });
  assert.strictEqual(status, 0, out);
  assert.match(out, /\[SRC-PATH\] Line 1:/);
});

test('.py, .toml and .json files are checked too', () => {
  for (const name of ['scripts/h.py', 'customize.toml', 'schemas/s.json']) {
    const { status, out } = runTool({ [`skf-a/${name}`]: `x = "${S('shared/p.md')}"\n` }, ['--strict']);
    assert.strictEqual(status, 1, `${name}: ${out}`);
    assert.match(out, /Unpaired src\/ paths: 1/, name);
  }
});

test('a project override file under _bmad/custom/ is no broken reference', () => {
  const line = 'Overrides: `{project-root}/_bmad/custom/skf-a.toml` and `{project-root}/_bmad/custom/skf-a.user.toml`.\n';
  const { status, out } = runTool({ 'skf-a/SKILL.md': line }, ['--strict']);
  assert.strictEqual(status, 0, out);
  assert.match(out, /Broken references: 0/);
});

test('a paired tree passes --strict', () => {
  const { status, out } = runTool(
    {
      'shared/p.md': '# p\n',
      'skf-a/references/s.md': `---\npProbeOrder:\n  - '${I('shared/p.md')}'\n  - '${S('shared/p.md')}'\n---\n`,
    },
    ['--strict'],
  );
  assert.strictEqual(status, 0, out);
  assert.match(out, /Unpaired src\/ paths: 0/);
});

test('in GitHub Actions: a ::warning annotation and a job-summary row', () => {
  const summaryDir = fs.mkdtempSync(path.join(os.tmpdir(), 'vfr-sum-'));
  tmpRoots.push(summaryDir);
  const summary = path.join(summaryDir, 'summary.md');
  const { status, out } = runTool({ 'skf-a/s.md': `\n${S('shared/p.md')}\n` }, ['--strict'], {
    GITHUB_ACTIONS: 'true',
    GITHUB_STEP_SUMMARY: summary,
  });
  assert.strictEqual(status, 1, out);
  assert.match(out, /::warning file=src[\\/]skf-a[\\/]s\.md,line=2::src\/ path with no installed twin before it/);
  assert.match(
    fs.readFileSync(summary, 'utf8'),
    /\| src[\\/]skf-a[\\/]s\.md \| 2 \| \{project-root\}\/src\/shared\/p\.md \| src-path unpaired \|/,
  );
});

test('--src-dir without an existing directory exits 2', () => {
  const result = spawnSync(process.execPath, [TOOL, '--src-dir', path.join(os.tmpdir(), 'vfr-does-not-exist-zz')], { encoding: 'utf8' });
  assert.strictEqual(result.status, 2, result.stdout + result.stderr);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
