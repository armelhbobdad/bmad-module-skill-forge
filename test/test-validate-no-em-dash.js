/**
 * Tests for tools/validate-no-em-dash.js
 *
 * `npm run validate:em-dash` runs this tool with --strict in CI. These tests
 * pin its three checks (the clean published docs, the lines a branch adds and
 * the branch's commit messages), the exempt snippet line and the base-branch
 * fallback.
 *
 * The pure helpers are called directly; the exit-code tests drive the tool
 * against throwaway git repositories through its --root and --base flags.
 * Every em dash here is written as an escape, because this file's own added
 * lines are checked too.
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const TOOL = path.join(__dirname, '..', 'tools', 'validate-no-em-dash.js');
const { hasEmDash, inCleanSet, findAddedEmDashes } = require(TOOL);

const D = '\u2014';
// Entity spellings are assembled so that this file does not trip the check it tests.
const AMP = '&';

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

/** Environment for git and the tool: no CI markers, no inherited repository. */
function cleanEnv(extra = {}) {
  const env = { ...process.env };
  for (const key of [
    'GITHUB_ACTIONS',
    'GITHUB_BASE_REF',
    'GITHUB_STEP_SUMMARY',
    'CI',
    'EM_DASH_BASE',
    'GIT_DIR',
    'GIT_INDEX_FILE',
    'GIT_WORK_TREE',
  ]) {
    delete env[key];
  }
  return {
    ...env,
    GIT_AUTHOR_NAME: 'Test',
    GIT_AUTHOR_EMAIL: 'test@example.com',
    GIT_COMMITTER_NAME: 'Test',
    GIT_COMMITTER_EMAIL: 'test@example.com',
    GIT_CONFIG_NOSYSTEM: '1',
    ...extra,
  };
}

function write(root, files) {
  for (const [rel, body] of Object.entries(files)) {
    const full = path.join(root, rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
}

function git(root, args) {
  execFileSync('git', ['-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', ...args], {
    cwd: root,
    env: cleanEnv(),
    stdio: 'pipe',
  });
}

function commitAll(root, message) {
  git(root, ['add', '-A']);
  git(root, ['commit', '-q', '-m', message]);
}

/**
 * A repository whose `main` holds `base` files, with a `feature` branch
 * checked out on top of it.
 */
function makeRepo(base) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vned-'));
  tmpRoots.push(root);
  git(root, ['init', '-q', '-b', 'main']);
  write(root, base);
  commitAll(root, 'base');
  git(root, ['switch', '-q', '-c', 'feature']);
  return root;
}

function run(root, flags = ['--strict', '--base', 'main'], env = {}) {
  const result = spawnSync(process.execPath, [TOOL, '--root', root, ...flags], { encoding: 'utf8', env: cleanEnv(env) });
  return { status: result.status, out: result.stdout + result.stderr };
}

const BASE = {
  'src/skill.md': `old line ${D} left alone\n`,
  'docs/page.md': 'A clean page.\n',
  'CHANGELOG.md': '# Changelog\n',
};

// --- Pure helpers ---

test('hasEmDash: the character and its three HTML entities', () => {
  assert.strictEqual(hasEmDash(`a ${D} b`), true);
  assert.strictEqual(hasEmDash(`a ${AMP}mdash; b`), true);
  assert.strictEqual(hasEmDash(`a ${AMP}#8212; b`), true);
  assert.strictEqual(hasEmDash(`a ${AMP}#X2014; b`), true);
});

test('hasEmDash: hyphens and en dashes pass', () => {
  assert.strictEqual(hasEmDash('steps 2\u201310 - see below'), false);
});

test('hasEmDash: context-snippet lines are exempt', () => {
  assert.strictEqual(hasEmDash(`|IMPORTANT: zod v3.23.8 ${D} read SKILL.md before writing zod code.`), false);
  assert.strictEqual(hasEmDash(`  |IMPORTANT: x v1 ${D} read SKILL.md`), false);
  assert.strictEqual(hasEmDash(`|key-types:SKILL.md#key-types ${D} SearchType: GRAPH_COMPLETION`), false);
  assert.strictEqual(hasEmDash(`|gotchas: v1 removed ${D} import from core`), false);
  assert.strictEqual(hasEmDash(`Note |IMPORTANT: x ${D} y`), true);
});

test('hasEmDash: a Markdown table row is not a snippet line', () => {
  assert.strictEqual(hasEmDash(`| Name | Value ${D} note |`), true);
  assert.strictEqual(hasEmDash(`| key: value ${D} note |`), true);
});

test('inCleanSet: README, docs and website, minus docs/_internal and generated files', () => {
  assert.strictEqual(inCleanSet('README.md'), true);
  assert.strictEqual(inCleanSet('docs/workflows.md'), true);
  assert.strictEqual(inCleanSet('docs/_data/pinned.yaml'), true);
  assert.strictEqual(inCleanSet('website/astro.config.mjs'), true);
  assert.strictEqual(inCleanSet('docs/_internal/RELEASING.md'), false);
  assert.strictEqual(inCleanSet('website/package-lock.json'), false);
  assert.strictEqual(inCleanSet('src/skf-setup/SKILL.md'), false);
  assert.strictEqual(inCleanSet('CHANGELOG.md'), false);
  assert.strictEqual(inCleanSet('src/README.md'), false);
});

test('findAddedEmDashes: counts new-file line numbers across hunks and skips removed lines', () => {
  const diff = [
    'diff --git a/src/a.md b/src/a.md',
    '--- a/src/a.md',
    '+++ b/src/a.md',
    '@@ -2,0 +3,2 @@',
    '+clean',
    `+dirty ${D} here`,
    '@@ -9 +10 @@',
    `-old ${D} gone`,
    `+new ${D} line`,
    'diff --git a/CHANGELOG.md b/CHANGELOG.md',
    '--- a/CHANGELOG.md',
    '+++ b/CHANGELOG.md',
    '@@ -1,0 +2 @@',
    `+generated ${D} entry`,
  ].join('\n');
  assert.deepStrictEqual(
    findAddedEmDashes(diff).map((f) => `${f.file}:${f.line}`),
    ['src/a.md:4', 'src/a.md:10'],
  );
});

// --- The tool against real repositories ---

test('a branch that adds no em dash passes', () => {
  const root = makeRepo(BASE);
  write(root, { 'src/skill.md': `old line ${D} left alone\nnew clean line\n` });
  commitAll(root, 'feat: add a clean line');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
  assert.match(out, /No em dashes/);
});

test('an added line with an em dash fails, and an untouched old one does not', () => {
  const root = makeRepo(BASE);
  write(root, { 'src/skill.md': `old line ${D} left alone\nnew ${D} line\n` });
  commitAll(root, 'feat: add a line');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /src\/skill\.md:2: new/);
  assert.doesNotMatch(out, /src\/skill\.md:1:/);
});

test('an HTML entity in an added line fails', () => {
  const root = makeRepo(BASE);
  write(root, { 'src/other.md': `a ${AMP}mdash; b\n` });
  commitAll(root, 'feat: add a file');
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /src\/other\.md:1:/);
});

test('an em dash already in the clean set fails even when the branch did not add it', () => {
  const root = makeRepo({ ...BASE, 'docs/page.md': `Title ${D} subtitle\n` });
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /docs\/page\.md:1:/);
});

test('docs/_internal is outside the clean set', () => {
  const root = makeRepo({ ...BASE, 'docs/_internal/RELEASING.md': `old ${D} note\n` });
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('context-snippet lines may be quoted in the docs', () => {
  const root = makeRepo(BASE);
  write(root, {
    'docs/page.md': `A clean page.\n\n\`\`\`text\n|IMPORTANT: zod v3.23.8 ${D} read SKILL.md before writing zod code.\n\`\`\`\n`,
  });
  commitAll(root, 'docs: quote the snippet line');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('CHANGELOG.md is not checked', () => {
  const root = makeRepo(BASE);
  write(root, { 'CHANGELOG.md': `# Changelog\n\n- fix ${D} generated entry\n` });
  commitAll(root, 'chore: changelog');
  const { status, out } = run(root);
  assert.strictEqual(status, 0, out);
});

test('a commit message with an em dash fails', () => {
  const root = makeRepo(BASE);
  write(root, { 'src/new.md': 'clean\n' });
  commitAll(root, `feat: add a file\n\nWhy ${D} because.`);
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /commit [0-9a-f]{8} "feat: add a file" \(message line 3\)/);
});

test('an uncommitted working-tree line is checked too', () => {
  const root = makeRepo(BASE);
  write(root, { 'src/skill.md': `old line ${D} left alone\nwip ${D} line\n` });
  const { status, out } = run(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /src\/skill\.md:2: wip/);
});

test('without --strict findings are reported and the exit code is 0', () => {
  const root = makeRepo(BASE);
  write(root, { 'src/skill.md': `old line ${D} left alone\nnew ${D} line\n` });
  const { status, out } = run(root, ['--base', 'main']);
  assert.strictEqual(status, 0, out);
  assert.match(out, /1 em dash finding/);
});

test('a missing base skips the diff checks locally and fails in CI', () => {
  const root = makeRepo(BASE);
  write(root, { 'src/skill.md': `old line ${D} left alone\nnew ${D} line\n` });
  const local = run(root, ['--strict', '--base', 'origin/nope']);
  assert.strictEqual(local.status, 0, local.out);
  assert.match(local.out, /skipped: origin\/nope not found/);
  const ci = run(root, ['--strict', '--base', 'origin/nope'], { CI: 'true' });
  assert.strictEqual(ci.status, 2, ci.out);
  assert.match(ci.out, /base origin\/nope not found/);
});

test('on a pull request the base comes from GITHUB_BASE_REF', () => {
  const root = makeRepo(BASE);
  git(root, ['update-ref', 'refs/remotes/origin/main', 'main']);
  write(root, { 'src/skill.md': `old line ${D} left alone\nnew ${D} line\n` });
  commitAll(root, 'feat: add a line');
  const { status, out } = run(root, ['--strict'], { GITHUB_BASE_REF: 'main', CI: 'true' });
  assert.strictEqual(status, 1, out);
  assert.match(out, /since origin\/main/);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
