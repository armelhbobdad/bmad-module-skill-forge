/**
 * Tests for tools/check-required-checks.js
 *
 * `npm run test:docs-links-tool` runs this file, then the tool itself with
 * --releasing, so the required validate job of quality.yaml runs both on
 * every pull request, on Linux and Windows (issue #570). These tests pin:
 * - the check names the tool derives from quality.yaml: a job's `name:` or
 *   else its key, one check per value of a one-dimension matrix as
 *   `<name> (<value>)`, and a stop (exit 2, every such job named, nothing
 *   compared) on each shape it does not handle: several dimensions,
 *   include, exclude, a matrix or a value that is not a plain string, an
 *   expression in `name:`, a reusable workflow call;
 * - the comparison with the list between the required-checks markers of
 *   RELEASING.md and with the live Default ruleset (gh answering from a
 *   table): a job renamed by key or by `name:`, removed or added, and an
 *   `os` matrix value changed each fail with exit 1, naming the missing
 *   and the extra checks; the order of a list does not matter, a name
 *   listed twice does, and a list the tool cannot read stops it;
 * - the ruleset found by name, a failed lookup tried again, and the
 *   repository taken from --repo or $GITHUB_REPOSITORY;
 * - this repository: quality.yaml, RELEASING.md and the wiring that runs
 *   the check (package.json, the validate job, npm test).
 *
 * Fixture checkouts are throwaway folders read through --root. A file the
 * tool reads is written byte for byte, so a CRLF case stays CRLF on Windows.
 */

const assert = require('node:assert');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const YAML = require('yaml');

const REPO_ROOT = path.join(__dirname, '..');
const TOOL = path.join(REPO_ROOT, 'tools', 'check-required-checks.js');
const { END, RELEASING, START, WORKFLOW, compareChecks, documentedChecks, expectedChecks, main } = require(TOOL);

const REPO = 'owner/repo';

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

// --- Fixtures ---

const STEPS = [{ run: 'npm test' }];
/** A job named by its key, one named by `name:`, and a one-dimension matrix. */
const JOBS = {
  lint: { 'runs-on': 'ubuntu-latest', steps: STEPS },
  build: { name: 'Build', 'runs-on': 'ubuntu-latest', steps: STEPS },
  test: {
    strategy: { 'fail-fast': false, matrix: { os: ['ubuntu-latest', 'windows-latest'] } },
    'runs-on': '${{ matrix.os }}',
    steps: STEPS,
  },
};
const CHECKS = ['lint', 'Build', 'test (ubuntu-latest)', 'test (windows-latest)'];

function workflowText(jobs) {
  return YAML.stringify({ name: 'Quality', on: { pull_request: { branches: ['**'] } }, jobs });
}

function releasingText(checks) {
  return ['# Releasing', '', 'Required checks:', '', START, '', ...checks.map((check) => `- \`${check}\``), '', END, ''].join('\n');
}

function write(root, file, text) {
  const target = path.join(root, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, Buffer.from(text, 'utf8'));
}

/** A throwaway checkout holding the two files the tool reads (null leaves one out). */
function makeRoot({ workflow = workflowText(JOBS), releasing = releasingText(CHECKS) } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'required-checks-'));
  tmpRoots.push(root);
  if (workflow !== null) write(root, WORKFLOW, workflow);
  if (releasing !== null) write(root, RELEASING, releasing);
  return root;
}

function realText(file) {
  return fs.readFileSync(path.join(REPO_ROOT, file), 'utf8');
}

const ok = (data) => ({ status: 0, stdout: JSON.stringify(data), stderr: '' });
const DOWN = { status: 1, stdout: '', stderr: 'connect: connection refused\n' };

function rulesetBody(required) {
  return { rules: [{ type: 'required_status_checks', parameters: { required_status_checks: required.map((context) => ({ context })) } }] };
}

/**
 * gh answering from a table: each route answers the calls whose joined
 * arguments contain its `match`, in order, repeating its last answer.
 */
function fakeIo(
  required,
  {
    list = [
      ok([
        { name: 'Other', id: 4 },
        { name: 'Default', id: 5 },
      ]),
    ],
  } = {},
) {
  const calls = [];
  const routes = [
    { match: `repos/${REPO}/rulesets/5`, answers: [ok(rulesetBody(required))] },
    { match: `repos/${REPO}/rulesets`, answers: list },
  ];
  return {
    calls,
    gh: (args) => {
      calls.push(['gh', ...args]);
      const line = args.join(' ');
      const route = routes.find((candidate) => line.includes(candidate.match));
      if (!route) return { status: 97, stdout: '', stderr: `no route for gh ${line}` };
      route.count = (route.count || 0) + 1;
      return route.answers[Math.min(route.count, route.answers.length) - 1];
    },
    sleep: (ms) => calls.push(['sleep', String(ms)]),
  };
}

/** Run the tool in-process against a fixture checkout, with its console captured. */
function runTool(root, argv, { env = {}, io = null } = {}) {
  const lines = [];
  const saved = { log: console.log, error: console.error };
  console.log = (...args) => lines.push(args.join(' '));
  console.error = (...args) => lines.push(args.join(' '));
  let status;
  try {
    status = main([...argv, '--root', root], env, io);
  } finally {
    console.log = saved.log;
    console.error = saved.error;
  }
  return { status, out: lines.join('\n') };
}

/** Run the tool as npm does, in a child process; GITHUB_ACTIONS is left out unless given. */
function spawnTool(argv, env = {}) {
  const childEnv = { ...process.env, ...env };
  if (!('GITHUB_ACTIONS' in env)) delete childEnv.GITHUB_ACTIONS;
  const result = spawnSync(process.execPath, [TOOL, ...argv], { encoding: 'utf8', env: childEnv });
  return { status: result.status, out: result.stdout + result.stderr };
}

const RELEASING_MISSING = 'missing from the list (a quality.yaml job reports it)';
const RELEASING_EXTRA = 'listed, but no quality.yaml job reports it';
const RULESET_MISSING = 'reported by a quality.yaml job, but not required, so it gates nothing';
const RULESET_EXTRA = 'required, but no quality.yaml job reports it';

function quoted(list) {
  return list.map((name) => `\`${name}\``).join(', ');
}

/** A drift result: exit 1, a line naming exactly the missing checks and one naming exactly the extra ones (none when empty). */
function assertDrift(result, { missing, extra }, labels) {
  assert.strictEqual(result.status, 1, result.out);
  const line = (label) => result.out.split('\n').find((text) => text.startsWith(`  ${label}`));
  for (const [label, list] of [
    [labels.missing, missing],
    [labels.extra, extra],
  ]) {
    if (list.length === 0) assert.strictEqual(line(label), undefined, result.out);
    else assert.ok(line(label) && line(label).endsWith(`: ${quoted(list)}`), `no "${label}: ${quoted(list)}" line in:\n${result.out}`);
  }
}

// --- Check names from quality.yaml ---

test('a job is named by its name: or else its key; a one-dimension matrix gives one check per value', () => {
  assert.deepStrictEqual(expectedChecks(workflowText(JOBS)), CHECKS);
});

test('a matrix job with a name: is named "<name> (<value>)"', () => {
  const jobs = { test: { ...JOBS.test, name: 'Tests' } };
  assert.deepStrictEqual(expectedChecks(workflowText(jobs)), ['Tests (ubuntu-latest)', 'Tests (windows-latest)']);
});

test('with no mode the tool prints the check names, one per line', () => {
  const result = spawnTool(['--root', makeRoot()]);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual(result.out.trimEnd().split(/\r?\n/), CHECKS);
});

/** The job shapes the tool does not handle, each with what it says about it. */
const UNHANDLED = [
  [
    'several dimensions',
    { matrix: { os: ['ubuntu-latest'], node: ['22'] } },
    /job `test`: its matrix has 2 dimensions \(os, node\), not one/,
  ],
  ['include', { matrix: { os: ['ubuntu-latest'], include: [{ os: 'macos-latest' }] } }, /job `test`: its matrix has include/],
  ['exclude', { matrix: { os: ['ubuntu-latest', 'windows-latest'], exclude: [{ os: 'windows-latest' }] } }, /its matrix has exclude/],
  [
    'an expression in place of a mapping',
    { matrix: '${{ fromJSON(needs.setup.outputs.matrix) }}' },
    /its matrix is not a mapping \(an expression\?\)/,
  ],
  ['an empty list', { matrix: { os: [] } }, /matrix\.os is not a list of values/],
  [
    'an expression as a value',
    { matrix: { os: ['${{ vars.OS }}'] } },
    /matrix\.os holds "\$\{\{ vars\.OS \}\}", which is not a plain string/,
  ],
  ['a mapping as a value', { matrix: { os: [{ name: 'ubuntu-latest' }] } }, /matrix\.os holds .* which is not a plain string/],
];

for (const [what, strategy, message] of UNHANDLED) {
  test(`a matrix with ${what}: exit 2, the job named, nothing compared`, () => {
    const root = makeRoot({ workflow: workflowText({ ...JOBS, test: { ...JOBS.test, strategy } }) });
    const result = runTool(root, ['--releasing']);
    assert.strictEqual(result.status, 2, result.out);
    assert.match(result.out, message);
    assert.match(result.out, /cannot tell which checks these jobs report, so nothing was compared/);
    assert.doesNotMatch(result.out, /disagree|lists the/);
  });
}

test('a number as a matrix value stops the tool: GitHub names 3.10 by its own reading', () => {
  const text =
    'jobs:\n  python:\n    strategy:\n      matrix:\n        python: [3.10, "3.11"]\n    runs-on: ubuntu-latest\n    steps:\n      - run: pytest\n';
  const result = runTool(makeRoot({ workflow: text }), []);
  assert.strictEqual(result.status, 2, result.out);
  assert.match(result.out, /matrix\.python holds 3\.1, which is not a plain string \(quote a number/);
});

test('an expression in name:, a reusable workflow call and a job that is not a mapping stop the tool, every one named', () => {
  const jobs = {
    ...JOBS,
    test: { ...JOBS.test, name: 'test ${{ matrix.os }}' },
    deploy: { uses: './.github/workflows/deploy.yaml' },
    odd: 'ubuntu-latest',
  };
  const result = runTool(makeRoot({ workflow: workflowText(jobs) }), []);
  assert.strictEqual(result.status, 2, result.out);
  assert.match(result.out, /job `test`: `name:` holds an expression \(test \$\{\{ matrix\.os \}\}\)/);
  assert.match(result.out, /job `deploy`: it calls a reusable workflow/);
  assert.match(result.out, /job `odd`: the job is not a mapping/);
});

test('a quality.yaml that is missing, not YAML or without jobs stops the tool', () => {
  for (const [workflow, message] of [
    [null, /quality\.yaml not found/],
    ['jobs: [unclosed\n', /quality\.yaml is not valid YAML/],
    ['name: Quality\non: push\n', /quality\.yaml has no jobs/],
  ]) {
    const result = runTool(makeRoot({ workflow }), ['--releasing']);
    assert.strictEqual(result.status, 2, result.out);
    assert.match(result.out, message);
  }
});

// --- Drift: RELEASING.md and the ruleset ---

/** Each drift of the issue: the jobs quality.yaml then holds, and the checks the lists then miss and have extra. */
const DRIFT = [
  ['a job renamed by its key', { ...JOBS, lint: undefined, eslint: JOBS.lint }, { missing: ['eslint'], extra: ['lint'] }],
  ['a job given another name', { ...JOBS, build: { ...JOBS.build, name: 'Compile' } }, { missing: ['Compile'], extra: ['Build'] }],
  ['a job removed', { ...JOBS, lint: undefined }, { missing: [], extra: ['lint'] }],
  ['a job added', { ...JOBS, docs: { 'runs-on': 'ubuntu-latest', steps: STEPS } }, { missing: ['docs'], extra: [] }],
  [
    'an os matrix value changed',
    { ...JOBS, test: { ...JOBS.test, strategy: { matrix: { os: ['ubuntu-latest', 'windows-2025'] } } } },
    { missing: ['test (windows-2025)'], extra: ['test (windows-latest)'] },
  ],
];

function withoutRemoved(jobs) {
  return Object.fromEntries(Object.entries(jobs).filter(([, job]) => job !== undefined));
}

for (const [what, jobs, drift] of DRIFT) {
  test(`${what}: RELEASING.md fails with exit 1, naming the missing and the extra checks`, () => {
    const root = makeRoot({ workflow: workflowText(withoutRemoved(jobs)) });
    const result = runTool(root, ['--releasing']);
    assertDrift(result, drift, { missing: RELEASING_MISSING, extra: RELEASING_EXTRA });
    assert.ok(result.out.startsWith(`${RELEASING} and ${WORKFLOW} disagree on the required checks:`), result.out);
    assert.ok(result.out.includes(`between ${START} and ${END}`), result.out);
  });

  test(`${what}: the ruleset fails with exit 1, naming the missing and the extra checks`, () => {
    const root = makeRoot({ workflow: workflowText(withoutRemoved(jobs)) });
    const result = runTool(root, ['--ruleset', '--repo', REPO], { io: fakeIo(CHECKS) });
    assertDrift(result, drift, { missing: RULESET_MISSING, extra: RULESET_EXTRA });
    assert.ok(result.out.startsWith(`The Default ruleset of ${REPO} and ${WORKFLOW} disagree on the required checks:`), result.out);
  });
}

test('the order of a list does not matter', () => {
  const root = makeRoot({ releasing: releasingText(CHECKS.toReversed()) });
  const releasing = runTool(root, ['--releasing']);
  assert.strictEqual(releasing.status, 0, releasing.out);
  assert.ok(releasing.out.includes(`${RELEASING} lists the 4 checks the jobs of ${WORKFLOW} report: ${quoted(CHECKS)}.`), releasing.out);
  const ruleset = runTool(root, ['--ruleset', '--repo', REPO], { io: fakeIo(CHECKS.toReversed()) });
  assert.strictEqual(ruleset.status, 0, ruleset.out);
});

test('a check RELEASING.md lists twice fails', () => {
  const result = runTool(makeRoot({ releasing: releasingText([...CHECKS, 'lint']) }), ['--releasing']);
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes('  listed more than once: `lint`'), result.out);
});

test('a RELEASING.md list the tool cannot read stops it, naming the line', () => {
  const items = CHECKS.map((check) => `- \`${check}\``);
  for (const [releasing, message] of [
    [null, /RELEASING\.md not found/],
    ['# Releasing\n\n- `lint`\n', /needs one <!-- required-checks:start --> line, then one <!-- required-checks:end --> line/],
    [[START, ...items, END, START, END].join('\n'), /needs one <!-- required-checks:start --> line/],
    [[END, ...items, START].join('\n'), /needs one <!-- required-checks:start --> line/],
    [
      [START, '', ...items, '- lint without backticks', END].join('\n'),
      /RELEASING\.md:7: not a "- `check name`" item: - lint without backticks/,
    ],
  ]) {
    const result = runTool(makeRoot({ releasing }), ['--releasing']);
    assert.strictEqual(result.status, 2, result.out);
    assert.match(result.out, message);
  }
});

test('CRLF files read the same as LF ones', () => {
  const crlf = (text) => text.replaceAll('\n', '\r\n');
  const root = makeRoot({ workflow: crlf(workflowText(JOBS)), releasing: crlf(releasingText(CHECKS)) });
  assert.ok(fs.readFileSync(path.join(root, RELEASING), 'utf8').includes('\r\n'));
  const result = runTool(root, ['--releasing']);
  assert.strictEqual(result.status, 0, result.out);
});

test('compareChecks: missing in expected order, extra and repeated in the order of the list', () => {
  assert.deepStrictEqual(compareChecks(['a', 'b', 'c'], ['d', 'c', 'c', 'a', 'e']), { missing: ['b'], extra: ['d', 'e'], repeated: ['c'] });
});

// --- The ruleset lookup ---

test('the ruleset is found by name, then read by its id', () => {
  const io = fakeIo(CHECKS);
  const result = runTool(makeRoot(), ['--ruleset', '--repo', REPO], { io });
  assert.strictEqual(result.status, 0, result.out);
  assert.ok(result.out.includes(`The Default ruleset of ${REPO} requires the 4 checks the jobs of ${WORKFLOW} report`), result.out);
  assert.deepStrictEqual(io.calls, [
    ['gh', 'api', `repos/${REPO}/rulesets`],
    ['gh', 'api', `repos/${REPO}/rulesets/5`],
  ]);
});

test('the repository comes from --repo, else $GITHUB_REPOSITORY; with neither the tool stops', () => {
  const root = makeRoot();
  const io = fakeIo(CHECKS);
  const fromEnv = runTool(root, ['--ruleset'], { env: { GITHUB_REPOSITORY: REPO }, io });
  assert.strictEqual(fromEnv.status, 0, fromEnv.out);
  assert.strictEqual(io.calls[0][2], `repos/${REPO}/rulesets`);
  const none = runTool(root, ['--ruleset'], { io: fakeIo(CHECKS) });
  assert.strictEqual(none.status, 2, none.out);
  assert.match(none.out, /--ruleset needs --repo <owner\/repo> or \$GITHUB_REPOSITORY/);
});

test('no ruleset named Default stops the tool', () => {
  const io = fakeIo(CHECKS, { list: [ok([{ name: 'Other', id: 4 }])] });
  const result = runTool(makeRoot(), ['--ruleset', '--repo', REPO], { io });
  assert.strictEqual(result.status, 2, result.out);
  assert.match(result.out, /has no ruleset named "Default"/);
});

test('a failed lookup is tried again, and six failures stop the tool with exit 2', () => {
  const flaky = fakeIo(CHECKS, { list: [DOWN, DOWN, ok([{ name: 'Default', id: 5 }])] });
  const recovered = runTool(makeRoot(), ['--ruleset', '--repo', REPO], { io: flaky });
  assert.strictEqual(recovered.status, 0, recovered.out);
  assert.strictEqual(flaky.calls.filter((call) => call[0] === 'sleep').length, 2);
  const down = fakeIo(CHECKS, { list: [DOWN] });
  const result = runTool(makeRoot(), ['--ruleset', '--repo', REPO], { io: down });
  assert.strictEqual(result.status, 2, result.out);
  assert.strictEqual(down.calls.filter((call) => call[0] === 'gh').length, 6);
  assert.strictEqual(down.calls.filter((call) => call[0] === 'sleep').length, 5);
  assert.match(result.out, /failed 6 times \(connect: connection refused\)/);
});

test('both modes at once: a drift in either one fails', () => {
  const root = makeRoot();
  const result = runTool(root, ['--releasing', '--ruleset', '--repo', REPO], { io: fakeIo(CHECKS.slice(1)) });
  assertDrift(result, { missing: ['lint'], extra: [] }, { missing: RULESET_MISSING, extra: RULESET_EXTRA });
  assert.ok(result.out.includes(`${RELEASING} lists the 4 checks`), result.out);
});

// --- Command line ---

test('in GitHub Actions a drift is also an error annotation, on the start marker for RELEASING.md', () => {
  const root = makeRoot({ workflow: workflowText(withoutRemoved({ ...JOBS, lint: undefined })) });
  const releasing = runTool(root, ['--releasing'], { env: { GITHUB_ACTIONS: 'true' } });
  assert.strictEqual(releasing.status, 1, releasing.out);
  assert.match(releasing.out, new RegExp(`^::error file=${RELEASING.replaceAll('.', String.raw`\.`)},line=5::`, 'm'));
  const ruleset = runTool(root, ['--ruleset', '--repo', REPO], { env: { GITHUB_ACTIONS: 'true' }, io: fakeIo(CHECKS) });
  assert.strictEqual(ruleset.status, 1, ruleset.out);
  assert.match(ruleset.out, /^::error::The Default ruleset of owner\/repo and/m);
  const quiet = runTool(root, ['--releasing']);
  assert.doesNotMatch(quiet.out, /::error/);
});

test('an unknown argument or a flag without its value stops the tool; --help does not', () => {
  for (const argv of [['--bogus'], ['--repo']]) {
    const result = spawnTool(argv);
    assert.strictEqual(result.status, 2, result.out);
    assert.match(result.out, /Usage: node tools\/check-required-checks\.js/);
  }
  const help = spawnTool(['--help']);
  assert.strictEqual(help.status, 0, help.out);
  assert.match(help.out, /--ruleset/);
});

// --- This repository ---

test('the jobs of quality.yaml report the checks RELEASING.md lists', () => {
  const expected = expectedChecks(realText(WORKFLOW));
  const { checks } = documentedChecks(realText(RELEASING));
  assert.deepStrictEqual(expected.toSorted(), checks.toSorted());
  const result = spawnTool(['--releasing']);
  assert.strictEqual(result.status, 0, result.out);
});

test('an os matrix value changed in quality.yaml fails against RELEASING.md', () => {
  const workflow = realText(WORKFLOW);
  const matrix = 'os: [ubuntu-latest, windows-latest]';
  assert.ok(workflow.includes(matrix), `${WORKFLOW} holds no ${matrix}`);
  const root = makeRoot({ workflow: workflow.replace(matrix, 'os: [ubuntu-latest, windows-2025]'), releasing: realText(RELEASING) });
  const result = runTool(root, ['--releasing']);
  assertDrift(
    result,
    { missing: ['validate (windows-2025)'], extra: ['validate (windows-latest)'] },
    { missing: RELEASING_MISSING, extra: RELEASING_EXTRA },
  );
});

test('every pull request runs the check inside a required check, and so does the release', () => {
  const scripts = JSON.parse(realText('package.json')).scripts;
  const chain = scripts['test:docs-links-tool'].split(' && ');
  assert.ok(chain.includes('node test/test-check-required-checks.js'), scripts['test:docs-links-tool']);
  assert.ok(chain.includes('node tools/check-required-checks.js --releasing'), scripts['test:docs-links-tool']);
  const validate = YAML.parse(realText(WORKFLOW)).jobs.validate;
  assert.ok(
    validate.steps.some((step) => step.run === 'npm run test:docs-links-tool'),
    'the validate job runs npm run test:docs-links-tool',
  );
  // The validate job's own checks are required, so a failure there blocks the merge.
  const { checks } = documentedChecks(realText(RELEASING));
  assert.ok(
    expectedChecks(realText(WORKFLOW))
      .filter((check) => check.startsWith('validate ('))
      .every((check) => checks.includes(check)),
    checks.join(', '),
  );
  // release.yaml's Run tests and validation step runs npm test.
  assert.ok(scripts.test.split(' && ').includes('npm run test:docs-links-tool'), scripts.test);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
