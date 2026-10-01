/**
 * Tests for tools/changes.js and tools/covered-surfaces.js
 *
 * `npm run test:changes-tool` runs this file. release.yaml runs the gate
 * before anything is committed and renders CHANGELOG.md and the release
 * notes with the same code, so these tests pin:
 * - fragment validation, case by case;
 * - the gate matrix: every refusal, every pass, and the version each bump
 *   gives, computed as the Bump version step computes it;
 * - a golden render of the fixture fragments, and the insertion into the
 *   real CHANGELOG.md with every older release left byte-identical;
 * - the commands end to end against throwaway git repositories, released
 *   fragments edited, renamed or copied included;
 * - the pr command on branches of those repositories: a change to the code
 *   the package ships (renames and deletions included) needs a fragment or
 *   a "Changelog: none (<reason>)" line, in any commit, merges included,
 *   and never the placeholder; the line never covers a removed or added
 *   covered item; a breaking fragment must name the removed item, an added
 *   one covers an addition, and an unreleased fragment the branch only edits
 *   counts only for the items it names; the release branch of this
 *   repository is exempt, and one from a fork or an unknown repository is
 *   not; a malformed or released fragment fails, against the last stable tag
 *   of the base; a failure prints a fragment to fill in that fails until its
 *   marked sentences are rewritten; the base resolves as the em dash check's
 *   does, and a shallow clone that hides the merge base says so;
 * - the extractors against this checkout (all 16 SKILL.md files read, `CA`
 *   and `--target-ref` found, `write_failure` gone, and every workflow that
 *   had flags at the pinned commit still has flags);
 * - a flag whose row is deleted while its workflow's Markdown still names it
 *   is a review item, listed first; a flag no file of its workflow names is
 *   hard, and so is one named only in a helper call, another program's
 *   command or a note that it was renamed; a flag that leaves the rows as a
 *   new name enters them is a possible rename, also hard;
 * - tool minimums in src/shared/tool-requirements.yaml: a raised or new one
 *   is hard and needs a breaking fragment that names the tool, a lowered or
 *   removed one is additive, and a tested version is no surface; every
 *   minimum v3.0.0 sets is named by a breaking fragment;
 * - backtests against the real history: v1.9.0..v2.0.0 finds only the
 *   `onboard` removal, v2.0.0..v2.0.1 finds skf-campaign's flags moved out of
 *   their Overrides row (review, not hard), no other pair of stable tags up to
 *   v2.2.0 has a hard item, and v2.2.0 to the pinned commit finds
 *   `write_failure` and five additions; the last stable tag against HEAD is a
 *   smoke test.
 *
 * The backtests need the release tags. A CI run without them fails; a local
 * run skips them and says to run `git fetch --tags`. Every em dash here is
 * built from its code point, because this file's own added lines are checked.
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const CHANGES_TOOL = path.join(ROOT, 'tools', 'changes.js');
const SURFACES_TOOL = path.join(ROOT, 'tools', 'covered-surfaces.js');
const FIXTURES = path.join(__dirname, 'fixtures', 'changes');
const changes = require(CHANGES_TOOL);
const surfaces = require(SURFACES_TOOL);

const EM_DASH = String.fromCodePoint(0x20_14);
// Entity spellings are assembled so that this file does not trip the em dash check.
const AMP = '&';
const REPO = 'https://github.com/armelhbobdad/bmad-module-skill-forge';
const IN_CI = process.env.GITHUB_ACTIONS === 'true' || process.env.CI === 'true';
// The merge of #554, the last commit the v3.0.0 design backtested against.
const PINNED_COMMIT = 'e8200f24';

let passed = 0;
let failed = 0;
let skipped = 0;
const tmpRoots = [];

function test(name, fn) {
  try {
    const result = fn();
    if (result === 'skip') {
      skipped += 1;
      console.log(`- ${name} (skipped)`);
      return;
    }
    passed += 1;
    console.log(`\u001B[32m✓\u001B[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`\u001B[31m✗\u001B[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

// --- Helpers ---

/** A parsed, valid fragment for the pure-function tests. */
function frag(type, data = {}, name = `${type}-${Math.random().toString(36).slice(2, 8)}.yaml`) {
  const base = { type, summary: `A ${type} change.` };
  if (type !== 'lead' && type !== 'docs') base.scope = 'skf-setup';
  if (type === 'breaking') base.migration = 'Do the new thing.';
  return { file: `changes/${name}`, name, data: { ...base, ...data }, errors: [] };
}

function hardFinding(token) {
  return {
    group: 'hard',
    kind: 'schema-enum',
    change: 'removed',
    workflow: 'skf-setup',
    token,
    text: `skf-setup: schema enum value \`${token}\` removed`,
  };
}

function additiveFinding(token) {
  return {
    group: 'additive',
    kind: 'flag',
    change: 'added',
    workflow: 'skf-update-skill',
    token,
    text: `skf-update-skill: flag \`${token}\` added`,
  };
}

function gate({ bump, current = '2.2.0', baseTag = 'v2.2.0', fragments = [], hard = [], additive = [] }) {
  const next = changes.nextVersion(current, bump);
  const found = { hard: hard.map((token) => hardFinding(token)), additive: additive.map((token) => additiveFinding(token)), review: [] };
  return changes.evaluateGate({ next, bump, current, baseTag, fragments, surfaces: found });
}

/**
 * Environment for git and the tools: no CI markers, no inherited repository,
 * and none of the pull request's refs (the em-dash job runs these tests on
 * one, and the pr command reads them).
 */
function cleanEnv(extra = {}) {
  const env = { ...process.env };
  for (const key of [
    'GITHUB_ACTIONS',
    'GITHUB_STEP_SUMMARY',
    'GITHUB_BASE_REF',
    'GITHUB_HEAD_REF',
    'GITHUB_REPOSITORY',
    'PR_HEAD_REPO',
    'CI',
    'GIT_DIR',
    'GIT_INDEX_FILE',
    'GIT_WORK_TREE',
  ])
    delete env[key];
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
    if (body === null) {
      fs.rmSync(full, { force: true });
      continue;
    }
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
}

function git(root, args) {
  return execFileSync('git', ['-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'core.hooksPath=/dev/null', ...args], {
    cwd: root,
    env: cleanEnv(),
    encoding: 'utf8',
    stdio: 'pipe',
  });
}

function commitAll(root, message) {
  git(root, ['add', '-A']);
  git(root, ['commit', '-q', '-m', message]);
}

const TEMP_CHANGELOG = [
  '# Changelog',
  '',
  'Preamble.',
  '',
  '## [Unreleased]',
  '',
  '## [1.0.0](https://github.com/example/tool/compare/v0.9.0...v1.0.0) (2026-01-01)',
  '',
  '### Bug Fixes',
  '',
  '* **old:** an old entry',
  '',
].join('\n');

const TEMP_SCHEMA = JSON.stringify(
  {
    type: 'object',
    properties: { tool_setup: { type: 'object', properties: { status: { enum: ['success', 'write_failure', 'blocked'] } } } },
  },
  null,
  2,
);

/**
 * A repository tagged v1.0.0 with one released fragment, a schema and a
 * CHANGELOG.md, ready for the next release's changes on top.
 */
function makeRepo({ version = '1.0.0', tag = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'skf-changes-'));
  tmpRoots.push(root);
  git(root, ['init', '-q', '-b', 'main']);
  write(root, {
    'package.json': JSON.stringify(
      { name: 'example-tool', version, repository: { type: 'git', url: 'git+https://github.com/example/tool.git' } },
      null,
      2,
    ),
    'CHANGELOG.md': TEMP_CHANGELOG,
    'changes/README.md': '# Change fragments\n',
    'changes/released-before.yaml': 'type: breaking\nscope: old\nsummary: Released at v1.0.0.\nmigration: Nothing now.\n',
    'src/shared/scripts/schemas/skf-tool-result-envelope.v1.json': TEMP_SCHEMA,
    'src/skf-tool/SKILL.md':
      '# Tool\n\n| Aspect | Detail |\n|---|---|\n| **Flags** | `--headless` / `-H` (skip prompts); `--dry-run` (write nothing) |\n',
  });
  commitAll(root, 'base');
  if (tag) git(root, ['tag', '-a', 'v1.0.0', '-m', 'v1.0.0']);
  return root;
}

function runTool(tool, args, env = {}) {
  const result = spawnSync(process.execPath, [tool, ...args], { encoding: 'utf8', env: cleanEnv(env) });
  return { status: result.status, out: result.stdout + result.stderr };
}

function hasRefs(refs) {
  return refs.every((ref) => surfaces.resolveCommit(ROOT, ref));
}

/** Skip locally, fail in CI, when the history the backtests read is missing. */
function needRefs(refs) {
  if (hasRefs(refs)) return true;
  const message = `missing ${refs.filter((ref) => !surfaces.resolveCommit(ROOT, ref)).join(', ')}: run git fetch --tags`;
  if (IN_CI) throw new Error(message);
  console.log(`  ${message}`);
  return false;
}

function tokens(findings) {
  return findings.map((finding) => finding.token).sort();
}

function describeFindings(findings) {
  return findings.map((finding) => finding.text).join('\n');
}

// --- Fragment validation ---

test('every fixture fragment is valid', () => {
  for (const name of fs.readdirSync(path.join(FIXTURES, 'fragments'))) {
    const parsed = changes.parseFragment(`changes/${name}`, fs.readFileSync(path.join(FIXTURES, 'fragments', name), 'utf8'));
    assert.deepStrictEqual(parsed.errors, [], name);
  }
});

test('validateFragment: one valid fragment of each type', () => {
  for (const type of ['breaking', 'added', 'changed', 'fixed', 'docs', 'lead']) {
    assert.deepStrictEqual(changes.validateFragment(frag(type).data), [], type);
  }
  assert.deepStrictEqual(changes.validateFragment({ type: 'docs', scope: 'docs', summary: 'x' }), [], 'docs may carry a scope');
  assert.deepStrictEqual(changes.validateFragment({ ...frag('fixed').data, issues: [502], prs: [509, 517] }), []);
});

const INVALID = [
  ['a list, not a mapping', ['type: fixed'], /YAML mapping/],
  ['no summary', { type: 'fixed', scope: 'skf-setup' }, /summary is required/],
  ['a blank summary', { type: 'fixed', scope: 'skf-setup', summary: '  \n' }, /summary is required/],
  ['an unknown key', { ...frag('fixed').data, title: 'x' }, /unknown key "title"/],
  ['an old type name', { ...frag('fixed').data, type: 'feature' }, /type must be one of breaking, added, changed, fixed, docs, lead/],
  ['a breaking change with no migration', { type: 'breaking', scope: 'skf-setup', summary: 'x' }, /needs a migration/],
  ['a breaking change with a blank migration', { type: 'breaking', scope: 'skf-setup', summary: 'x', migration: ' ' }, /needs a migration/],
  ['a migration on a fix', { ...frag('fixed').data, migration: 'x' }, /only for breaking changes/],
  ['no scope on a fix', { type: 'fixed', summary: 'x' }, /scope is required/],
  ['an upper-case scope', { ...frag('fixed').data, scope: 'SKF-Setup' }, /scope must be one line/],
  ['a two-line scope', { ...frag('fixed').data, scope: 'a\nb' }, /scope must be one line/],
  ['issues as a number', { ...frag('fixed').data, issues: 502 }, /issues must be a list/],
  ['prs with a string', { ...frag('fixed').data, prs: ['#509'] }, /prs must be a list of pull request numbers/],
  ['an empty prs list', { ...frag('fixed').data, prs: [] }, /prs must be a list/],
  ['issue number zero', { ...frag('fixed').data, issues: [0] }, /issues must be a list/],
  ['a lead with a scope', { type: 'lead', scope: 'skf-setup', summary: 'x' }, /a lead takes only a summary, not scope/],
  ['a lead with prs', { type: 'lead', summary: 'x', prs: [1] }, /a lead takes only a summary, not prs/],
  ['an em dash in a summary', { ...frag('fixed').data, summary: `now ${EM_DASH} then` }, /summary has an em dash/],
  ['an em dash entity in a migration', { ...frag('breaking').data, migration: `do ${AMP}mdash; this` }, /migration has an em dash/],
  ['a step-file section in a summary', { ...frag('fixed').data, summary: 'see init.md §4' }, /cites a step-file section/],
  ['two paragraphs', { ...frag('fixed').data, summary: 'one\n\ntwo\n' }, /one paragraph/],
  [
    'the template text in a summary',
    { ...frag('fixed').data, summary: 'Rewrite this paragraph: what a user sees.' },
    /summary still holds the template text/,
  ],
  [
    'the template text in a migration',
    { ...frag('breaking').data, migration: 'Rewrite this paragraph: the action.' },
    /migration still holds the template text/,
  ],
];

for (const [name, data, pattern] of INVALID) {
  test(`validateFragment rejects ${name}`, () => {
    const errors = changes.validateFragment(data);
    assert.ok(
      errors.some((error) => pattern.test(error)),
      `expected ${pattern}, got ${JSON.stringify(errors)}`,
    );
  });
}

test('parseFragment: bad YAML, a duplicate key and a bad file name', () => {
  assert.match(changes.parseFragment('changes/a.yaml', 'type: [fixed\n').errors.join('; '), /not valid YAML/);
  assert.match(
    changes.parseFragment('changes/a.yaml', 'type: fixed\ntype: added\nscope: x\nsummary: y\n').errors.join('; '),
    /not valid YAML/,
  );
  assert.match(changes.parseFragment('changes/Bad_Name.yaml', 'type: fixed\nscope: x\nsummary: y\n').errors.join('; '), /lower case/);
  assert.deepStrictEqual(changes.parseFragment('changes/good-name.yaml', 'type: fixed\nscope: x\nsummary: y\n').errors, []);
});

test('readFragments: README.md and .gitkeep are skipped, other files and folders are problems', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'skf-fragments-'));
  tmpRoots.push(root);
  write(root, {
    'changes/README.md': '# x\n',
    'changes/.gitkeep': '',
    'changes/ok.yaml': 'type: fixed\nscope: x\nsummary: y\n',
    'changes/notes.txt': 'x',
    'changes/wrong.yml': 'type: fixed\n',
    'changes/nested/a.yaml': 'type: fixed\n',
  });
  const { fragments, problems } = changes.readFragments(root);
  assert.deepStrictEqual(
    fragments.map((fragment) => fragment.file),
    ['changes/ok.yaml'],
  );
  assert.deepStrictEqual(problems.map((problem) => problem.file).sort(), ['changes/nested', 'changes/notes.txt', 'changes/wrong.yml']);
});

// --- Versions and the gate matrix ---

test('nextVersion matches npm version in the Bump version step', () => {
  assert.strictEqual(changes.nextVersion('2.2.0', 'patch'), '2.2.1');
  assert.strictEqual(changes.nextVersion('2.2.0', 'minor'), '2.3.0');
  assert.strictEqual(changes.nextVersion('2.2.0', 'major'), '3.0.0');
  assert.strictEqual(changes.nextVersion('2.2.0', 'rc'), '2.2.1-rc.0');
  assert.strictEqual(changes.nextVersion('3.0.0-rc.0', 'rc'), '3.0.0-rc.1');
  assert.strictEqual(changes.nextVersion('3.0.0-alpha.2', 'rc'), '3.0.0-rc.0');
  assert.strictEqual(changes.nextVersion('3.0.0-rc.1', 'major'), '3.0.0');
  assert.strictEqual(changes.nextVersion('3.0.0-rc.1', 'patch'), '3.0.0');
  assert.throws(() => changes.nextVersion('2.2.0', 'huge'), /--bump must be one of/);
});

test('reachedLevel: semver.diff from the last stable tag, a premajor counting as major', () => {
  assert.strictEqual(changes.reachedLevel('2.2.0', '3.0.0'), 'major');
  assert.strictEqual(changes.reachedLevel('2.2.0', '3.0.1'), 'major');
  assert.strictEqual(changes.reachedLevel('2.2.0', '3.0.0-rc.1'), 'major');
  assert.strictEqual(changes.reachedLevel('2.2.0', '2.3.0-rc.1'), 'minor');
  assert.strictEqual(changes.reachedLevel('2.2.0', '2.2.1-alpha.0'), 'patch');
  assert.strictEqual(changes.reachedLevel('2.2.0', '2.2.0'), 'none');
  assert.strictEqual(changes.reachedLevel('2.2.0', '2.1.9'), 'none');
});

test('namesToken matches whole items only', () => {
  const fragment = frag('breaking', { summary: 'No more `write_failure`.', migration: 'Drop `--dry-run` and `CA`.' });
  assert.strictEqual(changes.namesToken(fragment, 'write_failure'), true);
  assert.strictEqual(changes.namesToken(fragment, '--dry-run'), true);
  assert.strictEqual(changes.namesToken(fragment, 'CA'), true);
  assert.strictEqual(changes.namesToken(fragment, 'write'), false);
  assert.strictEqual(changes.namesToken(fragment, 'dry-run-all'), false);
  assert.strictEqual(changes.namesToken(frag('breaking', { summary: 'x `write_failures` y' }), 'write_failure'), false);
});

test('namesToken counts a name only inside backticks', () => {
  const names = (summary, token) => changes.namesToken(frag('breaking', { summary }), token);
  assert.strictEqual(names('an error is now reported', 'error'), false, 'a plain word names nothing');
  assert.strictEqual(names('Exit code 3 is gone.', '3'), false);
  assert.strictEqual(names('The `error` property is gone.', 'error'), true);
  assert.strictEqual(names('Read `error.phase` instead.', 'error'), false, 'error.phase is another item');
  assert.strictEqual(names('Use `forge-auto`.', 'forge'), false);
  assert.strictEqual(names('Pass `--tier=<Quick>` now.', '--tier'), true, 'a span that starts with the flag');
  assert.strictEqual(names('`@Ferris CA` is gone.', 'CA'), true);
  assert.strictEqual(changes.namesToken(frag('breaking', { summary: 'x', migration: 'Test for\n`blocked`.' }), 'blocked'), true);
});

const breakingNamed = () => frag('breaking', { summary: 'The `write_failure` status is gone.' });
const GATE_MATRIX = [
  {
    name: 'major with a breaking fragment that names the hard item passes',
    bump: 'major',
    fragments: [breakingNamed()],
    hard: ['write_failure'],
    next: '3.0.0',
  },
  {
    name: 'patch under a breaking fragment is refused',
    bump: 'patch',
    fragments: [breakingNamed()],
    refuse: /2\.2\.1, a patch step from v2\.2\.0, below the minimum major/,
  },
  {
    name: 'minor under a hard removal is refused',
    bump: 'minor',
    fragments: [frag('fixed')],
    hard: ['write_failure'],
    refuse: /below the minimum major/,
  },
  {
    name: 'a hard item no breaking fragment names is refused',
    bump: 'major',
    fragments: [frag('breaking', { summary: 'Something else.' })],
    hard: ['write_failure'],
    refuse: /no breaking fragment names `write_failure`/,
  },
  {
    name: 'a hard item named only in an added fragment is refused',
    bump: 'major',
    fragments: [frag('breaking'), frag('added', { summary: 'About `write_failure`.' })],
    hard: ['write_failure'],
    refuse: /no breaking fragment names `write_failure`/,
  },
  {
    name: 'major with no breaking fragment is refused',
    bump: 'major',
    fragments: [frag('added')],
    refuse: /major release, but no fragment has type: breaking/,
  },
  {
    name: 'a stable release with no fragment is refused',
    bump: 'patch',
    fragments: [],
    refuse: /stable release needs at least one change fragment/,
  },
  {
    name: 'a lead alone is not a change',
    bump: 'patch',
    fragments: [frag('lead')],
    refuse: /stable release needs at least one change fragment/,
  },
  { name: 'minor with an added fragment passes', bump: 'minor', fragments: [frag('added')], next: '2.3.0' },
  { name: 'patch under an added fragment is refused', bump: 'patch', fragments: [frag('added')], refuse: /below the minimum minor/ },
  { name: 'patch under a changed fragment is refused', bump: 'patch', fragments: [frag('changed')], refuse: /below the minimum minor/ },
  { name: 'patch with fixed and docs fragments passes', bump: 'patch', fragments: [frag('fixed'), frag('docs')], next: '2.2.1' },
  {
    name: 'an additive surface raises a fixes-only release to minor',
    bump: 'patch',
    fragments: [frag('fixed')],
    additive: ['--target-ref'],
    refuse: /below the minimum minor/,
  },
  { name: 'a bump above the minimum passes', bump: 'minor', fragments: [frag('fixed')], next: '2.3.0' },
  {
    name: 'rc from a stable version cannot reach major and names the hand bump',
    bump: 'rc',
    fragments: [breakingNamed()],
    hard: ['write_failure'],
    refuse:
      /2\.2\.1-rc\.0, a patch step from v2\.2\.0, and a prerelease cannot reach the minimum major .* Set the version to 3\.0\.0-rc\.0 by hand/,
  },
  {
    name: 'the hand bump names every file to edit and the first prerelease it publishes',
    bump: 'rc',
    fragments: [breakingNamed()],
    refuse:
      /\(package\.json, package-lock\.json, \.claude-plugin\/marketplace\.json and docs\/_data\/pinned\.yaml\), then dispatch rc: the first rc published is 3\.0\.0-rc\.1\. Or release major directly\./,
  },
  {
    name: 'alpha names an alpha hand bump',
    bump: 'alpha',
    fragments: [breakingNamed()],
    refuse: /Set the version to 3\.0\.0-alpha\.0 by hand/,
  },
  {
    name: 'a lower prerelease id than the current one is refused',
    bump: 'alpha',
    current: '3.0.0-rc.1',
    fragments: [breakingNamed()],
    hard: ['write_failure'],
    refuse:
      /alpha from 3\.0\.0-rc\.1 gives 3\.0\.0-alpha\.0, which is below the current version 3\.0\.0-rc\.1: dispatch rc, patch, minor or major instead/,
  },
  {
    name: 'beta after an alpha passes',
    bump: 'beta',
    current: '3.0.0-alpha.2',
    fragments: [breakingNamed()],
    hard: ['write_failure'],
    next: '3.0.0-beta.0',
  },
  {
    name: 'rc under a minor minimum names 2.3.0-rc.0',
    bump: 'rc',
    fragments: [frag('added')],
    refuse: /Set the version to 2\.3\.0-rc\.0 by hand/,
  },
  {
    name: 'rc after the hand bump passes',
    bump: 'rc',
    current: '3.0.0-rc.0',
    fragments: [breakingNamed()],
    hard: ['write_failure'],
    next: '3.0.0-rc.1',
  },
  {
    name: 'major from an rc gives the final version',
    bump: 'major',
    current: '3.0.0-rc.1',
    fragments: [breakingNamed()],
    hard: ['write_failure'],
    next: '3.0.0',
  },
  { name: 'a prerelease with no fragment passes when nothing sets a minimum', bump: 'alpha', fragments: [], next: '2.2.1-alpha.0' },
  {
    name: 'a premajor prerelease with no breaking fragment is refused',
    bump: 'rc',
    current: '3.0.0-rc.0',
    fragments: [frag('fixed')],
    refuse: /no fragment has type: breaking/,
  },
  {
    name: 'a patch after a burned, untagged 3.0.0 gives 3.0.1 and passes',
    bump: 'patch',
    current: '3.0.0',
    fragments: [breakingNamed()],
    hard: ['write_failure'],
    next: '3.0.1',
  },
  {
    name: 'two lead fragments are refused',
    bump: 'patch',
    fragments: [frag('fixed'), frag('lead'), frag('lead')],
    refuse: /only one lead fragment per release/,
  },
  {
    name: 'an invalid fragment is refused',
    bump: 'patch',
    fragments: [frag('fixed'), { ...frag('fixed'), errors: ['summary is required'] }],
    refuse: /summary is required/,
  },
  {
    name: 'a version not above the last stable tag is refused',
    bump: 'patch',
    current: '2.1.0',
    fragments: [frag('fixed')],
    refuse: /2\.1\.1 is not above v2\.2\.0/,
  },
];

for (const row of GATE_MATRIX) {
  test(`gate: ${row.name}`, () => {
    const result = gate(row);
    if (row.refuse) {
      assert.ok(
        result.refusals.some((refusal) => row.refuse.test(refusal)),
        `expected ${row.refuse}, got ${JSON.stringify(result.refusals)}`,
      );
    } else {
      assert.deepStrictEqual(result.refusals, []);
      assert.strictEqual(result.next, row.next);
    }
  });
}

test('evaluateGate: files in changes/ to fix are refused, and a stable release needs an empty [Unreleased]', () => {
  const input = {
    next: '2.2.1',
    bump: 'patch',
    current: '2.2.0',
    baseTag: 'v2.2.0',
    fragments: [frag('fixed')],
    surfaces: { hard: [], additive: [], review: [] },
  };
  assert.deepStrictEqual(changes.evaluateGate({ ...input, problems: [{ file: 'changes/x.yml', errors: ['not a fragment'] }] }).refusals, [
    'changes/x.yml: not a fragment',
  ]);
  const stray = '# Changelog\n\n## [Unreleased]\n\n- a stray note\n\n## [2.2.0] (x)\n';
  assert.match(
    changes.evaluateGate({ ...input, changelog: stray }).refusals.join('\n'),
    /"## \[Unreleased]" in CHANGELOG\.md is not empty/,
  );
  assert.deepStrictEqual(changes.evaluateGate({ ...input, next: '2.2.1-alpha.0', bump: 'alpha', changelog: stray }).refusals, []);
  assert.deepStrictEqual(changes.evaluateGate({ ...input, changelog: '# Changelog\n\n## [Unreleased]\n\n## [2.2.0] (x)\n' }).refusals, []);
  assert.strictEqual(
    changes.unreleasedProblem('# Changelog\n'),
    'CHANGELOG.md has no "## [Unreleased]" heading to insert the release under.',
  );
});

test('minimumBump lists every reason, highest first', () => {
  const floor = changes.minimumBump([frag('fixed', {}, 'a.yaml'), frag('added', {}, 'b.yaml')], {
    hard: [hardFinding('write_failure')],
    additive: [additiveFinding('--target-ref')],
    review: [],
  });
  assert.strictEqual(floor.level, 'major');
  assert.deepStrictEqual(
    floor.reasons.map((reason) => reason.level),
    ['major', 'minor', 'minor', 'patch'],
  );
  assert.strictEqual(changes.minimumBump([frag('lead')], null).level, 'none');
});

// --- Rendering ---

function fixtureFragments() {
  const dir = path.join(FIXTURES, 'fragments');
  return fs
    .readdirSync(dir)
    .sort()
    .map((name) => changes.parseFragment(`changes/${name}`, fs.readFileSync(path.join(dir, name), 'utf8')));
}

function fixtureBlock() {
  return changes.renderBlock({ version: '3.0.0', baseTag: 'v2.2.0', date: '2026-10-01', fragments: fixtureFragments(), repoUrl: REPO });
}

test('golden render: the fixture fragments give the expected block', () => {
  assert.strictEqual(fixtureBlock(), fs.readFileSync(path.join(FIXTURES, 'golden-block.md'), 'utf8'));
});

test('render: heading shape, section order, migration under each breaking change', () => {
  const block = fixtureBlock();
  assert.match(
    block,
    /^## \[3\.0\.0]\(https:\/\/github\.com\/armelhbobdad\/bmad-module-skill-forge\/compare\/v2\.2\.0\.\.\.v3\.0\.0\) \(2026-10-01\)\n\nSKF 3\.0\.0 runs/,
  );
  const order = ['### Breaking changes', '### Added', '### Changed', '### Fixed', '### Documentation'].map((heading) =>
    block.indexOf(heading),
  );
  assert.ok(
    order.every((index, i) => index > 0 && (i === 0 || index > order[i - 1])),
    `section order ${order}`,
  );
  assert.strictEqual((block.match(/\n {2}\*\*Migration:\*\* /g) || []).length, 2);
  assert.match(block, /\(\[#509]\(https:\/\/github\.com\/armelhbobdad\/bmad-module-skill-forge\/pull\/509\); issue \[#502]\(/);
  assert.match(block, /; issues \[#495]\([^)]+\), \[#497]/);
  assert.match(block, /\n- The published docs were checked/, 'a docs fragment with no scope has no bold scope');
  assert.ok(!block.includes('\n\n\n'), 'no double blank lines');
});

test('CHANGELOG.md: the block goes under an empty [Unreleased] and older history stays byte-identical', () => {
  const original = fs.readFileSync(path.join(ROOT, 'CHANGELOG.md'), 'utf8');
  const block = fixtureBlock();
  const updated = changes.insertIntoChangelog(original, block, '3.0.0');
  const firstRelease = original.search(/^## \[\d/m);
  const history = original.slice(firstRelease);
  const unreleasedEnd = original.indexOf('## [Unreleased]') + '## [Unreleased]'.length;
  assert.ok(updated.endsWith(history), 'every older release is byte-identical');
  assert.strictEqual(updated.slice(0, unreleasedEnd), original.slice(0, unreleasedEnd), 'the title and preamble are unchanged');
  assert.strictEqual(
    updated.slice(unreleasedEnd),
    `\n\n${block}\n${history}`,
    'the block sits between [Unreleased] and the previous release',
  );
  assert.throws(() => changes.insertIntoChangelog(updated, block, '3.0.0'), /already has a ## \[3\.0\.0] section/);
});

test('CHANGELOG.md: a non-empty or missing [Unreleased] is refused', () => {
  const block = fixtureBlock();
  assert.throws(
    () => changes.insertIntoChangelog('# Changelog\n\n## [Unreleased]\n\n- stray note\n\n## [1.0.0] (x)\n', block, '3.0.0'),
    /is not empty/,
  );
  assert.throws(() => changes.insertIntoChangelog('# Changelog\n\n## [1.0.0] (x)\n', block, '3.0.0'), /no "## \[Unreleased]" heading/);
  assert.strictEqual(
    changes.insertIntoChangelog('# Changelog\n\n## [Unreleased]\n', 'B\n', '1.0.0'),
    '# Changelog\n\n## [Unreleased]\n\nB\n',
  );
});

test('renderNotes: install line and compare link, with the version for a prerelease', () => {
  const stable = changes.renderNotes({
    block: fixtureBlock(),
    version: '3.0.0',
    baseTag: 'v2.2.0',
    repoUrl: REPO,
    packageName: 'bmad-module-skill-forge',
  });
  assert.match(stable, /\n## Installation\n\n```bash\nnpx bmad-module-skill-forge install\n```\n/);
  assert.ok(stable.endsWith(`**Full Changelog**: <${REPO}/compare/v2.2.0...v3.0.0>\n`));
  const pre = changes.renderNotes({
    block: 'B\n',
    version: '3.0.0-rc.1',
    baseTag: 'v2.2.0',
    repoUrl: REPO,
    packageName: 'bmad-module-skill-forge',
  });
  assert.match(pre, /npx bmad-module-skill-forge@3\.0\.0-rc\.1 install/);
  assert.match(pre, /compare\/v2\.2\.0\.\.\.v3\.0\.0-rc\.1>/);
});

test('renderReview: checklist, reasons, surfaces and the notes one heading level down', () => {
  const result = gate({ bump: 'major', fragments: [breakingNamed()], hard: ['write_failure'] });
  const review = changes.renderReview({
    version: '3.0.0',
    baseTag: 'v2.2.0',
    gate: result,
    surfaces: { hard: [hardFinding('write_failure')], additive: [], review: [{ text: 'skf-setup: flag `--quiet` text changed' }] },
    block: fixtureBlock(),
  });
  assert.match(review, /^## Review before approving\n/);
  assert.match(review, /v3\.0\.0 is a major step from v2\.2\.0; .* at least major\./);
  assert.match(review, /- \[ ] each breaking change says what stopped working/);
  assert.match(review, /### Why the minimum is major\n\n- major: breaking fragment/);
  assert.match(review, /Hard \(a breaking fragment names each one\):\n\n- skf-setup: schema enum value `write_failure` removed/);
  assert.match(review, /Additive:\n\n- none/);
  assert.match(review, /- skf-setup: flag `--quiet` text changed/);
  assert.match(review, /\n### \[3\.0\.0]\(/);
  assert.match(review, /\n#### Breaking changes\n/);
});

test('renderReview: a text too long for a pull request body is cut', () => {
  const many = Array.from({ length: 3000 }, (_, i) => ({ text: `shared: halt_reason value \`reason-${i}\` added` }));
  const review = changes.renderReview({
    version: '3.0.0',
    baseTag: 'v2.2.0',
    gate: gate({ bump: 'major', fragments: [breakingNamed()] }),
    surfaces: { hard: [], additive: [], review: many },
    block: fixtureBlock(),
  });
  assert.ok(review.length < 61_000, `${review.length} characters`);
  assert.match(review, /Cut to fit a pull request body/);
});

// --- The commands against throwaway repositories ---

test('check: exit 0 on valid fragments, 1 with the file and the problem otherwise', () => {
  const root = makeRepo();
  write(root, { 'changes/new-flag.yaml': 'type: added\nscope: skf-tool\nsummary: New `--all` flag.\n' });
  const ok = runTool(CHANGES_TOOL, ['check', '--root', root]);
  assert.strictEqual(ok.status, 0, ok.out);
  assert.match(ok.out, /2 change fragment\(s\) valid/);
  write(root, { 'changes/broken.yaml': 'type: breaking\nscope: skf-tool\nsummary: Gone.\n', 'changes/stray.txt': 'x' });
  const bad = runTool(CHANGES_TOOL, ['check', '--root', root]);
  assert.strictEqual(bad.status, 1, bad.out);
  assert.match(bad.out, /changes\/broken\.yaml: a breaking change needs a migration/);
  assert.match(bad.out, /changes\/stray\.txt: not a fragment/);
});

test('check annotates each problem in GitHub Actions', () => {
  const root = makeRepo();
  write(root, { 'changes/broken.yaml': 'type: fixed\nsummary: No scope.\n' });
  const { status, out } = runTool(CHANGES_TOOL, ['check', '--root', root], { GITHUB_ACTIONS: 'true' });
  assert.strictEqual(status, 1, out);
  assert.match(out, /::error file=changes\/broken\.yaml::scope is required/);
});

test('gate: a fragment present at the last stable tag is not selected again', () => {
  const root = makeRepo();
  write(root, { 'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n' });
  commitAll(root, 'fix');
  const { status, out } = runTool(CHANGES_TOOL, ['gate', '--bump', 'patch', '--root', root]);
  assert.strictEqual(status, 0, out);
  assert.match(out, /Change fragments since then: 1\n/);
  assert.match(out, /patch: 1\.0\.0 -> 1\.0\.1/);
});

test('gate: a removed schema enum value needs major and a breaking fragment that names it', () => {
  const root = makeRepo();
  write(root, {
    'src/shared/scripts/schemas/skf-tool-result-envelope.v1.json': TEMP_SCHEMA.replace('"write_failure",', ''),
    'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n',
  });
  const minor = runTool(CHANGES_TOOL, ['gate', '--bump', 'minor', '--root', root]);
  assert.strictEqual(minor.status, 1, minor.out);
  assert.match(minor.out, /skf-tool: schema enum value `write_failure` removed/);
  assert.match(minor.out, /below the minimum major/);
  assert.match(minor.out, /Nothing was committed/);
  write(root, {
    'changes/drop-status.yaml':
      'type: breaking\nscope: skf-tool\nsummary: The `write_failure` status is gone.\nmigration: Branch on `blocked`.\n',
  });
  const major = runTool(CHANGES_TOOL, ['gate', '--bump', 'major', '--root', root]);
  assert.strictEqual(major.status, 0, major.out);
  assert.match(major.out, /The release gate passes/);
});

test('gate: annotations and a step summary in GitHub Actions', () => {
  const root = makeRepo();
  const summaryFile = path.join(root, 'summary.md');
  const { status, out } = runTool(CHANGES_TOOL, ['gate', '--bump', 'patch', '--root', root, '--base', 'v1.0.0'], {
    GITHUB_ACTIONS: 'true',
    GITHUB_STEP_SUMMARY: summaryFile,
  });
  assert.strictEqual(status, 1, out);
  assert.match(out, /::error::a stable release needs at least one change fragment/);
  assert.match(fs.readFileSync(summaryFile, 'utf8'), /### Release gate[\s\S]*\*\*Refused:\*\*/);
});

test('gate and preview: usage errors exit 2', () => {
  const root = makeRepo();
  assert.strictEqual(runTool(CHANGES_TOOL, ['gate', '--root', root]).status, 2);
  assert.strictEqual(runTool(CHANGES_TOOL, ['gate', '--bump', 'huge', '--root', root]).status, 2);
  assert.strictEqual(runTool(CHANGES_TOOL, ['preview', '--base', 'v9.9.9', '--root', root]).status, 2);
  assert.strictEqual(runTool(CHANGES_TOOL, ['launch', '--root', root]).status, 2);
  assert.strictEqual(runTool(CHANGES_TOOL, []).status, 2);
});

test('no stable tag: CI exits 2, a local run selects every fragment and says so', () => {
  const root = makeRepo({ tag: false });
  write(root, { 'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n' });
  const ci = runTool(CHANGES_TOOL, ['gate', '--bump', 'major', '--root', root], { CI: 'true' });
  assert.strictEqual(ci.status, 2, ci.out);
  assert.match(ci.out, /no stable release tag found/);
  const local = runTool(CHANGES_TOOL, ['gate', '--bump', 'major', '--root', root]);
  assert.strictEqual(local.status, 0, local.out);
  assert.match(local.out, /warning: No stable release tag found/);
  assert.match(local.out, /Change fragments since then: 2/);
});

test('preview: fragments, surfaces, minimum bump, next version, gate verdict and the block', () => {
  const root = makeRepo();
  write(root, {
    'src/skf-tool/SKILL.md':
      '# Tool\n\n| **Flags** | `--headless` / `-H` (skip prompts); `--dry-run` (write nothing); `--all` (every skill) |\n',
    'changes/all-flag.yaml': 'type: added\nscope: skf-tool\nsummary: New `--all` flag.\nprs: [12]\n',
  });
  const { status, out } = runTool(CHANGES_TOOL, ['preview', '--root', root]);
  assert.strictEqual(status, 0, out);
  assert.match(out, /Change fragments added since v1\.0\.0: 1\n {2}added {5}changes\/all-flag\.yaml {2}skf-tool/);
  assert.match(out, /additive: 1\n {4}- skf-tool: flag `--all` added/);
  assert.match(out, /Minimum bump: minor/);
  assert.match(out, /Next version: 1\.0\.0 -> 1\.1\.0 \(--bump minor/);
  assert.match(out, /Gate: passes\./);
  assert.match(out, /## \[1\.1\.0]\(https:\/\/github\.com\/example\/tool\/compare\/v1\.0\.0\.\.\.v1\.1\.0\)/);
  const patch = runTool(CHANGES_TOOL, ['preview', '--bump', 'patch', '--root', root]);
  assert.strictEqual(patch.status, 0, patch.out);
  assert.match(patch.out, /Gate: refuses this bump:\n {2}- patch gives 1\.0\.1/);
  write(root, { 'changes/bad.yaml': 'type: nope\n' });
  assert.strictEqual(runTool(CHANGES_TOOL, ['preview', '--root', root]).status, 1);
});

test('release: a stable release writes CHANGELOG.md, the notes and the review, leaving history intact', () => {
  const root = makeRepo({ version: '1.1.0' });
  write(root, { 'changes/all-flag.yaml': 'type: added\nscope: skf-tool\nsummary: New `--all` flag.\n' });
  const { status, out } = runTool(CHANGES_TOOL, ['release', '--root', root, '--date', '2026-10-01', '--review', 'release_review.md']);
  assert.strictEqual(status, 0, out);
  const changelog = fs.readFileSync(path.join(root, 'CHANGELOG.md'), 'utf8');
  const history = TEMP_CHANGELOG.slice(TEMP_CHANGELOG.indexOf('## [1.0.0]'));
  assert.ok(changelog.endsWith(history), changelog);
  assert.match(
    changelog,
    /## \[Unreleased]\n\n## \[1\.1\.0]\(https:\/\/github\.com\/example\/tool\/compare\/v1\.0\.0\.\.\.v1\.1\.0\) \(2026-10-01\)\n\n### Added\n\n- \*\*skf-tool:\*\* New `--all` flag\.\n\n## \[1\.0\.0]/,
  );
  const notes = fs.readFileSync(path.join(root, 'release_notes.md'), 'utf8');
  assert.match(notes, /^## \[1\.1\.0][\s\S]*## Installation[\s\S]*npx example-tool install/);
  assert.match(fs.readFileSync(path.join(root, 'release_review.md'), 'utf8'), /^## Review before approving/);
  const again = runTool(CHANGES_TOOL, ['release', '--root', root]);
  assert.strictEqual(again.status, 1, again.out);
  assert.match(again.out, /already has a ## \[1\.1\.0] section/);
});

test('release: a prerelease writes only the notes', () => {
  const root = makeRepo({ version: '1.1.0-rc.1' });
  write(root, { 'changes/all-flag.yaml': 'type: added\nscope: skf-tool\nsummary: New `--all` flag.\n' });
  const { status, out } = runTool(CHANGES_TOOL, ['release', '--root', root, '--notes', 'notes.md']);
  assert.strictEqual(status, 0, out);
  assert.strictEqual(fs.readFileSync(path.join(root, 'CHANGELOG.md'), 'utf8'), TEMP_CHANGELOG);
  assert.match(fs.readFileSync(path.join(root, 'notes.md'), 'utf8'), /^## \[1\.1\.0-rc\.1][\s\S]*npx example-tool@1\.1\.0-rc\.1 install/);
  assert.match(out, /A prerelease leaves CHANGELOG\.md alone/);
});

test('release: refuses what the gate refuses, and a non-empty [Unreleased]', () => {
  const root = makeRepo({ version: '1.0.1' });
  const empty = runTool(CHANGES_TOOL, ['release', '--root', root]);
  assert.strictEqual(empty.status, 1, empty.out);
  assert.match(empty.out, /at least one change fragment/);
  write(root, {
    'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n',
    'CHANGELOG.md': TEMP_CHANGELOG.replace('## [Unreleased]\n', '## [Unreleased]\n\n- hand-written note\n'),
  });
  const stray = runTool(CHANGES_TOOL, ['release', '--root', root]);
  assert.strictEqual(stray.status, 1, stray.out);
  assert.match(stray.out, /is not empty/);
  assert.ok(!fs.existsSync(path.join(root, 'release_notes.md')), 'nothing is written when the CHANGELOG.md insert fails');
});

test('a released fragment rewritten in place is refused by check, preview and the gate, not skipped', () => {
  const root = makeRepo();
  write(root, {
    'changes/released-before.yaml': 'type: breaking\nscope: skf-tool\nsummary: `--dry-run` is gone.\nmigration: Drop it.\n',
    'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n',
  });
  const refusal = /changes\/released-before\.yaml: is in v1\.0\.0, so it was already released, and it has changed since/;
  const gateRun = runTool(CHANGES_TOOL, ['gate', '--bump', 'patch', '--root', root]);
  assert.strictEqual(gateRun.status, 1, gateRun.out);
  assert.match(gateRun.out, refusal);
  assert.match(gateRun.out, /git checkout v1\.0\.0 -- changes\/released-before\.yaml/);
  const check = runTool(CHANGES_TOOL, ['check', '--root', root]);
  assert.strictEqual(check.status, 1, check.out);
  assert.match(check.out, refusal);
  const preview = runTool(CHANGES_TOOL, ['preview', '--bump', 'patch', '--root', root]);
  assert.strictEqual(preview.status, 1, preview.out);
  assert.match(preview.out, /Change fragments added since v1\.0\.0: 1\n/);
  assert.match(preview.out, /Files in changes\/ to fix \(never rendered\):\n {2}changes\/released-before\.yaml: is in v1\.0\.0/);
});

test('a released fragment renamed or copied is refused, not selected again', () => {
  const root = makeRepo();
  git(root, ['mv', 'changes/released-before.yaml', 'changes/renamed-before.yaml']);
  write(root, { 'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n' });
  const { status, out } = runTool(CHANGES_TOOL, ['gate', '--bump', 'patch', '--root', root]);
  assert.strictEqual(status, 1, out);
  assert.match(
    out,
    /changes\/renamed-before\.yaml: has the same content as changes\/released-before\.yaml, which v1\.0\.0 already released/,
  );
  assert.doesNotMatch(out, /minimum major/, 'the old breaking change does not set the minimum again');
  assert.match(out, /Change fragments since then: 1\n/);
  git(root, ['mv', 'changes/renamed-before.yaml', 'changes/released-before.yaml']);
  write(root, { 'changes/copy-of-before.yaml': fs.readFileSync(path.join(root, 'changes/released-before.yaml'), 'utf8') });
  const copy = runTool(CHANGES_TOOL, ['check', '--root', root]);
  assert.strictEqual(copy.status, 1, copy.out);
  assert.match(copy.out, /changes\/copy-of-before\.yaml: has the same content as changes\/released-before\.yaml/);
});

test('preview and the gate report a file in changes/ that is not a fragment', () => {
  const root = makeRepo();
  write(root, {
    'changes/small-fix.yml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n',
    'changes/other.yaml': 'type: fixed\nscope: x\nsummary: y\n',
  });
  const preview = runTool(CHANGES_TOOL, ['preview', '--root', root]);
  assert.strictEqual(preview.status, 1, preview.out);
  assert.match(preview.out, /Files in changes\/ to fix \(never rendered\):\n {2}changes\/small-fix\.yml: not a fragment/);
  const gateRun = runTool(CHANGES_TOOL, ['gate', '--bump', 'patch', '--root', root]);
  assert.strictEqual(gateRun.status, 1, gateRun.out);
  assert.match(gateRun.out, /- changes\/small-fix\.yml: not a fragment/);
});

test('gate and check: a stable release needs an empty [Unreleased]; a prerelease does not', () => {
  const root = makeRepo();
  write(root, {
    'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n',
    'CHANGELOG.md': TEMP_CHANGELOG.replace('## [Unreleased]\n', '## [Unreleased]\n\n- a stray note\n'),
  });
  const stable = runTool(CHANGES_TOOL, ['gate', '--bump', 'patch', '--root', root]);
  assert.strictEqual(stable.status, 1, stable.out);
  assert.match(stable.out, /"## \[Unreleased]" in CHANGELOG\.md is not empty/);
  const pre = runTool(CHANGES_TOOL, ['gate', '--bump', 'alpha', '--root', root]);
  assert.strictEqual(pre.status, 0, pre.out);
  const check = runTool(CHANGES_TOOL, ['check', '--root', root]);
  assert.strictEqual(check.status, 1, check.out);
  assert.match(check.out, /CHANGELOG\.md: "## \[Unreleased]" in CHANGELOG\.md is not empty/);
});

test('lastStableTag takes only version tags: `stable` and prerelease tags are skipped', () => {
  const root = makeRepo();
  write(root, { 'changes/small-fix.yaml': 'type: fixed\nscope: skf-tool\nsummary: A fix.\n' });
  commitAll(root, 'fix');
  git(root, ['tag', '-a', 'stable', '-m', 'stable']);
  git(root, ['tag', '-a', 'v1.1.0-rc.0', '-m', 'v1.1.0-rc.0']);
  assert.strictEqual(surfaces.lastStableTag(root), 'v1.0.0');
});

// --- The pr command: the fragments one branch needs ---

const SKILL_WITH_ALL =
  '# Tool\n\n| Aspect | Detail |\n|---|---|\n| **Flags** | `--headless` / `-H` (skip prompts); `--dry-run` (write nothing); `--all` (every skill) |\n';
const SCHEMA_WITHOUT_WRITE_FAILURE = TEMP_SCHEMA.replace('"write_failure",', '');
const DROP_STATUS = 'type: breaking\nscope: skf-tool\nsummary: The `write_failure` status is gone.\nmigration: Branch on `blocked`.\n';
const ALL_FLAG = 'type: added\nscope: skf-tool\nsummary: New `--all` flag.\n';
const SMALL_FIX = 'type: fixed\nscope: skf-tool\nsummary: A fix.\n';

/**
 * makeRepo()'s repository with a branch off main, and `files` committed on
 * it with `message`.
 */
function makeBranch(files = {}, { message = 'change', name = 'feat/topic', repo = {} } = {}) {
  const root = makeRepo(repo);
  git(root, ['checkout', '-q', '-b', name]);
  if (Object.keys(files).length > 0) {
    write(root, files);
    commitAll(root, message);
  }
  return root;
}

function runPr(root, env = {}, args = ['--base', 'main']) {
  return runTool(CHANGES_TOOL, ['pr', '--root', root, ...args], env);
}

/** The fragment template a failed run prints, parsed. */
function printedTemplate(out) {
  const match = /```yaml\n([\s\S]*?)```/.exec(out);
  assert.ok(match, `no fragment template in:\n${out}`);
  return { ...changes.parseFragment('changes/template.yaml', match[1]), text: match[1] };
}

/**
 * A template fails only on the sentences it marks for rewriting, and is a
 * valid fragment once they are rewritten.
 */
function assertOnlyTemplateText(template, context) {
  assert.ok(template.errors.length > 0, `the template text is accepted as it is:\n${context}`);
  for (const error of template.errors) assert.match(error, /still holds the template text/, context);
  const rewritten = template.text.replaceAll(/Rewrite this paragraph:[^\n]*/g, 'Done.');
  assert.deepStrictEqual(changes.parseFragment('changes/template.yaml', rewritten).errors, [], context);
}

test('isShipped: src/, tools/cli/, the npx wrapper and .npmignore, nothing else', () => {
  for (const file of ['src/skf-setup/SKILL.md', 'src/module.yaml', 'tools/cli/skf-cli.js', 'tools/skf-npx-wrapper.js', '.npmignore']) {
    assert.strictEqual(changes.isShipped(file), true, file);
  }
  for (const file of [
    'tools/changes.js',
    'tools/cli.js',
    'test/test-changes.js',
    'docs/index.md',
    'changes/a.yaml',
    'srcx/a',
    'a/.npmignore',
  ]) {
    assert.strictEqual(changes.isShipped(file), false, file);
  }
});

test('changelogTrailers: "Changelog: none (<reason>)" covers; no reason, the placeholder or another value does not', () => {
  const { waivers, malformed } = changes.changelogTrailers([
    { commit: 'aaaa1111', message: 'fix: reword\n\nChangelog: none (wording only, nothing a user sees)\nCo-Authored-By: x\n' },
    { commit: 'bbbb2222', message: 'fix: x\n\n  changelog:NONE (tests (and CI) only)\n' },
    { commit: 'cccc3333', message: 'fix: y\n\nChangelog: none\nChangelog: none ( )\nChangelog: skip (why)\n' },
    { commit: 'dddd4444', message: 'The Changelog: none line is described here.\n' },
    { commit: 'eeee5555', message: 'fix: z\n\nChangelog: none (<reason>)\nChangelog: none ( <why> )\n' },
  ]);
  assert.deepStrictEqual(waivers, [
    { commit: 'aaaa1111', reason: 'wording only, nothing a user sees' },
    { commit: 'bbbb2222', reason: 'tests (and CI) only' },
  ]);
  assert.deepStrictEqual(
    malformed.map(({ commit, line }) => `${commit} ${line}`),
    [
      'cccc3333 Changelog: none',
      'cccc3333 Changelog: none ( )',
      'cccc3333 Changelog: skip (why)',
      'eeee5555 Changelog: none (<reason>)',
      'eeee5555 Changelog: none ( <why> )',
    ],
  );
});

test('evaluatePullRequest: what counts as a fragment for a shipped change and for each surface change', () => {
  const touched = ['src/skf-setup/SKILL.md'];
  const waiver = { waivers: [{ commit: 'aaaa1111', reason: 'x' }], malformed: [] };
  const found = { hard: [hardFinding('write_failure')], additive: [additiveFinding('--target-ref')], review: [] };
  const run = (input) => changes.evaluatePullRequest({ touched, fragments: [], ...input });
  assert.deepStrictEqual(run({ touched: [] }).failures, [], 'nothing shipped, nothing needed');
  assert.strictEqual(run({}).missing.fragment, true);
  assert.strictEqual(run({ fragments: [frag('lead')] }).missing.fragment, true, 'a lead is not a change');
  assert.strictEqual(run({ fragments: [frag('docs')] }).missing.fragment, false);
  assert.strictEqual(run({ trailers: waiver }).missing.fragment, false);
  const waived = run({ trailers: waiver, surfaces: found });
  assert.deepStrictEqual(tokens(waived.missing.hard), ['write_failure'], 'the trailer never covers a removal');
  assert.deepStrictEqual(tokens(waived.missing.additive), ['--target-ref'], 'nor an addition');
  assert.match(waived.failures.join('\n'), /never covers a surface change/);
  const changed = run({ fragments: [frag('changed', { summary: 'About `--target-ref`.' })], surfaces: found });
  assert.deepStrictEqual(tokens(changed.missing.additive), ['--target-ref'], 'a changed fragment does not cover an addition');
  const covered = run({ fragments: [breakingNamed()], surfaces: found });
  assert.deepStrictEqual(covered.failures, [], 'a breaking fragment names the removal and covers the addition');
  assert.strictEqual(covered.template, null);
  const invalid = run({ fragments: [{ ...frag('fixed'), errors: ['scope is required'] }] });
  assert.strictEqual(invalid.missing.fragment, false, 'an invalid fragment is reported for its errors, not as missing');
  assert.match(invalid.failures.join('\n'), /: scope is required/);
});

test('evaluatePullRequest: an unreleased fragment the branch edits counts only where it names the item', () => {
  const touched = ['src/skf-setup/SKILL.md'];
  const found = { hard: [hardFinding('write_failure')], additive: [additiveFinding('--target-ref')], review: [] };
  const edited = (fragment) => ({ ...fragment, status: 'M' });
  const run = (input) => changes.evaluatePullRequest({ touched, fragments: [], ...input });
  const fix = run({ fragments: [edited(frag('fixed', {}, 'pending.yaml'))] });
  assert.strictEqual(fix.missing.fragment, true, 'an edited fragment does not stand in for a fragment of its own');
  assert.match(fix.failures.join('\n'), /Editing an unreleased fragment \(changes\/pending\.yaml\) does not count here/);
  assert.strictEqual(run({ fragments: [{ ...frag('fixed'), status: 'A' }] }).missing.fragment, false, 'an added one does');
  const other = run({ fragments: [edited(frag('added', { summary: 'New `--all` flag.' }, 'other.yaml'))], surfaces: found });
  assert.deepStrictEqual(tokens(other.missing.additive), ['--target-ref'], 'an edited added fragment covers only what it names');
  assert.strictEqual(other.missing.fragment, true);
  assert.match(other.failures.join('\n'), /or name `--target-ref` in backticks in changes\/other\.yaml, which it edits/);
  const names = run({
    fragments: [
      edited(frag('added', { summary: 'New `--target-ref` flag.' })),
      edited(frag('breaking', { summary: 'The `write_failure` status is gone.' })),
    ],
    surfaces: found,
  });
  assert.deepStrictEqual(names.failures, [], 'edited fragments that name the removal and the addition cover them');
  const hardOnly = run({ fragments: [edited(breakingNamed())], surfaces: { ...found, additive: [] } });
  assert.deepStrictEqual(hardOnly.failures, [], 'a follow-up that names its removal in a pending breaking fragment passes');
});

test('fragmentTemplate: typed and scoped from the surface changes, else from the files; it fails only on the text to rewrite', () => {
  const parse = (input) => {
    const text = changes.fragmentTemplate(input);
    return { ...changes.parseFragment('changes/t.yaml', text), text };
  };
  const cases = [
    [{ touched: ['src/skf-tool/SKILL.md', 'src/skf-tool/references/a.md'] }, 'fixed', 'skf-tool'],
    [{ touched: ['src/shared/references/x.md', 'src/skf-tool/SKILL.md'] }, 'fixed', 'all workflows'],
    [{ touched: ['tools/cli/skf-cli.js', '.npmignore'] }, 'fixed', 'installer, packaging'],
    [{ touched: ['src/forger/preferences.yaml'] }, 'fixed', 'skf-forger'],
    [{ touched: ['src/skf-a/x.md', 'src/skf-b/x.md', 'src/skf-c/x.md', 'src/skf-d/x.md'] }, 'fixed', 'all workflows'],
    [{ additive: [additiveFinding('--target-ref')], touched: ['src/skf-tool/SKILL.md'] }, 'added', 'skf-update-skill'],
    [{ hard: [hardFinding('write_failure')], additive: [additiveFinding('--all')] }, 'breaking', 'skf-setup, skf-update-skill'],
  ];
  for (const [input, type, scope] of cases) {
    const parsed = parse(input);
    assertOnlyTemplateText(parsed, JSON.stringify(input));
    assert.strictEqual(parsed.data.type, type, JSON.stringify(input));
    assert.strictEqual(parsed.data.scope, scope, JSON.stringify(input));
  }
  const breaking = parse({ hard: [hardFinding('write_failure')], additive: [additiveFinding('--all')] });
  assert.strictEqual(changes.namesToken(breaking, 'write_failure'), true, 'the breaking template names the removed item');
  assert.match(breaking.data.summary, /Adds the flag `--all`/);
  assert.match(parse({ additive: [additiveFinding('--target-ref')] }).data.summary, /^New flag `--target-ref`\./);
});

test('pr: a branch that changes nothing the package ships passes with no fragment', () => {
  const root = makeBranch({
    'docs/guide.md': '# Guide\n',
    'test/test-tool.js': '// a test\n',
    'tools/validate-thing.js': '// a maintainer tool\n',
    '.github/workflows/quality.yaml': 'name: Quality\n',
  });
  const summaryFile = path.join(root, 'summary.md');
  const { status, out } = runPr(root, { GITHUB_STEP_SUMMARY: summaryFile });
  assert.strictEqual(status, 0, out);
  assert.match(out, /Branch: main \(merge base [0-9a-f]{8}\) -> HEAD\nFiles changed in the code the package ships: 0\n/);
  assert.match(out, /Covered surfaces: not compared/);
  assert.match(out, /The branch has the change fragments it needs\./);
  assert.match(fs.readFileSync(summaryFile, 'utf8'), /\*\*Passes\.\*\*[\s\S]*Covered surfaces: not compared/);
});

test('pr: a change under src/, tools/cli/, the npx wrapper or .npmignore fails with no fragment, and prints one to fill in', () => {
  const root = makeBranch({ 'src/skf-tool/references/step-01.md': 'A new step.\n' });
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /changes the code the package ships \(src\/skf-tool\/references\/step-01\.md\) and adds no change fragment/);
  assert.match(out, /add a `Changelog: none \(<reason>\)` line to one of its commit messages/);
  assert.match(out, /A fragment to fill in; save it as changes\/topic\.yaml:/);
  const template = printedTemplate(out);
  assertOnlyTemplateText(template, out);
  assert.deepStrictEqual([template.data.type, template.data.scope], ['fixed', 'skf-tool']);
  for (const file of ['tools/cli/skf-cli.js', 'tools/skf-npx-wrapper.js', '.npmignore']) {
    const other = runPr(makeBranch({ [file]: 'x\n' }));
    assert.strictEqual(other.status, 1, other.out);
    assert.match(other.out, /adds no change fragment/, file);
    assertOnlyTemplateText(printedTemplate(other.out), file);
  }
});

test('pr: a Changelog: none (<reason>) line passes a change under src/; one with no reason does not', () => {
  const change = { 'src/skf-tool/references/step-01.md': 'Reworded.\n' };
  const ok = runPr(makeBranch(change, { message: 'fix(skf-tool): reword\n\nChangelog: none (wording only)' }));
  assert.strictEqual(ok.status, 0, ok.out);
  assert.match(ok.out, /Changelog: none lines: 1\n {2}commit [0-9a-f]{8}: wording only\n/);
  const empty = runPr(makeBranch(change, { message: 'fix(skf-tool): reword\n\nChangelog: none ()' }));
  assert.strictEqual(empty.status, 1, empty.out);
  assert.match(empty.out, /"Changelog: none \(\)" covers nothing: write `Changelog: none \(<reason>\)`/);
});

test('pr: the Changelog line never covers a removed covered item, and the template is a breaking fragment that names it', () => {
  const root = makeBranch(
    { 'src/shared/scripts/schemas/skf-tool-result-envelope.v1.json': SCHEMA_WITHOUT_WRITE_FAILURE },
    { message: 'refactor: drop a status\n\nChangelog: none (never emitted)' },
  );
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.doesNotMatch(out, /adds no change fragment/, 'the line covers the shipped change itself');
  assert.match(
    out,
    /schema enum value `write_failure` removed .*, and no breaking fragment on this branch names `write_failure` in backticks/,
  );
  assert.match(out, /never covers a surface change/);
  const template = printedTemplate(out);
  assertOnlyTemplateText(template, out);
  assert.strictEqual(template.data.type, 'breaking');
  assert.strictEqual(changes.namesToken(template, 'write_failure'), true);
});

test('pr: the Changelog line never covers an added covered item, and the template is an added fragment', () => {
  const root = makeBranch({ 'src/skf-tool/SKILL.md': SKILL_WITH_ALL }, { message: 'feat: all\n\nChangelog: none (internal)' });
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /skf-tool: flag `--all` added {2}\[NOT COVERED by an added or breaking fragment on this branch]/);
  assert.match(out, /flag `--all` added, and no added or breaking fragment on this branch covers it/);
  const template = printedTemplate(out);
  assertOnlyTemplateText(template, out);
  assert.deepStrictEqual([template.data.type, template.data.scope], ['added', 'skf-tool']);
  assert.match(template.data.summary, /`--all`/);
});

test('pr: a breaking fragment that names the removed item passes; one that does not fails and is named', () => {
  const schema = { 'src/shared/scripts/schemas/skf-tool-result-envelope.v1.json': SCHEMA_WITHOUT_WRITE_FAILURE };
  const ok = runPr(makeBranch({ ...schema, 'changes/drop-status.yaml': DROP_STATUS }));
  assert.strictEqual(ok.status, 0, ok.out);
  assert.match(ok.out, /`write_failure` removed .* {2}\[named in changes\/drop-status\.yaml]/);
  const unnamed = DROP_STATUS.replace('The `write_failure` status', 'The write_failure status');
  const bad = runPr(makeBranch({ ...schema, 'changes/drop-status.yaml': unnamed }));
  assert.strictEqual(bad.status, 1, bad.out);
  assert.match(bad.out, /names `write_failure` in backticks: name it in changes\/drop-status\.yaml, or add a breaking fragment/);
});

test('pr: an added fragment covers an addition; a fixed one does not', () => {
  const ok = runPr(makeBranch({ 'src/skf-tool/SKILL.md': SKILL_WITH_ALL, 'changes/all-flag.yaml': ALL_FLAG }));
  assert.strictEqual(ok.status, 0, ok.out);
  assert.match(ok.out, /flag `--all` added {2}\[covered by changes\/all-flag\.yaml]/);
  const fixed = runPr(makeBranch({ 'src/skf-tool/SKILL.md': SKILL_WITH_ALL, 'changes/all-flag.yaml': SMALL_FIX }));
  assert.strictEqual(fixed.status, 1, fixed.out);
  assert.doesNotMatch(fixed.out, /adds no change fragment/);
  assert.match(fixed.out, /flag `--all` added, and no added or breaking fragment on this branch covers it/);
  assert.strictEqual(printedTemplate(fixed.out).data.type, 'added');
});

test('pr: the release branch (release/bot/*) of this repository passes with a note; from a fork or an unknown repository it is checked', () => {
  const root = makeBranch({ 'src/skf-tool/references/step-01.md': 'x\n' }, { name: 'release/bot/v1.0.1-42' });
  const head = 'release/bot/v1.0.1-42';
  const summaryFile = path.join(root, 'summary.md');
  const bot = runPr(root, {
    GITHUB_HEAD_REF: head,
    PR_HEAD_REPO: 'example/tool',
    GITHUB_REPOSITORY: 'example/tool',
    GITHUB_STEP_SUMMARY: summaryFile,
  });
  assert.strictEqual(bot.status, 0, bot.out);
  assert.match(bot.out, /release\/bot\/v1\.0\.1-42 is the release branch of release\.yaml/);
  assert.match(fs.readFileSync(summaryFile, 'utf8'), /### Change fragments for this pull request\n\n\*\*Passes\.\*\* /);
  const fork = runPr(root, { GITHUB_HEAD_REF: head, PR_HEAD_REPO: 'someone/tool', GITHUB_REPOSITORY: 'example/tool' });
  assert.strictEqual(fork.status, 1, fork.out);
  assert.match(fork.out, /comes from someone\/tool, not example\/tool, so it is checked like any other branch/);
  assert.match(fork.out, /adds no change fragment/);
  const unknown = [
    [{ PR_HEAD_REPO: '', GITHUB_REPOSITORY: 'example/tool' }, /PR_HEAD_REPO does not say which repository it comes from/],
    [{ PR_HEAD_REPO: 'someone/tool' }, /GITHUB_REPOSITORY is not set/],
    [{}, /PR_HEAD_REPO does not say which repository it comes from/],
  ];
  for (const [env, note] of unknown) {
    const run = runPr(root, { GITHUB_HEAD_REF: head, ...env });
    assert.strictEqual(run.status, 1, run.out);
    assert.match(run.out, note);
    assert.match(run.out, /so it is checked like any other branch/);
    assert.doesNotMatch(run.out, /Passed without a check/);
  }
});

test('pr: a fragment the branch adds must pass the checks of check', () => {
  const root = makeBranch({
    'src/skf-tool/references/step-01.md': 'x\n',
    'changes/no-scope.yaml': 'type: fixed\nsummary: A fix.\n',
    'changes/broken.yaml': 'type: [fixed\n',
    'changes/stray.txt': 'x',
    'changes/nested/a.yaml': SMALL_FIX,
    'changes/Bad_Name.yaml': SMALL_FIX,
  });
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /changes\/no-scope\.yaml: scope is required/);
  assert.match(out, /changes\/broken\.yaml: not valid YAML/);
  assert.match(out, /changes\/stray\.txt: not a fragment/);
  assert.match(out, /changes\/nested\/a\.yaml: fragments go directly in changes\//);
  assert.match(out, /changes\/Bad_Name\.yaml: name fragments <topic>\.yaml in lower case/);
  assert.doesNotMatch(out, /adds no change fragment/, 'the fragments are there, only invalid');
});

test('pr: a released fragment edited, renamed or copied on the branch fails', () => {
  const edited = runPr(makeBranch({ 'changes/released-before.yaml': 'type: fixed\nscope: old\nsummary: Rewritten.\n' }));
  assert.strictEqual(edited.status, 1, edited.out);
  assert.match(edited.out, /changes\/released-before\.yaml: is in v1\.0\.0, so it was already released, and it has changed since/);
  const renamed = makeBranch();
  git(renamed, ['mv', 'changes/released-before.yaml', 'changes/renamed-before.yaml']);
  commitAll(renamed, 'rename');
  const rename = runPr(renamed);
  assert.strictEqual(rename.status, 1, rename.out);
  assert.match(
    rename.out,
    /changes\/renamed-before\.yaml: has the same content as changes\/released-before\.yaml, which v1\.0\.0 already released/,
  );
  const copied = makeBranch();
  write(copied, { 'changes/copy.yaml': fs.readFileSync(path.join(copied, 'changes/released-before.yaml'), 'utf8') });
  commitAll(copied, 'copy');
  assert.strictEqual(runPr(copied).status, 1);
});

/** makeRepo()'s repository with `pending` committed on main (unreleased), and a branch off it. */
function branchAfterPending(pending, name = 'fix/more') {
  const root = makeRepo();
  write(root, pending);
  commitAll(root, 'pending change on main');
  git(root, ['checkout', '-q', '-b', name]);
  return root;
}

test('pr: an unreleased fragment the branch edits never covers a change of its own, nor an item it does not name', () => {
  const other = 'type: added\nscope: skf-other\nsummary: New `--foo` flag.\n';
  const root = branchAfterPending({ 'changes/other-foo.yaml': other }, 'feat/unrelated');
  write(root, { 'src/skf-tool/SKILL.md': SKILL_WITH_ALL, 'changes/other-foo.yaml': `${other}prs: [12]\n` });
  commitAll(root, 'feat: all');
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /added {5}changes\/other-foo\.yaml {2}skf-other {2}\(edited\)/);
  assert.match(out, /flag `--all` added {2}\[NOT COVERED by an added or breaking fragment on this branch]/);
  assert.match(out, /Editing an unreleased fragment \(changes\/other-foo\.yaml\) does not count here/);
  assert.match(out, /or name `--all` in backticks in changes\/other-foo\.yaml, which it edits/);
  assert.doesNotMatch(out, /The branch has the change fragments it needs/);

  const fix = branchAfterPending({ 'changes/pending.yaml': SMALL_FIX });
  write(fix, { 'changes/pending.yaml': SMALL_FIX.replace('A fix.', 'A fix, now for every skill.'), 'src/skf-tool/references/a.md': 'x\n' });
  commitAll(fix, 'extend the fix');
  const extended = runPr(fix);
  assert.strictEqual(extended.status, 1, extended.out);
  assert.match(extended.out, /fixed {5}changes\/pending\.yaml {2}skf-tool {2}\(edited\)/);
  assert.match(extended.out, /adds no change fragment/);
  git(fix, ['commit', '-q', '--allow-empty', '-m', 'chore: note\n\nChangelog: none (described in changes/pending.yaml)']);
  assert.strictEqual(runPr(fix).status, 0, 'an empty commit adds the line to a branch already pushed');
});

test('pr: a follow-up that names what it removes or adds in an unreleased fragment it edits passes', () => {
  const pendingBreaking = 'type: breaking\nscope: skf-tool\nsummary: The result envelope changes.\nmigration: Read the new field.\n';
  const root = branchAfterPending({ 'changes/envelope.yaml': pendingBreaking });
  write(root, {
    'src/shared/scripts/schemas/skf-tool-result-envelope.v1.json': SCHEMA_WITHOUT_WRITE_FAILURE,
    'changes/envelope.yaml': pendingBreaking.replace('changes.', 'changes, and the `write_failure` status is gone.'),
  });
  commitAll(root, 'drop write_failure too');
  const removal = runPr(root);
  assert.strictEqual(removal.status, 0, removal.out);
  assert.match(removal.out, /`write_failure` removed .* {2}\[named in changes\/envelope\.yaml]/);

  const pendingAdded = 'type: added\nscope: skf-tool\nsummary: New `--dry-run` behaviour.\n';
  const added = branchAfterPending({ 'changes/tool-flags.yaml': pendingAdded });
  write(added, {
    'src/skf-tool/SKILL.md': SKILL_WITH_ALL,
    'changes/tool-flags.yaml': pendingAdded.replace('behaviour.', 'behaviour, and a new `--all` flag.'),
  });
  commitAll(added, 'add --all too');
  const addition = runPr(added);
  assert.strictEqual(addition.status, 0, addition.out);
  assert.match(addition.out, /flag `--all` added {2}\[covered by changes\/tool-flags\.yaml]/);
});

test("pr: the base branch's own changes, merged into the branch, are not the branch's", () => {
  const root = makeBranch({ 'docs/guide.md': '# Guide\n' });
  git(root, ['checkout', '-q', 'main']);
  write(root, { 'src/skf-tool/SKILL.md': SKILL_WITH_ALL, 'changes/all-flag.yaml': ALL_FLAG });
  commitAll(root, 'feature on main');
  git(root, ['checkout', '-q', 'feat/topic']);
  git(root, ['merge', '-q', '--no-edit', 'main']);
  const { status, out } = runPr(root);
  assert.strictEqual(status, 0, out);
  assert.match(out, /Files changed in the code the package ships: 0\nChange fragments on this branch: 0\n/);
});

test('pr: reads commits only, and warns about an uncommitted fragment', () => {
  const root = makeBranch({ 'src/skf-tool/references/step-01.md': 'x\n' });
  write(root, { 'changes/small-fix.yaml': SMALL_FIX });
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /warning: changes under changes\/ or in the code the package ships are not committed/);
  assert.match(out, /adds no change fragment/);
  const clean = makeBranch({ 'src/skf-tool/references/step-01.md': 'x\n', 'changes/small-fix.yaml': SMALL_FIX });
  write(clean, { 'src/skf-tool/references/step-02.md': 'y\n' });
  const pass = runPr(clean);
  assert.strictEqual(pass.status, 0, pass.out);
  assert.match(pass.out, /The branch has the change fragments it needs, in its commits: the uncommitted changes were not read\./);
});

test('pr: a Changelog: none line in a merge commit on the branch counts', () => {
  const root = makeBranch({ 'src/skf-tool/references/step-01.md': 'Reworded.\n' }, { name: 'fix/x' });
  git(root, ['checkout', '-q', 'main']);
  write(root, { 'docs/guide.md': '# Guide\n' });
  commitAll(root, 'docs on main');
  git(root, ['checkout', '-q', 'fix/x']);
  git(root, ['merge', '-q', '--no-ff', '-m', 'Merge main into fix/x\n\nChangelog: none (wording only)', 'main']);
  const { status, out } = runPr(root);
  assert.strictEqual(status, 0, out);
  assert.match(out, /Changelog: none lines: 1\n {2}commit [0-9a-f]{8}: wording only\n/);
});

test('pr: a branch whose only change is a fragment passes when the fragment is valid, and fails when it is not', () => {
  const ok = runPr(makeBranch({ 'changes/small-fix.yaml': SMALL_FIX }));
  assert.strictEqual(ok.status, 0, ok.out);
  assert.match(ok.out, /Change fragments on this branch: 1\n {2}fixed {5}changes\/small-fix\.yaml {2}skf-tool\nChangelog/);
  const bad = runPr(makeBranch({ 'changes/small-fix.yaml': 'type: fixed\nsummary: A fix.\n' }));
  assert.strictEqual(bad.status, 1, bad.out);
  assert.match(bad.out, /changes\/small-fix\.yaml: scope is required/);
  assert.doesNotMatch(bad.out, /```yaml/, 'nothing is missing, so there is no template');
});

test('pr: a file under src/ renamed or deleted, or .npmignore deleted, changes the code the package ships', () => {
  const setup = () => {
    const root = makeRepo();
    write(root, { 'src/skf-tool/references/step-01.md': 'A step.\n', '.npmignore': 'test/\n' });
    commitAll(root, 'more files');
    git(root, ['checkout', '-q', '-b', 'feat/topic']);
    return root;
  };
  const renamed = setup();
  git(renamed, ['mv', 'src/skf-tool/references/step-01.md', 'src/skf-tool/references/step-one.md']);
  commitAll(renamed, 'refactor: rename a step\n\nChangelog: none (a file name only the workflow reads)');
  const rename = runPr(renamed);
  assert.strictEqual(rename.status, 0, rename.out);
  assert.match(
    rename.out,
    /ships: 2\n {2}src\/skf-tool\/references\/step-01\.md\n {2}src\/skf-tool\/references\/step-one\.md\n/,
    'a rename is a deletion and an addition',
  );
  for (const [file, scope] of [
    ['src/skf-tool/references/step-01.md', 'skf-tool'],
    ['.npmignore', 'packaging'],
  ]) {
    const deleted = setup();
    git(deleted, ['rm', '-q', file]);
    commitAll(deleted, `remove ${file}`);
    const run = runPr(deleted);
    assert.strictEqual(run.status, 1, run.out);
    assert.match(run.out, /adds no change fragment/, file);
    assert.strictEqual(printedTemplate(run.out).data.scope, scope, file);
  }
});

test('pr: a fragment the branch adds and then removes does not count', () => {
  const root = makeBranch({ 'src/skf-tool/references/step-01.md': 'x\n', 'changes/small-fix.yaml': SMALL_FIX });
  write(root, { 'changes/small-fix.yaml': null });
  commitAll(root, 'drop the fragment');
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /Change fragments on this branch: 0\n/);
  assert.match(out, /adds no change fragment/);
});

test('pr: the released-fragment rule takes the last stable tag of the base branch, not of a branch forked before it', () => {
  const root = branchAfterPending({ 'changes/pending.yaml': SMALL_FIX }, 'fix/late');
  git(root, ['checkout', '-q', 'main']);
  write(root, { 'docs/release.md': 'Released.\n' });
  commitAll(root, 'release 1.1.0');
  git(root, ['tag', '-a', 'v1.1.0', '-m', 'v1.1.0']);
  git(root, ['checkout', '-q', 'fix/late']);
  write(root, { 'changes/pending.yaml': SMALL_FIX.replace('A fix.', 'A better fix.') });
  commitAll(root, 'reword the pending fix');
  const { status, out } = runPr(root);
  assert.strictEqual(status, 1, out);
  assert.match(out, /changes\/pending\.yaml: is in v1\.1\.0, so it was already released, and it has changed since/);
});

test('pr: in a shallow clone whose base branch moved on, it names the missing history', () => {
  const origin = makeRepo();
  const clone = fs.mkdtempSync(path.join(os.tmpdir(), 'skf-shallow-'));
  tmpRoots.push(clone);
  git(clone, ['clone', '-q', '--depth', '1', '-b', 'main', `file://${origin}`, '.']);
  git(clone, ['checkout', '-q', '-b', 'fix/x']);
  write(clone, { 'docs/guide.md': '# Guide\n' });
  commitAll(clone, 'docs');
  write(origin, { 'docs/other.md': '# Other\n' });
  commitAll(origin, 'main moves on');
  git(clone, ['fetch', '-q', '--depth', '1', 'origin', 'main']);
  const { status, out } = runPr(clone, {}, []);
  assert.strictEqual(status, 2, out);
  assert.match(out, /this clone is shallow/);
  assert.match(out, /git fetch --unshallow origin/);
});

test('pr: the base is origin/$GITHUB_BASE_REF, else origin/main; a missing base or, in CI, a missing tag exits 2', () => {
  const root = makeBranch({ 'docs/guide.md': '# Guide\n' });
  const missing = runPr(root, {}, []);
  assert.strictEqual(missing.status, 2, missing.out);
  assert.match(missing.out, /base origin\/main not found, so the branch cannot be compared with it/);
  const ci = runPr(root, { GITHUB_ACTIONS: 'true', GITHUB_BASE_REF: 'develop' }, []);
  assert.strictEqual(ci.status, 2, ci.out);
  assert.match(ci.out, /::error::base origin\/develop not found/);
  git(root, ['update-ref', 'refs/remotes/origin/main', 'main']);
  const origin = runPr(root, {}, []);
  assert.strictEqual(origin.status, 0, origin.out);
  assert.match(origin.out, /Branch: origin\/main \(merge base/);
  assert.strictEqual(runPr(root, { GITHUB_BASE_REF: 'main' }, []).status, 0);
  const untagged = makeBranch({ 'docs/guide.md': '# Guide\n' }, { repo: { tag: false } });
  const noTag = runPr(untagged, { CI: 'true' });
  assert.strictEqual(noTag.status, 2, noTag.out);
  assert.match(noTag.out, /no stable release tag found/);
  const local = runPr(untagged);
  assert.strictEqual(local.status, 0, local.out);
  assert.match(local.out, /warning: No stable release tag found/);
});

test('pr: in GitHub Actions, annotations, and the verdict, fixes, surface changes and template in the step summary', () => {
  const failing = makeBranch({ 'src/shared/scripts/schemas/skf-tool-result-envelope.v1.json': SCHEMA_WITHOUT_WRITE_FAILURE });
  const summaryFile = path.join(failing, 'summary.md');
  const bad = runPr(failing, { GITHUB_ACTIONS: 'true', GITHUB_STEP_SUMMARY: summaryFile });
  assert.strictEqual(bad.status, 1, bad.out);
  assert.match(bad.out, /::error::skf-tool: schema enum value `write_failure` removed/);
  const summary = fs.readFileSync(summaryFile, 'utf8');
  assert.match(summary, /^### Change fragments for this pull request\n\n\*\*Fails:\*\* 2 fix\(es\) needed\.\n/);
  assert.match(summary, /\*\*To fix:\*\*\n\n- this branch changes the code the package ships/);
  assert.match(
    summary,
    /Hard \(a breaking fragment on the branch names each one\):\n\n- skf-tool: schema enum value `write_failure` removed .*\(NOT NAMED in a breaking fragment on this branch\)/,
  );
  assert.match(summary, /\*\*A fragment to fill in\*\*; save it as `changes\/topic\.yaml`:\n\n```yaml\n# The type is what a user sees/);
  const passing = makeBranch({ 'src/skf-tool/references/halts.md': 'halt_reason: "tool-missing"\n', 'changes/small-fix.yaml': SMALL_FIX });
  const passFile = path.join(passing, 'summary.md');
  const ok = runPr(passing, { GITHUB_ACTIONS: 'true', GITHUB_STEP_SUMMARY: passFile });
  assert.strictEqual(ok.status, 0, ok.out);
  const passed = fs.readFileSync(passFile, 'utf8');
  assert.match(passed, /^### Change fragments for this pull request\n\n\*\*Passes\.\*\*\n/);
  assert.match(
    passed,
    /Review \(never fails; decide whether each one needs a note\):\n\n- skf-tool: halt_reason value `tool-missing` added\n/,
  );
  assert.doesNotMatch(passed, /```yaml/);
});

// --- covered-surfaces.js on small trees ---

function memoryTree(files) {
  return { label: 'memory', files: Object.keys(files).sort(), read: (file) => files[file] ?? null };
}

const SURFACE_BASE = {
  'src/skf-forger/SKILL.md':
    '# Ferris\n\n## Capabilities\n\n| # | Code | Description | Skill |\n|---|------|-------------|-------|\n| 1 | SF | Setup | skf-setup |\n| 2 | CA | Campaign | skf-campaign |\n\n## Next\n\n| # | Code | x |\n|---|---|---|\n| 1 | ZZ | not a menu |\n',
  'src/shared/references/pipeline-contracts.md':
    '| Alias | Expands To | Description |\n|-------|-----------|-------------|\n| `forge` | `BS CS` | x |\n| `deepwiki` | `AN CS` | x |\n',
  'src/skf-setup/SKILL.md':
    '| Aspect | Detail |\n|---|---|\n| **Inputs** | (none) |\n| **Flags** | `--headless` / `-H` (skip prompts); `--tier=<Quick\\|Forge>` (pick a tier); `--quiet` (envelope only) |\n',
  'src/skf-setup/references/exit-codes.md':
    '| Code | Meaning | Raised by |\n| ---- | ------- | --------- |\n| 0 | success | end |\n| 3 | resolution-failure | step 1 |\n| 5 | state-conflict | step 2 |\n\n| Name | Value |\n|---|---|\n| 7 | not an exit code |\n',
  'src/skf-setup/references/halts.md': 'halt_reason: "tier-missing"\n{"phase":"step 2:write-tools"} and later with phase `step 3:init`\n',
  'src/forger/preferences.yaml': 'tier_override: ~\nheadless_mode: false\n',
  'src/module.yaml': 'code: skf\nskills_output_folder:\n  prompt: x\n',
  'src/shared/scripts/schemas/skf-setup-result-envelope.v1.json': JSON.stringify({
    properties: { status: { enum: ['success', 'write_failure'] }, error: { type: 'object' } },
    required: ['status'],
  }),
};

test('extractSurfaces: menu codes, aliases, flags, exit codes, halts, keys and schema items', () => {
  const found = surfaces.extractSurfaces(memoryTree(SURFACE_BASE));
  const list = (kind) =>
    [...found.items.values()]
      .filter((item) => item.kind === kind)
      .map((item) => `${item.workflow} ${item.token}`)
      .sort();
  assert.deepStrictEqual(list('menu-code'), ['skf-forger CA', 'skf-forger SF']);
  assert.deepStrictEqual(list('pipeline-alias'), ['skf-forger deepwiki', 'skf-forger forge']);
  assert.deepStrictEqual(list('flag'), ['skf-setup --headless', 'skf-setup --quiet', 'skf-setup --tier', 'skf-setup -H']);
  assert.deepStrictEqual(list('exit-code'), ['skf-setup 0', 'skf-setup 3', 'skf-setup 5']);
  assert.deepStrictEqual(list('halt-reason'), ['skf-setup tier-missing']);
  assert.deepStrictEqual(list('error-phase'), ['skf-setup step 2:write-tools', 'skf-setup step 3:init']);
  assert.deepStrictEqual(list('preference'), ['preferences headless_mode', 'preferences tier_override']);
  assert.deepStrictEqual(list('config'), ['module config skills_output_folder']);
  assert.deepStrictEqual(list('schema-enum'), ['skf-setup success', 'skf-setup write_failure']);
  assert.deepStrictEqual(list('schema-property'), ['skf-setup error', 'skf-setup status']);
  assert.deepStrictEqual(list('schema-required'), ['skf-setup status']);
  assert.deepStrictEqual(found.skillFiles, ['src/skf-forger/SKILL.md', 'src/skf-setup/SKILL.md']);
});

test('diffSurfaces: removals are hard, additions additive, the rest for review', () => {
  const head = {
    ...SURFACE_BASE,
    'src/skf-forger/SKILL.md': SURFACE_BASE['src/skf-forger/SKILL.md'].replace(
      '| 2 | CA | Campaign | skf-campaign |\n',
      '| 2 | KI | Knowledge | x |\n',
    ),
    'src/shared/references/pipeline-contracts.md':
      '| Alias | Expands To | Description |\n|-------|-----------|-------------|\n| `forge` | `BS CS` | x |\n\n**Deprecated alias:** `deepwiki` resolves to `forge-auto`.\n',
    'src/skf-setup/SKILL.md':
      '| **Flags** | `--headless` / `-H` (skip prompts); `--tier=<Quick\\|Forge\\|Deep>` (pick a tier); `--target-ref <ref>` (new) |\n',
    'src/skf-setup/references/exit-codes.md':
      '| Code | Meaning | Raised by |\n| ---- | ------- | --------- |\n| 0 | success | end |\n| 3 | input-missing | x |\n| 9 | state-conflict | x |\n',
    'src/skf-setup/references/halts.md': 'halt_reason: "not-skf-output"\n',
    'src/forger/preferences.yaml': 'tier_override: ~\ntessl_review_workspace: ~\n',
    'src/module.yaml': 'code: skf\nforge_data_folder:\n  prompt: x\n',
    'src/shared/scripts/schemas/skf-setup-result-envelope.v1.json': JSON.stringify({
      properties: { status: { enum: ['success', 'blocked'] }, error: { type: 'object' } },
      required: ['status', 'error'],
    }),
  };
  const result = surfaces.diffSurfaces(surfaces.extractSurfaces(memoryTree(SURFACE_BASE)), surfaces.extractSurfaces(memoryTree(head)));
  assert.deepStrictEqual(
    result.hard.map((finding) => finding.text),
    [
      'skf-forger: Ferris menu code `CA` removed',
      'skf-setup: schema enum value `write_failure` removed (src/shared/scripts/schemas/skf-setup-result-envelope.v1.json#/properties/status)',
      'skf-setup: flag `--quiet` removed',
    ],
  );
  assert.deepStrictEqual(result.additive.map((finding) => finding.text).sort(), [
    'preferences: preference key `tessl_review_workspace` added',
    'skf-forger: Ferris menu code `KI` added',
    'skf-setup: exit code `9` added (state-conflict)',
    'skf-setup: flag `--target-ref` added',
    'skf-setup: schema enum value `blocked` added (src/shared/scripts/schemas/skf-setup-result-envelope.v1.json#/properties/status)',
  ]);
  const review = result.review.map((finding) => finding.text);
  for (const expected of [
    'module config: install config key `forge_data_folder` added',
    'module config: install config key `skills_output_folder` removed',
    'preferences: preference key `headless_mode` removed',
    'skf-forger: pipeline alias `deepwiki` is now deprecated',
    'skf-setup: flag `--tier` text changed',
    'skf-setup: exit code `3` meaning changed from "resolution-failure" to "input-missing"',
    'skf-setup: exit code `5` removed (was state-conflict)',
    'skf-setup: required field `error` added (src/shared/scripts/schemas/skf-setup-result-envelope.v1.json#)',
    'skf-setup: halt_reason value `tier-missing` removed',
    'skf-setup: halt_reason value `not-skf-output` added',
    'skf-setup: error.phase value `step 2:write-tools` removed',
  ]) {
    assert.ok(review.includes(expected), `missing review item: ${expected}\n${review.join('\n')}`);
  }
  assert.ok(!review.some((text) => text.includes('`--headless`') || text.includes('`-H`')), 'an unchanged flag is not listed');
});

function diffTrees(base, head) {
  return surfaces.diffSurfaces(surfaces.extractSurfaces(memoryTree(base)), surfaces.extractSurfaces(memoryTree(head)));
}

test('diffSurfaces: a new workflow folder alone changes nothing, even when a schema label moves to shared', () => {
  const file = 'src/shared/scripts/schemas/skf-update-result-envelope.v1.json';
  const base = {
    'src/skf-update-skill/SKILL.md': '# Update\n',
    [file]: JSON.stringify({ properties: { status: { enum: ['success', 'blocked'] }, error: { type: 'object' } }, required: ['status'] }),
  };
  const head = { ...base, 'src/skf-update-stack-skill/SKILL.md': '# Update stack\n' };
  const label = (tree) =>
    [...surfaces.extractSurfaces(memoryTree(tree)).items.values()].find((item) => item.kind === 'schema-enum').workflow;
  assert.deepStrictEqual([label(base), label(head)], ['skf-update-skill', 'shared'], 'the label changes');
  assert.deepStrictEqual(diffTrees(base, head), { hard: [], additive: [], review: [] });
});

test('diffSurfaces: an enum moved into $defs behind a $ref, or properties wrapped in allOf, is a move to review', () => {
  const file = 'src/shared/scripts/schemas/skf-setup-result-envelope.v1.json';
  const base = {
    'src/skf-setup/SKILL.md': '# Setup\n',
    [file]: JSON.stringify({ properties: { status: { enum: ['success', 'blocked'] }, error: { type: 'object' } } }),
  };
  const head = {
    ...base,
    [file]: JSON.stringify({
      $defs: { status: { enum: ['success', 'blocked'] } },
      allOf: [{ properties: { status: { $ref: '#/$defs/status' }, error: { type: 'object' } } }],
    }),
  };
  const result = diffTrees(base, head);
  assert.deepStrictEqual(result.hard, [], describeFindings(result.hard));
  assert.deepStrictEqual(result.additive, [], describeFindings(result.additive));
  assert.deepStrictEqual(
    result.review.map((finding) => finding.text),
    [
      `skf-setup: schema enum value \`blocked\` moved from ${file}#/properties/status to #/$defs/status`,
      `skf-setup: schema enum value \`success\` moved from ${file}#/properties/status to #/$defs/status`,
      `skf-setup: schema property \`error\` moved from ${file}#/properties/error to #/allOf/0/properties/error`,
      `skf-setup: schema property \`status\` moved from ${file}#/properties/status to #/allOf/0/properties/status`,
    ],
  );
});

test('diffSurfaces: a value dropped from one place while it stays at another it already had is still hard', () => {
  const file = 'src/shared/scripts/schemas/skf-setup-result-envelope.v1.json';
  const base = { [file]: JSON.stringify({ properties: { a: { enum: ['x', 'y'] }, b: { enum: ['x'] } } }) };
  const head = { [file]: JSON.stringify({ properties: { a: { enum: ['y'] }, b: { enum: ['x'] } } }) };
  assert.deepStrictEqual(
    diffTrees(base, head).hard.map((finding) => finding.text),
    [`shared: schema enum value \`x\` removed (${file}#/properties/a)`],
  );
});

test('extractSurfaces: flags in the Headless inputs, Headless flag and Overrides rows, and bare --flags', () => {
  const found = surfaces.extractSurfaces(
    memoryTree({
      'src/skf-analyze-source/SKILL.md':
        '| **Headless inputs** | `--project-path <path>` (skip the prompt), `--pin <ref>` (pin) |\n| **Headless flag** | `--headless` / `-H` flips every gate |\n| **Auto flag** | `[auto]` requires `--auto-only` |\n',
      'src/skf-quick-skill/SKILL.md': '| **Overrides** | `--description`, `--batch <file>`, `--fail-fast` |\n',
      'src/skf-create-skill/SKILL.md':
        '| **Inputs** | brief_path [required], --batch [optional] |\n| **Headless** | pass --not-a-flag-row |\n',
    }),
  );
  assert.deepStrictEqual(
    [...found.items.values()]
      .filter((item) => item.kind === 'flag')
      .map((item) => `${item.workflow} ${item.token}`)
      .sort(),
    [
      'skf-analyze-source --headless',
      'skf-analyze-source --pin',
      'skf-analyze-source --project-path',
      'skf-analyze-source -H',
      'skf-create-skill --batch',
      'skf-quick-skill --batch',
      'skf-quick-skill --description',
      'skf-quick-skill --fail-fast',
    ],
  );
});

test('flagsInRow: a bare --flag is read, a flag inside a span that starts with other text is not', () => {
  const flags = surfaces.flagsInRow(
    '| **Inputs** | brief_path [required], --batch [optional]; `--all` (every skill); `run [--from=<x>]` |',
  );
  assert.deepStrictEqual([...flags.keys()], ['--batch', '--all']);
  assert.strictEqual(flags.get('--batch'), '--batch [optional]');
  assert.strictEqual(flags.get('--all'), '--all every skill run [--from=<x>]');
});

test('flagsInRow: long and short flags, values and the text after each', () => {
  const flags = surfaces.flagsInRow('| **Flags** | `--headless` / `-H` (skip); `--tier=<A\\|B>` (pick). `campaign resume [--from=<x>]` |');
  assert.deepStrictEqual([...flags.keys()], ['--headless', '-H', '--tier']);
  assert.strictEqual(flags.get('--headless'), '--headless /');
  assert.strictEqual(flags.get('-H'), '-h skip');
  assert.strictEqual(flags.get('--tier'), '--tier=<a b> pick campaign resume [--from=<x>]');
});

const ADD_BREAKING = 'if the workflow no longer accepts it, add a breaking fragment that names it';

// A workflow whose Overrides row lists its flags, as skf-campaign's did at v2.0.0.
const OVERRIDES_BASE = {
  'src/skf-campaign/SKILL.md':
    '# Campaign\n\n| Aspect | Detail |\n|---|---|\n| **Overrides** | `--brief <file>` (seed targets); `--headless` / `-H` (no prompts); `--from <skill>` (resume point); `-X` (extra) |\n',
  'src/skf-campaign/references/step-01-setup.md': 'Draw inputs from `--brief` when headless, not from --brief-file.\n',
  'src/skf-campaign/references/sub/resume.md': 'Pass --headless, or `-H`, to skip every prompt.\n',
  'src/skf-campaign/references/step-02.md': 'Every gate honours `--headless`.\n',
  'src/skf-campaign/references/step-03.md': 'In `--headless` runs, log each auto-decision.\n',
  'src/skf-campaign/templates/report.md': 'Headless: `--headless`\n',
};

test('diffSurfaces: a flag whose row is deleted while its workflow still names it is a review item, not hard', () => {
  const head = { ...OVERRIDES_BASE, 'src/skf-campaign/SKILL.md': '# Campaign\n\nThe overrides moved to the step files.\n' };
  const result = diffTrees(OVERRIDES_BASE, head);
  assert.deepStrictEqual(tokens(result.hard), ['--from', '-X'], describeFindings(result.hard));
  assert.deepStrictEqual(result.additive, [], describeFindings(result.additive));
  const movedOut = result.review.filter((finding) => finding.change === 'moved-out');
  assert.deepStrictEqual(
    movedOut.map((finding) => finding.text),
    [
      `skf-campaign: flag \`--brief\` left every flag row but is still named in src/skf-campaign/references/step-01-setup.md: ${ADD_BREAKING}`,
      `skf-campaign: flag \`--headless\` left every flag row but is still named in src/skf-campaign/references/step-02.md, src/skf-campaign/references/step-03.md, src/skf-campaign/references/sub/resume.md and 1 more file: ${ADD_BREAKING}`,
      `skf-campaign: flag \`-H\` left every flag row but is still named in src/skf-campaign/references/sub/resume.md: ${ADD_BREAKING}`,
    ],
  );
  assert.strictEqual(movedOut[0].where, 'src/skf-campaign/references/step-01-setup.md');
  assert.ok(
    movedOut.every((finding) => finding.group === 'review'),
    'every moved flag is for review',
  );
});

test('diffSurfaces: a moved-out flag comes first in the review group', () => {
  const head = {
    ...OVERRIDES_BASE,
    'src/skf-campaign/SKILL.md': '# Campaign\n\nThe overrides moved to the step files.\n',
    'src/skf-analyze-source/references/halts.md': 'halt_reason: "a-new-halt"\n',
  };
  const review = diffTrees(OVERRIDES_BASE, head).review;
  assert.deepStrictEqual(
    review.map((finding) => `${finding.change} ${finding.workflow} ${finding.token}`),
    [
      'moved-out skf-campaign --brief',
      'moved-out skf-campaign --headless',
      'moved-out skf-campaign -H',
      'added skf-analyze-source a-new-halt',
    ],
  );
});

// skf-setup's Flags row and step 1, trimmed, with the helper call of
// detect-and-tier.md that hands `--require-tier` on to skf-detect-tools.py.
const SETUP_BASE = {
  'src/skf-setup/SKILL.md':
    '# Setup\n\n| **Flags** | `--headless` / `-H` (skip prompts); `--require-tier=<Quick\\|Deep>` (halt below it); `--quiet` (envelope only); `--dry-run` (plan only) |\n\n1. Parse flags: `{quiet_mode}` is true on `--quiet`, `{dry_run}` on `--dry-run`, and `{require_tier}` comes from `--require-tier=<tier>`.\n',
  'src/skf-setup/references/detect-and-tier.md':
    'Build the Bash invocation: `uv run {detectToolsHelper} --project-root "{project-root}"`. If `{require_tier}` is non-null, append `--require-tier "{require_tier}"`. Then execute.\n',
  'src/skf-analyze-source/SKILL.md': '| **Headless inputs** | `--project-path <path>` (skip the prompt), `--pin <version>` (pin a tag) |\n',
  'src/skf-analyze-source/references/step-auto-scope.md': 'When `--pin` is provided, validate it.\n',
};

test("diffSurfaces: a flag named only in a helper call or in another program's command is removed, so hard", () => {
  const head = {
    ...SETUP_BASE,
    'src/skf-setup/SKILL.md':
      '# Setup\n\n| **Flags** | `--headless` / `-H` (skip prompts); `--quiet` (envelope only) |\n\n1. Parse flags: `{quiet_mode}` is true on `--quiet`. Preview a publish with `npm publish --dry-run`.\n',
    'src/skf-analyze-source/SKILL.md': '| **Headless inputs** | `--project-path <path>` (skip the prompt) |\n',
    'src/skf-analyze-source/references/step-auto-scope.md':
      'Validate the pin:\n\n```bash\nuv run {validatePinsHelper} --repo-url {project_path} \\\n  --pin {pin_value}\n```\n',
  };
  const result = diffTrees(SETUP_BASE, head);
  assert.deepStrictEqual(
    result.hard.map((finding) => finding.text),
    ['skf-analyze-source: flag `--pin` removed', 'skf-setup: flag `--dry-run` removed', 'skf-setup: flag `--require-tier` removed'],
  );
  assert.ok(!result.review.some((finding) => finding.change === 'moved-out'), describeFindings(result.review));
});

test('diffSurfaces: a flag named only in a note that it was renamed is removed, and the gate refuses a minor', () => {
  const head = {
    ...SETUP_BASE,
    'src/skf-setup/SKILL.md':
      '# Setup\n\n| **Flags** | `--headless` / `-H` (skip prompts); `--require-tier=<Quick\\|Deep>` (halt below it); `--silent` (envelope only); `--dry-run` (plan only) |\n\n1. Parse flags: `{quiet_mode}` is true on `--silent`, `{dry_run}` on `--dry-run`, and `{require_tier}` comes from `--require-tier=<tier>`. `--quiet` was renamed to `--silent`.\n',
  };
  const result = diffTrees(SETUP_BASE, head);
  assert.deepStrictEqual(
    result.hard.map((finding) => `${finding.change} ${finding.token}`),
    ['removed --quiet'],
  );
  assert.deepStrictEqual(tokens(result.additive), ['--silent']);
  const verdict = changes.evaluateGate({
    next: '2.3.0',
    bump: 'minor',
    current: '2.2.0',
    baseTag: 'v2.2.0',
    fragments: [frag('added')],
    surfaces: result,
  });
  assert.ok(
    verdict.refusals.some((refusal) => refusal.includes('no breaking fragment names `--quiet`')),
    verdict.refusals.join('\n'),
  );
});

test('diffSurfaces: a flag that leaves the rows as a new name enters them is a possible rename, so hard', () => {
  const head = {
    ...SETUP_BASE,
    'src/skf-setup/SKILL.md':
      '# Setup\n\n| **Flags** | `--headless` / `-H` (skip prompts); `--require-tier=<Quick\\|Deep>` (halt below it); `--silent` (envelope only); `--dry-run` (plan only) |\n\n1. Parse flags: `{quiet_mode}` is true on `--quiet`, `{dry_run}` on `--dry-run`, and `{require_tier}` comes from `--require-tier=<tier>`.\n',
  };
  const result = diffTrees(SETUP_BASE, head);
  assert.deepStrictEqual(
    result.hard.map((finding) => finding.text),
    [
      'skf-setup: flag `--quiet` left every flag row as `--silent` entered one, a possible rename (still named in src/skf-setup/SKILL.md; if the workflow still accepts `--quiet`, put it back in a flag row)',
    ],
  );
  assert.strictEqual(result.hard[0].change, 'possible-rename');
  assert.ok(!result.review.some((finding) => finding.change === 'moved-out'), describeFindings(result.review));
});

test('diffSurfaces: a flag the workflow already named entering a row is no rename, so the flag that left stays a review item', () => {
  const base = { ...SETUP_BASE, 'src/skf-setup/references/log.md': 'Log every probe when `--verbose` is set.\n' };
  const head = {
    ...base,
    'src/skf-setup/SKILL.md':
      '# Setup\n\n| **Flags** | `--headless` / `-H` (skip prompts); `--require-tier=<Quick\\|Deep>` (halt below it); `--verbose` (log probes); `--dry-run` (plan only) |\n\n1. Parse flags: `{quiet_mode}` is true on `--quiet`. The old `--silent` alias was removed, `{dry_run}` is true on `--dry-run`.\n',
  };
  const result = diffTrees(base, head);
  assert.deepStrictEqual(result.hard, [], describeFindings(result.hard));
  assert.deepStrictEqual(tokens(result.additive), ['--verbose']);
  assert.deepStrictEqual(
    result.review.filter((finding) => finding.change === 'moved-out').map((finding) => finding.token),
    ['--quiet'],
  );
});

test('diffSurfaces: a flag no file of its workflow names any more is hard, whatever other workflows or longer flags say', () => {
  const head = {
    'src/skf-campaign/SKILL.md': '# Campaign\n\n| **Overrides** | `--headless` / `-H` (no prompts) |\n',
    'src/skf-campaign/references/step-01-setup.md': 'Seed from `--brief-file`, never `--briefs`; run `tool -X` or tool -X.\n',
    'src/skf-campaign/references/notes.md': 'Resume with `--from-skill <x>`.\n',
    'src/skf-other/references/step.md': 'This workflow still takes `--brief`, `--from <skill>` and `-X`.\n',
  };
  const result = diffTrees(OVERRIDES_BASE, head);
  assert.deepStrictEqual(
    result.hard.map((finding) => finding.text),
    ['skf-campaign: flag `--brief` removed', 'skf-campaign: flag `--from` removed', 'skf-campaign: flag `-X` removed'],
  );
  assert.ok(!result.review.some((finding) => finding.change === 'moved-out'), describeFindings(result.review));
});

// --- Tool minimums (src/shared/tool-requirements.yaml) ---

const TOOL_LIST = 'src/shared/tool-requirements.yaml';

/** A tool list: each tool key with [name, minimum or null]. */
function toolList(tools, tested = '1.0') {
  const lines = ['schema_version: 1', 'tools:'];
  for (const [key, [name, minimum]] of Object.entries(tools)) {
    lines.push(`  ${key}:`, `    name: ${name}`, `    minimum: ${minimum === null ? 'null' : `"${minimum}"`}`, `    tested: ["${tested}"]`);
  }
  return `${lines.join('\n')}\n`;
}

test('isSurfaceFile reads the tool list, and extractSurfaces a minimum for each tool that has one', () => {
  assert.strictEqual(surfaces.isSurfaceFile(TOOL_LIST), true);
  assert.strictEqual(surfaces.isSurfaceFile('src/shared/other.yaml'), false);
  const found = surfaces.extractSurfaces(memoryTree({ [TOOL_LIST]: toolList({ ast_grep: ['ast-grep', '0.45.3'], gh_cli: ['gh', null] }) }));
  const items = [...found.items.values()].filter((item) => item.kind === 'tool-minimum');
  assert.deepStrictEqual(
    items.map((item) => [item.workflow, item.token, item.detail, item.where]),
    [['requirements', 'ast-grep', '0.45.3', TOOL_LIST]],
  );
  assert.deepStrictEqual(surfaces.extractSurfaces(memoryTree({ [TOOL_LIST]: 'tools: [unclosed\n' })).items.size, 0);
});

test('diffSurfaces: a raised or new tool minimum is hard, a lowered or removed one additive, a tested version no surface', () => {
  const base = {
    [TOOL_LIST]: toolList({
      node: ['Node.js', '22'],
      git: ['git', '2.15'],
      ast_grep: ['ast-grep', '0.45.3'],
      gh_cli: ['gh', null],
      uv: ['uv', '0.4'],
      qmd: ['qmd', '2.0'],
    }),
  };
  const head = {
    [TOOL_LIST]: toolList(
      {
        node: ['Node.js', '22.0.0'],
        git: ['git', '2.20'],
        ast_grep: ['ast-grep', '0.44'],
        gh_cli: ['gh', '2.40'],
        uv: ['uv', null],
        ccc: ['ccc', '0.2'],
      },
      '9.9',
    ),
  };
  const result = diffTrees(base, head);
  assert.deepStrictEqual(
    result.hard.map((finding) => finding.text),
    [
      'requirements: tool minimum `ccc` added (0.2)',
      'requirements: tool minimum `gh` added (2.40)',
      'requirements: tool minimum `git` raised from 2.15 to 2.20',
    ],
  );
  assert.deepStrictEqual(
    result.additive.map((finding) => finding.text),
    [
      'requirements: tool minimum `ast-grep` lowered from 0.45.3 to 0.44',
      'requirements: tool minimum `qmd` removed (was 2.0)',
      'requirements: tool minimum `uv` removed (was 0.4)',
    ],
  );
  assert.deepStrictEqual(result.review, [], describeFindings(result.review));
  const verdict = changes.evaluateGate({
    next: '2.3.0',
    bump: 'minor',
    current: '2.2.0',
    baseTag: 'v2.2.0',
    fragments: [frag('added')],
    surfaces: result,
  });
  assert.ok(
    verdict.refusals.some((refusal) => refusal.includes('no breaking fragment names `git`')),
    verdict.refusals.join('\n'),
  );
  assert.ok(
    verdict.refusals.some((refusal) => refusal.includes('below the minimum major')),
    verdict.refusals.join('\n'),
  );
});

test('pr: a raised tool minimum needs a breaking fragment that names the tool', () => {
  const root = makeRepo();
  write(root, { [TOOL_LIST]: toolList({ ast_grep: ['ast-grep', '0.45.3'] }) });
  commitAll(root, 'tool list');
  git(root, ['checkout', '-q', '-b', 'feat/raise']);
  write(root, { [TOOL_LIST]: toolList({ ast_grep: ['ast-grep', '0.46.0'] }) });
  commitAll(root, 'raise');
  const raised = runPr(root);
  assert.strictEqual(raised.status, 1, raised.out);
  assert.match(
    raised.out,
    /tool minimum `ast-grep` raised from 0\.45\.3 to 0\.46\.0, and no breaking fragment on this branch names `ast-grep` in backticks/,
  );
  write(root, {
    'changes/raise-ast-grep.yaml':
      'type: breaking\nscope: requirements\nsummary: |\n  SKF now needs `ast-grep` 0.46.0 or newer.\nmigration: |\n  Run `npm install -g @ast-grep/cli@latest`.\n',
  });
  commitAll(root, 'fragment');
  const named = runPr(root);
  assert.strictEqual(named.status, 0, named.out);
  assert.match(named.out, /tool minimum `ast-grep` raised from 0\.45\.3 to 0\.46\.0 {2}\[named in changes\/raise-ast-grep\.yaml]/);
});

test('backtest v2.2.0..working tree: a breaking fragment names every tool minimum since v2.2.0', () => {
  if (!needRefs(['v2.2.0'])) return 'skip';
  const minimums = surfaces.compareRefs(ROOT, 'v2.2.0', null).hard.filter((finding) => finding.kind === 'tool-minimum');
  for (const token of ['Node.js', 'Python', 'git', 'ast-grep']) assert.ok(tokens(minimums).includes(token), token);
  const breaking = changes.readFragments(ROOT).fragments.filter((fragment) => fragment.data && fragment.data.type === 'breaking');
  const unnamed = minimums.filter((finding) => !breaking.some((fragment) => changes.namesToken(fragment, finding.token)));
  assert.deepStrictEqual(unnamed, [], describeFindings(unnamed));
});

test('schemaWorkflow names the workflow a result-envelope schema belongs to', () => {
  const workflows = ['skf-setup', 'skf-update-skill', 'skf-brief-skill', 'skf-create-skill', 'skf-create-stack-skill'];
  assert.strictEqual(surfaces.schemaWorkflow('src/shared/scripts/schemas/skf-setup-result-envelope.v1.json', workflows), 'skf-setup');
  assert.strictEqual(
    surfaces.schemaWorkflow('src/shared/scripts/schemas/skf-update-result-envelope.v1.json', workflows),
    'skf-update-skill',
  );
  assert.strictEqual(surfaces.schemaWorkflow('src/shared/scripts/schemas/skf-brief-result-envelope.v1.json', workflows), 'skf-brief-skill');
  assert.strictEqual(surfaces.schemaWorkflow('src/shared/scripts/schemas/skf-create-result-envelope.v1.json', workflows), 'shared');
  assert.strictEqual(surfaces.schemaWorkflow('src/shared/scripts/schemas/skill-brief.v1.json', workflows), 'shared');
});

test('parseCatFileBatch reads sizes in bytes and marks missing objects', () => {
  const body = 'hé\n';
  const buffer = Buffer.concat([
    Buffer.from(`aaa blob ${Buffer.byteLength(body)}\n`),
    Buffer.from(body),
    Buffer.from('\nbbb missing\nccc blob 0\n\n'),
  ]);
  assert.deepStrictEqual(surfaces.parseCatFileBatch(buffer), [body, null, '']);
});

test('covered-surfaces CLI: a ref that does not resolve exits 2', () => {
  const { status, out } = runTool(SURFACES_TOOL, ['--root', ROOT, '--base', 'refs/tags/does-not-exist']);
  assert.strictEqual(status, 2, out);
  assert.match(out, /ref refs\/tags\/does-not-exist not found/);
});

// --- Floors on this checkout ---

test('real tree: all 16 workflow SKILL.md files are read', () => {
  const found = surfaces.extractSurfaces(surfaces.workingTree(ROOT));
  const onDisk = fs
    .readdirSync(path.join(ROOT, 'src'))
    .filter((name) => name.startsWith('skf-') && fs.existsSync(path.join(ROOT, 'src', name, 'SKILL.md')))
    .map((name) => `src/${name}/SKILL.md`)
    .sort();
  assert.strictEqual(onDisk.length, 16);
  assert.deepStrictEqual(found.skillFiles, onDisk);
});

test('real tree: CA, --target-ref and the other surfaces v3.0.0 adds are found, write_failure is gone', () => {
  const items = [...surfaces.extractSurfaces(surfaces.workingTree(ROOT)).items.values()];
  const has = (kind, workflow, token) => items.some((item) => item.kind === kind && item.workflow === workflow && item.token === token);
  assert.ok(has('menu-code', 'skf-forger', 'CA'), 'menu code CA');
  assert.ok(has('flag', 'skf-update-skill', '--target-ref'), 'skf-update-skill --target-ref');
  assert.ok(has('preference', 'preferences', 'tessl_review_workspace'), 'preference tessl_review_workspace');
  assert.ok(has('exit-code', 'skf-quick-skill', '9'), 'skf-quick-skill exit 9');
  assert.ok(has('exit-code', 'skf-create-stack-skill', '5'), 'skf-create-stack-skill exit 5');
  assert.ok(has('pipeline-alias', 'skf-forger', 'forge-auto'), 'alias forge-auto');
  assert.ok(
    items.some((item) => item.kind === 'pipeline-alias' && item.token === 'deepwiki' && item.detail === 'deprecated'),
    'deepwiki counts as a deprecated alias',
  );
  assert.ok(!items.some((item) => item.token === 'write_failure'), 'write_failure is gone');
  const status = items.filter(
    (item) => item.kind === 'schema-enum' && item.workflow === 'skf-setup' && item.where.endsWith('/skf_setup/properties/status'),
  );
  assert.deepStrictEqual(status.map((item) => item.token).sort(), ['blocked', 'success', 'tier_failure']);
});

test('real tree: the flags of AN, QS and CS outside a Flags row are found', () => {
  const items = [...surfaces.extractSurfaces(surfaces.workingTree(ROOT)).items.values()];
  const has = (workflow, token) => items.some((item) => item.kind === 'flag' && item.workflow === workflow && item.token === token);
  for (const token of ['--project-path', '--pin', '--target-ref', '--headless', '-H']) assert.ok(has('skf-analyze-source', token), token);
  for (const token of ['--batch', '--fail-fast', '--no-active-pointer']) assert.ok(has('skf-quick-skill', token), token);
  assert.ok(has('skf-create-skill', '--batch'), 'the bare --batch in the Inputs row');
});

const FLAG_WORKFLOWS_AT_PIN = [
  'skf-analyze-source',
  'skf-create-skill',
  'skf-drop-skill',
  'skf-export-skill',
  'skf-quick-skill',
  'skf-refine-architecture',
  'skf-rename-skill',
  'skf-setup',
  'skf-test-skill',
  'skf-update-skill',
  'skf-verify-stack',
];

test(`real tree: every workflow with flags at ${PINNED_COMMIT} still has flags (a renamed flag row goes blind)`, () => {
  if (!needRefs([PINNED_COMMIT])) return 'skip';
  const withFlags = (tree) =>
    [
      ...new Set([...surfaces.extractSurfaces(tree).items.values()].filter((item) => item.kind === 'flag').map((item) => item.workflow)),
    ].sort();
  assert.deepStrictEqual(withFlags(surfaces.refTree(ROOT, PINNED_COMMIT)), FLAG_WORKFLOWS_AT_PIN);
  const now = new Set(withFlags(surfaces.workingTree(ROOT)));
  const blind = FLAG_WORKFLOWS_AT_PIN.filter((workflow) => !now.has(workflow));
  assert.deepStrictEqual(blind, [], `no flag is read from ${blind.join(', ')}: was its Flags or Inputs row renamed?`);
});

// --- Backtests against the real history ---

test('backtest v1.9.0..v2.0.0: the hard group holds only the onboard alias', () => {
  if (!needRefs(['v1.9.0', 'v2.0.0'])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v1.9.0', 'v2.0.0');
  assert.deepStrictEqual(tokens(report.hard), ['onboard'], describeFindings(report.hard));
  assert.strictEqual(report.hard[0].kind, 'pipeline-alias');
});

test('backtest v2.0.0..v2.0.1: skf-campaign dropped its Overrides row but kept its flags, so they are review items', () => {
  if (!needRefs(['v2.0.0', 'v2.0.1'])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v2.0.0', 'v2.0.1');
  assert.deepStrictEqual(report.hard, [], describeFindings(report.hard));
  const movedOut = report.review.filter((finding) => finding.change === 'moved-out');
  assert.deepStrictEqual(
    movedOut.map((finding) => `${finding.workflow} ${finding.token}`),
    ['skf-campaign --brief', 'skf-campaign --from', 'skf-campaign --headless', 'skf-campaign --manifest', 'skf-campaign -H'],
  );
  assert.ok(
    movedOut.every((finding) => finding.where.split(', ').includes('src/skf-campaign/SKILL.md')),
    'each one is still in the step-4 table of SKILL.md',
  );
});

test('backtest: of every consecutive pair of stable tags up to v2.2.0, only v1.9.0..v2.0.0 has a hard item', () => {
  if (!needRefs(['v1.9.0', 'v2.0.0', 'v2.0.1', 'v2.2.0'])) return 'skip';
  const stable = git(ROOT, ['tag', '--list', 'v[0-9]*', '--sort=v:refname'])
    .split('\n')
    .filter((tag) => tag && !tag.includes('-'));
  const tags = stable.slice(0, stable.indexOf('v2.2.0') + 1);
  const withHard = [];
  for (const [index, tag] of tags.entries()) {
    if (index === 0) continue;
    const report = surfaces.compareRefs(ROOT, tags[index - 1], tag);
    if (report.hard.length > 0) withHard.push(`${tags[index - 1]}..${tag}: ${tokens(report.hard).join(', ')}`);
  }
  assert.ok(tags.length > 2, `stable tags: ${tags.join(' ')}`);
  assert.deepStrictEqual(withHard, ['v1.9.0..v2.0.0: onboard']);
});

const V3_ADDITIVE = [
  'preferences: preference key `tessl_review_workspace` added',
  'skf-create-stack-skill: exit code `5` added (state-conflict)',
  'skf-forger: Ferris menu code `CA` added',
  'skf-quick-skill: exit code `9` added (state-conflict)',
  'skf-update-skill: flag `--target-ref` added',
];

test(`backtest v2.2.0..${PINNED_COMMIT}: write_failure is hard, and exactly five additions`, () => {
  if (!needRefs(['v2.2.0', PINNED_COMMIT])) return 'skip';
  const report = surfaces.compareRefs(ROOT, 'v2.2.0', PINNED_COMMIT);
  assert.deepStrictEqual(tokens(report.hard), ['write_failure'], describeFindings(report.hard));
  assert.deepStrictEqual(
    report.additive.map((finding) => finding.text),
    V3_ADDITIVE,
  );
});

// A smoke test only: later changes may rightly change what HEAD reports, and
// the exact result is pinned by the backtest above.
test('smoke: the last stable tag compares with HEAD', () => {
  const tag = surfaces.lastStableTag(ROOT);
  if (!tag) {
    if (IN_CI) throw new Error('no stable release tag: run git fetch --tags');
    console.log('  no stable release tag: run git fetch --tags');
    return 'skip';
  }
  const report = surfaces.compareRefs(ROOT, tag, 'HEAD');
  for (const group of surfaces.GROUPS) assert.ok(Array.isArray(report[group]), group);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed${skipped > 0 ? `, ${skipped} skipped` : ''}`);
if (failed > 0) process.exit(1);
