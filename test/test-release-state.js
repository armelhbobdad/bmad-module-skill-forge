/**
 * Tests for tools/release-state.js
 *
 * `npm run test:changes-tool` runs this file after test/test-changes.js, so
 * the required em-dash job runs it on every pull request. release.yaml asks
 * the tool what version_bump=resume still has to do for the version main
 * carries, and whether another version_bump would skip past it (issue #566).
 * These tests pin:
 * - the resume decision on given states: the six cases of the issue (no
 *   tag; the tag on the merge commit; the tag elsewhere; npm has the version
 *   but there is no Release; everything present; no merged bot PR), a ref
 *   other than main, where the tag goes when main moved while the release
 *   waited, a squash merge, a required check that is not green or never
 *   ran, and what each refusal tells the maintainer to do;
 * - the guard on given states: minor and major over an unpublished version
 *   refused with a message that names resume, patch and the prereleases
 *   allowed, and no refusal once npm has the version or when no release
 *   commit carries it (a hand bump);
 * - both commands end to end on throwaway repositories with an origin, in a
 *   fresh clone as actions/checkout makes it, with real git and gh and npm
 *   answering from a table: the tag anchor, a squash-merged head fetched
 *   from refs/pull/<n>/head, the --base and --date of the notes (the stable
 *   tag before the version even when its own tag is on the release commit),
 *   the step outputs, what the summary says to do if the run stops later,
 *   the lookups a decision never needs, and a lookup that keeps failing
 *   (exit 2 after six tries).
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const releaseState = require(path.join(__dirname, '..', 'tools', 'release-state.js'));
const { nextVersion } = require(path.join(__dirname, '..', 'tools', 'changes.js'));

const REPO = 'owner/repo';
const HEAD = 'a'.repeat(40);
const MERGE = 'b'.repeat(40);
const DISPATCH = 'c'.repeat(40);
const OTHER = 'd'.repeat(40);
const BRANCH = 'release/bot/v3.0.0-42-1';
const REQUIRED = ['lint', 'validate (ubuntu-latest)'];

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

// --- Given states ---

function run(name, conclusion, startedAt, status = 'completed') {
  return { name, status, conclusion, started_at: startedAt, html_url: `https://github.com/${REPO}/runs/${name}@${startedAt}` };
}

const GREEN_RUNS = REQUIRED.map((name) => run(name, 'success', '2026-09-30T10:00:00Z'));

/** A cut from main whose bot PR #7 merged with a merge commit while main did not move, and nothing after the merge ran. */
function cutState(overrides = {}) {
  return {
    ref: 'refs/heads/main',
    version: '3.0.0',
    npm: false,
    tag: null,
    release: false,
    prs: [{ number: 7, branch: BRANCH, headSha: HEAD, mergeSha: MERGE }],
    commits: { headVersion: '3.0.0', headParent: DISPATCH, mergeParent: DISPATCH, headInMerge: true, mergeOnMain: true },
    checks: { required: REQUIRED, runs: GREEN_RUNS },
    base: 'v2.2.0',
    date: '2026-09-30',
    ...overrides,
  };
}

function refused(plan, ...parts) {
  assert.ok(plan.refusal, `expected a refusal, got ${JSON.stringify(plan)}`);
  for (const part of parts) assert.ok(plan.refusal.includes(part), `refusal lacks "${part}": ${plan.refusal}`);
}

// --- resume, the six cases of the issue ---

test('no tag: tag the merge commit, publish and create the Release', () => {
  const plan = releaseState.decideResume(cutState());
  assert.strictEqual(plan.refusal, undefined, plan.refusal);
  assert.deepStrictEqual(
    { done: plan.done, createTag: plan.createTag, publish: plan.publish, createRelease: plan.createRelease },
    { done: false, createTag: true, publish: true, createRelease: true },
  );
  assert.strictEqual(plan.anchor, MERGE);
  assert.strictEqual(plan.anchorKind, 'merge commit');
  assert.deepStrictEqual([plan.base, plan.date], ['v2.2.0', '2026-09-30']);
});

test('the tag on the merge commit: keep it, publish and create the Release', () => {
  const plan = releaseState.decideResume(cutState({ tag: MERGE }));
  assert.strictEqual(plan.refusal, undefined, plan.refusal);
  assert.deepStrictEqual([plan.createTag, plan.publish, plan.createRelease], [false, true, true]);
});

test('the tag elsewhere: refused, naming the commit the tag step would use', () => {
  // The tag recovery the old Scenario E gave: the run's head_sha, main before the bump.
  const plan = releaseState.decideResume(cutState({ tag: DISPATCH }));
  refused(plan, 'v3.0.0 points at ccccccc', 'merge commit bbbbbbb', 'git push --delete origin v3.0.0', 'dispatch resume again');
});

test('npm has the version but there is no Release: create only the Release', () => {
  const plan = releaseState.decideResume(cutState({ npm: true, tag: MERGE, checks: undefined }));
  assert.strictEqual(plan.refusal, undefined, plan.refusal);
  assert.deepStrictEqual([plan.createTag, plan.publish, plan.createRelease], [false, false, true]);
});

test('everything present: nothing to do, and no bot PR needed', () => {
  const plan = releaseState.decideResume({ ref: 'refs/heads/main', version: '2.2.0', npm: true, tag: MERGE, release: true });
  assert.deepStrictEqual(plan, { done: true, version: '2.2.0' });
  assert.deepStrictEqual(releaseState.resumeOutputs(plan), {
    version: '2.2.0',
    done: 'true',
    create_tag: 'false',
    publish: 'false',
    create_release: 'false',
  });
});

test('no merged bot PR: refused', () => {
  const plan = releaseState.decideResume(cutState({ prs: [], commits: undefined }));
  refused(plan, 'no bot PR titled "release: bump to v3.0.0" was merged into main', 'no release commit to finish', 'is not a cut');
});

// --- resume, the rest ---

test('a ref other than main: refused before anything else, even with nothing missing', () => {
  const plan = releaseState.decideResume({ ref: 'refs/heads/feat/x', version: '3.0.0', npm: true, tag: MERGE, release: true });
  refused(plan, 'runs from main only', 'refs/heads/feat/x');
});

test('a version that is not valid semver: refused', () => {
  refused(releaseState.decideResume(cutState({ version: 'v3.0.0' })), 'not a valid semantic version');
});

test('main moved while the release waited: the tag goes on the release commit', () => {
  const plan = releaseState.decideResume(cutState({ commits: { ...cutState().commits, mergeParent: OTHER } }));
  assert.strictEqual(plan.refusal, undefined, plan.refusal);
  assert.strictEqual(plan.anchor, HEAD);
  assert.strictEqual(plan.anchorKind, 'release commit');
});

test('main moved: a tag already on the release commit is kept, one on the merge commit is refused', () => {
  const moved = { ...cutState().commits, mergeParent: OTHER };
  assert.strictEqual(releaseState.decideResume(cutState({ commits: moved, tag: HEAD })).createTag, false);
  refused(releaseState.decideResume(cutState({ commits: moved, tag: MERGE })), 'not at the release commit aaaaaaa');
});

test('squash-merged while main did not move: the tag goes on the squash commit', () => {
  const plan = releaseState.decideResume(cutState({ commits: { ...cutState().commits, headInMerge: false } }));
  assert.strictEqual(plan.refusal, undefined, plan.refusal);
  assert.strictEqual(plan.anchor, MERGE);
});

test('squash- or rebase-merged after main moved: refused, ship forward with patch', () => {
  const plan = releaseState.decideResume(cutState({ commits: { ...cutState().commits, mergeParent: OTHER, headInMerge: false } }));
  refused(plan, 'not merged with a merge commit', 'is not on main', 'version_bump=patch', 'Scenario H');
});

test('a required check that is not green: refused, each one named, when npm does not have the version', () => {
  const runs = [
    run('lint', 'success', '2026-09-30T10:00:00Z'),
    run('lint', 'failure', '2026-09-30T11:00:00Z'),
    run('prettier', null, '2026-09-30T11:00:00Z', 'in_progress'),
  ];
  const plan = releaseState.decideResume(cutState({ checks: { required: ['lint', 'prettier', 'eslint'], runs } }));
  refused(plan, 'lint (failure, https://', 'prettier (in_progress)', 'eslint (no run)', 'Re-run a flaky check', 'version_bump=patch');
});

test('a required check with no run on the release commit: the refusal says how to start the checks there', () => {
  const plan = releaseState.decideResume(cutState({ checks: { required: [...REQUIRED, 'em-dash'], runs: GREEN_RUNS } }));
  refused(
    plan,
    'em-dash (no run)',
    `start the checks with gh workflow run quality.yaml --ref ${BRANCH}`,
    `git push origin ${HEAD}:refs/heads/${BRANCH}`,
    'then dispatch resume again',
  );
  // A check that ran has a run page to re-run it from.
  const red = releaseState.decideResume(
    cutState({ checks: { required: REQUIRED, runs: [run('lint', 'failure', '2026-09-30T10:00:00Z'), GREEN_RUNS[1]] } }),
  );
  refused(red, 'Re-run a flaky check from its run page');
  assert.ok(!red.refusal.includes('gh workflow run quality.yaml'), red.refusal);
});

test('npm lacks the version and the checks were not read: refused, never taken as green', () => {
  refused(releaseState.decideResume(cutState({ checks: undefined })), 'were not read');
  refused(releaseState.decideResume(cutState({ checks: { required: [], runs: GREEN_RUNS } })), 'were not read');
});

test('the checks are not read once npm has the version', () => {
  const plan = releaseState.decideResume(cutState({ npm: true, checks: undefined }));
  assert.strictEqual(plan.refusal, undefined, plan.refusal);
  assert.strictEqual(plan.publish, false);
});

test('two merged bot PRs of the version: refused', () => {
  const prs = [
    { number: 7, branch: BRANCH, headSha: HEAD, mergeSha: MERGE },
    { number: 9, branch: 'release/bot/v3.0.0-43-1', headSha: OTHER, mergeSha: DISPATCH },
  ];
  refused(releaseState.decideResume(cutState({ prs })), '2 merged bot PRs', '#7, #9');
});

test('a release commit that holds another version, or a merge commit off main: refused', () => {
  refused(releaseState.decideResume(cutState({ commits: { ...cutState().commits, headVersion: '2.2.0' } })), 'holds the version 2.2.0');
  refused(releaseState.decideResume(cutState({ commits: { ...cutState().commits, mergeOnMain: false } })), 'is not on main');
});

test('a Release to create needs the base and the date of the notes; an existing one does not', () => {
  refused(releaseState.decideResume(cutState({ base: null })), 'no --base');
  refused(releaseState.decideResume(cutState({ date: null })), 'no --date');
  const plan = releaseState.decideResume(cutState({ release: true, base: null, date: null }));
  assert.strictEqual(plan.refusal, undefined, plan.refusal);
  assert.strictEqual(plan.createRelease, false);
});

test('checks: the newest run of a context wins; skipped and neutral are green, stale and cancelled are not', () => {
  const runs = [
    run('a', 'failure', '2026-09-30T10:00:00Z'),
    run('a', 'success', '2026-09-30T12:00:00Z'),
    run('b', 'skipped', '2026-09-30T10:00:00Z'),
    run('c', 'neutral', '2026-09-30T10:00:00Z'),
    run('d', 'stale', '2026-09-30T10:00:00Z'),
    run('e', 'cancelled', '2026-09-30T10:00:00Z'),
  ];
  const problems = releaseState.checksNotGreen(['a', 'b', 'c', 'd', 'e'], runs);
  assert.deepStrictEqual(
    problems.map((problem) => problem.split(' ')[0]),
    ['d', 'e'],
  );
});

// --- guard ---

function guardState(bump, overrides = {}) {
  const version = overrides.version || '3.0.0';
  return { bump, version, next: nextVersion(version, bump), releaseCommit: 'e'.repeat(40), npm: false, ...overrides };
}

test('guard: major and minor over an unpublished version are refused, naming resume and patch', () => {
  for (const [bump, next] of [
    ['major', '4.0.0'],
    ['minor', '3.1.0'],
  ]) {
    const verdict = releaseState.decideGuard(guardState(bump));
    refused(verdict, `${bump} gives ${next}, past v3.0.0`, 'version_bump=resume', 'version_bump=patch', 'Scenario H');
  }
});

test('guard: patch and the prereleases stay within the major.minor and pass', () => {
  for (const bump of ['patch', 'alpha', 'beta', 'rc']) {
    const verdict = releaseState.decideGuard(guardState(bump));
    assert.ok(verdict.pass && verdict.pass.includes('within the major.minor'), `${bump}: ${JSON.stringify(verdict)}`);
  }
});

test('guard: no refusal once npm has the version, or when no release commit carries it', () => {
  assert.ok(releaseState.decideGuard(guardState('major', { npm: true })).pass);
  assert.ok(releaseState.decideGuard(guardState('major', { releaseCommit: null })).pass);
});

test('guard: an unpublished prerelease cut is skipped only by a higher major.minor', () => {
  // major and minor from 3.0.0-rc.1 give 3.0.0, the same line; major from 2.3.0-rc.1 gives 3.0.0.
  assert.ok(releaseState.decideGuard(guardState('minor', { version: '3.0.0-rc.1' })).pass);
  assert.ok(releaseState.decideGuard(guardState('major', { version: '3.0.0-rc.1' })).pass);
  refused(releaseState.decideGuard(guardState('major', { version: '2.3.0-rc.1' })), 'major gives 3.0.0, past v2.3.0-rc.1');
});

// --- End to end, on throwaway repositories ---

/** Environment for git: no inherited repository or CI markers, and a fixed identity. */
function cleanEnv(extra = {}) {
  const env = { ...process.env };
  for (const key of ['GIT_DIR', 'GIT_INDEX_FILE', 'GIT_WORK_TREE', 'GITHUB_ACTIONS', 'GITHUB_OUTPUT', 'GITHUB_STEP_SUMMARY'])
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

function git(root, args, extra = {}) {
  return execFileSync('git', ['-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', '-c', 'core.hooksPath=/dev/null', ...args], {
    cwd: root,
    env: cleanEnv(extra),
    encoding: 'utf8',
    stdio: 'pipe',
  }).trim();
}

function write(root, files) {
  for (const [rel, body] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), body);
  }
}

function commit(root, message, extra = {}) {
  git(root, ['add', '-A']);
  git(root, ['commit', '-q', '-m', message], extra);
  return git(root, ['rev-parse', 'HEAD']);
}

function packageJson(version) {
  return `${JSON.stringify({ name: 'example-tool', version }, null, 2)}\n`;
}

function changelog(blocks) {
  return ['# Changelog', '', '## [Unreleased]', '', ...blocks.flatMap((block) => [block, '', '- a change', '']), ''].join('\n');
}

const V220 = '## [2.2.0](https://github.com/owner/repo/compare/v2.1.0...v2.2.0) (2026-09-22)';

/**
 * An origin holding main at v2.2.0, one more change (the commit the cut
 * was dispatched from), the release commit on its bot branch (also at
 * refs/pull/7/head, as GitHub keeps it) and the bot PR merged into main as
 * `merge` says ('merge' or 'squash'). `moved` merges another pull request
 * into main first. Returns the commits and a fresh clone of the origin.
 */
function makeCut({ version = '3.0.0', merge = 'merge', moved = false, releaseDate = null } = {}) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'skf-release-state-'));
  tmpRoots.push(base);
  const origin = path.join(base, 'origin.git');
  const work = path.join(base, 'work');
  git(base, ['init', '-q', '--bare', '-b', 'main', origin]);
  git(base, ['init', '-q', '-b', 'main', work]);
  git(work, ['remote', 'add', 'origin', origin]);
  write(work, { 'package.json': packageJson('2.2.0'), 'CHANGELOG.md': changelog([V220]) });
  commit(work, 'release: bump to v2.2.0');
  git(work, ['tag', '-a', 'v2.2.0', '-m', 'Release v2.2.0']);
  write(work, { 'feature.txt': 'a feature\n' });
  const dispatch = commit(work, 'feat: a feature');
  const branch = `release/bot/v${version}-42-1`;
  git(work, ['checkout', '-q', '-b', branch]);
  const heading = `## [${version}](https://github.com/owner/repo/compare/v2.2.0...v${version}) (2026-09-30)`;
  const isPrerelease = version.includes('-');
  write(work, { 'package.json': packageJson(version), 'CHANGELOG.md': changelog(isPrerelease ? [V220] : [heading, V220]) });
  const dateEnv = releaseDate ? { GIT_COMMITTER_DATE: releaseDate, GIT_AUTHOR_DATE: releaseDate } : {};
  const head = commit(work, `release: bump to v${version}`, dateEnv);
  git(work, ['checkout', '-q', 'main']);
  if (moved) {
    write(work, { 'other.txt': 'another pull request\n' });
    commit(work, 'fix: another pull request');
  }
  if (merge === 'merge') {
    git(work, ['merge', '-q', '--no-ff', '-m', `Merge pull request #7 from owner/${branch}`, branch]);
  } else {
    git(work, ['merge', '-q', '--squash', branch]);
    commit(work, `release: bump to v${version} (#7)`);
  }
  const mergeSha = git(work, ['rev-parse', 'HEAD']);
  git(work, ['push', '-q', 'origin', 'main', '--tags']);
  git(work, ['push', '-q', 'origin', `${head}:refs/pull/7/head`]);
  if (merge === 'merge') git(work, ['push', '-q', 'origin', branch]);
  // --no-local: a local clone would copy every object of the origin, refs/pull/7/head's included.
  const checkout = path.join(base, 'checkout');
  git(base, ['clone', '-q', '--no-local', origin, checkout]);
  return { base, origin, work, checkout, dispatch, head, merge: mergeSha, version, branch };
}

/**
 * Put the tag on `sha` on origin, as a run's tag step (or a hand recovery)
 * would, and fetch it into the clone: actions/checkout (fetch-depth: 0)
 * brings every tag to a resume run dispatched after the tag was pushed.
 */
function pushTag(cut, sha) {
  git(cut.work, ['tag', '-a', `v${cut.version}`, '-m', `Release v${cut.version}`, sha]);
  git(cut.work, ['push', '-q', 'origin', `v${cut.version}`]);
  git(cut.checkout, ['fetch', '-q', '--tags', 'origin']);
}

const ok = (data) => ({ status: 0, stdout: JSON.stringify(data), stderr: '' });
const NOT_FOUND = { status: 1, stdout: '{"message":"Not Found","status":"404"}', stderr: 'gh: Not Found (HTTP 404)\n' };
const DOWN = { status: 1, stdout: '', stderr: 'connect: connection refused\n' };

function botPr(cut, overrides = {}) {
  return {
    number: 7,
    title: `release: bump to v${cut.version}`,
    headRefName: cut.branch,
    headRefOid: cut.head,
    mergeCommit: { oid: cut.merge },
    isCrossRepository: false,
    ...overrides,
  };
}

/**
 * gh and npm answering from a table: each route answers the calls whose
 * joined arguments contain its `match`, in order, repeating its last answer.
 */
function fakeIo(cut, { published = ['2.2.0'], release = false, prs = null, checks = GREEN_RUNS, npm = null } = {}) {
  const calls = [];
  const routes = {
    gh: [
      { match: 'pr list', answers: [ok(prs || [botPr(cut)])] },
      { match: `releases/tags/v${cut.version}`, answers: [release ? ok({ tag_name: `v${cut.version}` }) : NOT_FOUND] },
      {
        match: `repos/${REPO}/rulesets/5`,
        answers: [
          ok({
            rules: [{ type: 'required_status_checks', parameters: { required_status_checks: REQUIRED.map((context) => ({ context })) } }],
          }),
        ],
      },
      { match: `repos/${REPO}/rulesets`, answers: [ok([{ name: 'Default', id: 5 }])] },
      { match: '/check-runs?per_page=100 --paginate --slurp', answers: [ok([{ total_count: checks.length, check_runs: checks }])] },
    ],
    npm: [{ match: 'view example-tool versions --json', answers: npm || [ok(published)] }],
  };
  const answer = (tool) => (args) => {
    calls.push([tool, ...args]);
    const line = args.join(' ');
    const route = routes[tool].find((candidate) => line.includes(candidate.match));
    if (!route) return { status: 97, stdout: '', stderr: `no route for ${tool} ${line}` };
    route.count = (route.count || 0) + 1;
    return route.answers[Math.min(route.count, route.answers.length) - 1];
  };
  return {
    calls,
    git: (args) => {
      calls.push(['git', ...args]);
      const result = spawnSync('git', args, { cwd: cut.checkout, env: cleanEnv(), encoding: 'utf8' });
      return { status: result.status, stdout: result.stdout || '', stderr: result.stderr || '' };
    },
    gh: answer('gh'),
    npm: answer('npm'),
    sleep: (ms) => calls.push(['sleep', String(ms)]),
  };
}

/** Run a command of the tool in-process against the clone, with its console captured. */
function runTool(cut, io, argv, env = {}) {
  const output = path.join(cut.base, `output-${Math.random().toString(36).slice(2)}.txt`);
  const lines = [];
  const saved = { log: console.log, error: console.error };
  console.log = (...args) => lines.push(args.join(' '));
  console.error = (...args) => lines.push(args.join(' '));
  let status;
  try {
    status = releaseState.main(
      [...argv, '--root', cut.checkout],
      { GITHUB_REF: 'refs/heads/main', GITHUB_REPOSITORY: REPO, GITHUB_OUTPUT: output, ...env },
      io,
    );
  } finally {
    Object.assign(console, saved);
  }
  const written = fs.existsSync(output) ? fs.readFileSync(output, 'utf8') : '';
  const outputs = Object.fromEntries(
    written
      .split('\n')
      .filter(Boolean)
      .map((line) => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]),
  );
  return { status, out: lines.join('\n'), outputs };
}

function called(io, tool, part) {
  return io.calls.filter((call) => call[0] === tool && call.slice(1).join(' ').includes(part));
}

test('resume end to end: a cut that stopped after the merge gets its tag, publish and Release', () => {
  const cut = makeCut();
  const io = fakeIo(cut);
  const result = runTool(cut, io, ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual(result.outputs, {
    version: '3.0.0',
    done: 'false',
    create_tag: 'true',
    publish: 'true',
    create_release: 'true',
    pr_number: '7',
    head_sha: cut.head,
    merge_sha: cut.merge,
    anchor: cut.merge,
    anchor_kind: 'merge commit',
    base: 'v2.2.0',
    date: '2026-09-30',
  });
  assert.deepStrictEqual(Object.keys(result.outputs), releaseState.RESUME_OUTPUTS);
  assert.ok(result.out.includes(`Tag v3.0.0: missing; resume tags the merge commit ${cut.merge}.`), result.out);
  // The PR is found by its exact title, from main, merged.
  const [list] = called(io, 'gh', 'pr list');
  assert.ok(list.join(' ').includes('--state merged --base main --search "release: bump to v3.0.0" in:title'), list.join(' '));
});

test('resume end to end: everything present exits without a decision to publish, and reads no bot PR', () => {
  const cut = makeCut();
  pushTag(cut, cut.merge);
  const io = fakeIo(cut, { published: ['2.2.0', '3.0.0'], release: true });
  const result = runTool(cut, io, ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual(result.outputs, {
    version: '3.0.0',
    done: 'true',
    create_tag: 'false',
    publish: 'false',
    create_release: 'false',
  });
  assert.ok(result.out.includes('nothing to finish, and nothing is published'), result.out);
  assert.deepStrictEqual(called(io, 'gh', 'pr list'), []);
  assert.deepStrictEqual(called(io, 'gh', 'check-runs'), []);
});

test('resume end to end: the tag on the merge commit is kept', () => {
  const cut = makeCut();
  pushTag(cut, cut.merge);
  const result = runTool(cut, fakeIo(cut), ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual([result.outputs.create_tag, result.outputs.publish, result.outputs.create_release], ['false', 'true', 'true']);
});

test('resume end to end: a tag on the dispatch commit is refused', () => {
  const cut = makeCut();
  pushTag(cut, cut.dispatch);
  const result = runTool(cut, fakeIo(cut), ['resume'], { GITHUB_ACTIONS: 'true' });
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes(`::error::The resume path refuses: v3.0.0 points at ${cut.dispatch.slice(0, 7)}`), result.out);
  assert.ok(result.out.includes('Nothing was tagged, published or released.'), result.out);
  assert.deepStrictEqual(result.outputs, {});
});

test('resume end to end: npm has the version and the tag is there, so only the Release, and no check is read', () => {
  const cut = makeCut();
  pushTag(cut, cut.merge);
  const io = fakeIo(cut, { published: ['2.2.0', '3.0.0'] });
  const result = runTool(cut, io, ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual([result.outputs.create_tag, result.outputs.publish, result.outputs.create_release], ['false', 'false', 'true']);
  assert.deepStrictEqual(called(io, 'gh', 'rulesets'), []);
  assert.deepStrictEqual(called(io, 'gh', 'check-runs'), []);
});

test('resume end to end: no merged bot PR is refused, and a PR from a fork or another branch does not count', () => {
  const cut = makeCut();
  const prs = [
    botPr(cut, { isCrossRepository: true }),
    botPr(cut, { headRefName: 'feat/bump' }),
    botPr(cut, { title: 'release: bump to v3.0.0-rc.1' }),
  ];
  const result = runTool(cut, fakeIo(cut, { prs }), ['resume']);
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes('no bot PR titled "release: bump to v3.0.0" was merged into main'), result.out);
});

test('resume end to end: a ref other than main is refused before any lookup', () => {
  const cut = makeCut();
  const io = fakeIo(cut);
  const result = runTool(cut, io, ['resume', '--ref', 'refs/heads/feat/x']);
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes('runs from main only'), result.out);
  assert.deepStrictEqual(io.calls, []);
});

test('resume end to end: main moved while the release waited, so the tag goes on the release commit', () => {
  const cut = makeCut({ moved: true });
  const result = runTool(cut, fakeIo(cut), ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.strictEqual(result.outputs.anchor, cut.head);
  assert.strictEqual(result.outputs.anchor_kind, 'release commit');
});

test('resume end to end: main moved and the tag is on the release commit, so the notes start at the stable tag before it', () => {
  // The run tagged the release commit and its publish failed. git describe
  // from that commit names v3.0.0 itself, and the notes step would refuse
  // 3.0.0 as not above its base.
  const cut = makeCut({ moved: true });
  pushTag(cut, cut.head);
  const result = runTool(cut, fakeIo(cut), ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual(
    [result.outputs.create_tag, result.outputs.anchor, result.outputs.anchor_kind, result.outputs.base],
    ['false', cut.head, 'release commit', 'v2.2.0'],
  );
});

test('resume end to end: the summary says what to do if the run stops later, the dry-run case only when it publishes', () => {
  const cut = makeCut();
  const summary = path.join(cut.base, 'summary.md');
  const result = runTool(cut, fakeIo(cut), ['resume'], { GITHUB_STEP_SUMMARY: summary });
  assert.strictEqual(result.status, 0, result.out);
  const text = fs.readFileSync(summary, 'utf8');
  assert.ok(text.startsWith(`## Resume v3.0.0\n\n- Bot PR #7: release commit ${cut.head}`), text);
  const again = 'If the resume run stops before it finishes, dispatch version_bump=resume again: it keeps what is done and does the rest.';
  const dryRun =
    'A pre-publish dry-run that rejects the package fails the same way on every dispatch: ship 3.0.0 forward with ' +
    'version_bump=patch instead (docs/_internal/RELEASING.md, Scenario H).';
  for (const where of [result.out, text]) {
    assert.ok(where.includes(`${again} ${dryRun}`), where);
  }
  // npm has the version, so there is no dry-run; with nothing missing, nothing can stop.
  pushTag(cut, cut.merge);
  const published = runTool(cut, fakeIo(cut, { published: ['2.2.0', '3.0.0'] }), ['resume']);
  assert.ok(published.out.includes(again), published.out);
  assert.ok(!published.out.includes('dry-run'), published.out);
  const done = runTool(cut, fakeIo(cut, { published: ['2.2.0', '3.0.0'], release: true }), ['resume']);
  assert.strictEqual(done.outputs.done, 'true', done.out);
  assert.ok(!done.out.includes('dispatch version_bump=resume again'), done.out);
});

test('resume end to end: a squash merge with main unmoved tags the squash commit, and the head is fetched from refs/pull/7/head', () => {
  const cut = makeCut({ merge: 'squash' });
  assert.notStrictEqual(spawnSync('git', ['cat-file', '-e', `${cut.head}^{commit}`], { cwd: cut.checkout, env: cleanEnv() }).status, 0);
  const io = fakeIo(cut);
  const result = runTool(cut, io, ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.strictEqual(result.outputs.anchor, cut.merge);
  assert.strictEqual(result.outputs.head_sha, cut.head);
  assert.strictEqual(called(io, 'git', 'fetch --quiet --no-tags origin refs/pull/7/head').length, 1);
});

test('resume end to end: a squash merge after main moved is refused', () => {
  const cut = makeCut({ merge: 'squash', moved: true });
  const result = runTool(cut, fakeIo(cut), ['resume']);
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes('was not merged with a merge commit'), result.out);
});

test('resume end to end: a red required check on the release commit is refused while npm lacks the version', () => {
  const cut = makeCut();
  const checks = [run('lint', 'success', '2026-09-30T10:00:00Z'), run('validate (ubuntu-latest)', 'failure', '2026-09-30T10:00:00Z')];
  const io = fakeIo(cut, { checks });
  const result = runTool(cut, io, ['resume']);
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes('validate (ubuntu-latest) (failure'), result.out);
  assert.strictEqual(called(io, 'gh', `commits/${cut.head}/check-runs`).length, 1);
});

test('resume end to end: a required check that never ran is started on the bot PR head branch', () => {
  const cut = makeCut();
  const result = runTool(cut, fakeIo(cut, { checks: [run('lint', 'success', '2026-09-30T10:00:00Z')] }), ['resume']);
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes('validate (ubuntu-latest) (no run)'), result.out);
  assert.ok(result.out.includes(`gh workflow run quality.yaml --ref ${cut.branch} `), result.out);
});

test('resume end to end: a prerelease cut takes its notes date from the release commit, in UTC', () => {
  const cut = makeCut({ version: '3.0.0-rc.1', releaseDate: '2026-09-30T01:30:00+02:00' });
  const result = runTool(cut, fakeIo(cut), ['resume']);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual([result.outputs.base, result.outputs.date], ['v2.2.0', '2026-09-29']);
});

test('resume end to end: npm is read again after a failure, and six failures stop with exit 2', () => {
  const cut = makeCut();
  const flaky = fakeIo(cut, { npm: [DOWN, DOWN, ok(['2.2.0'])] });
  const recovered = runTool(cut, flaky, ['resume']);
  assert.strictEqual(recovered.status, 0, recovered.out);
  assert.strictEqual(called(flaky, 'sleep', '10000').length, 2);
  const down = fakeIo(cut, { npm: [DOWN] });
  const result = runTool(cut, down, ['resume']);
  assert.strictEqual(result.status, 2, result.out);
  assert.strictEqual(called(down, 'npm', 'view').length, 6);
  // One wait between tries, none after the last.
  assert.strictEqual(called(down, 'sleep', '10000').length, 5);
  assert.ok(result.out.includes('failed 6 times (connect: connection refused)'), result.out);
  assert.deepStrictEqual(result.outputs, {});
});

test('guard end to end: major over an unpublished release commit on main is refused; patch reads nothing', () => {
  const cut = makeCut();
  const io = fakeIo(cut);
  const result = runTool(cut, io, ['guard', '--bump', 'major'], { GITHUB_ACTIONS: 'true' });
  assert.strictEqual(result.status, 1, result.out);
  assert.ok(result.out.includes('::error::major gives 4.0.0, past v3.0.0'), result.out);
  assert.ok(result.out.includes(`(commit ${cut.head.slice(0, 7)}, "release: bump to v3.0.0")`), result.out);
  const patchIo = fakeIo(cut);
  const patch = runTool(cut, patchIo, ['guard', '--bump', 'patch']);
  assert.strictEqual(patch.status, 0, patch.out);
  assert.deepStrictEqual(patchIo.calls, []);
});

test('guard end to end: a squash-merged release commit counts, and a published version passes', () => {
  const cut = makeCut({ merge: 'squash' });
  const refusedRun = runTool(cut, fakeIo(cut), ['guard', '--bump', 'minor']);
  assert.strictEqual(refusedRun.status, 1, refusedRun.out);
  assert.ok(refusedRun.out.includes(`(commit ${cut.merge.slice(0, 7)}, "release: bump to v3.0.0")`), refusedRun.out);
  const published = runTool(cut, fakeIo(cut, { published: ['2.2.0', '3.0.0'] }), ['guard', '--bump', 'major']);
  assert.strictEqual(published.status, 0, published.out);
  assert.ok(published.out.includes('npm has 3.0.0'), published.out);
});

test('guard end to end: a hand-set version with no release commit passes without reading npm', () => {
  const cut = makeCut();
  write(cut.checkout, { 'package.json': packageJson('3.1.0-rc.0') });
  commit(cut.checkout, 'chore: set 3.1.0-rc.0 by hand');
  const io = fakeIo(cut);
  const result = runTool(cut, io, ['guard', '--bump', 'major']);
  assert.strictEqual(result.status, 0, result.out);
  assert.deepStrictEqual(called(io, 'npm', 'view'), []);
});

test('usage: a missing or unknown bump, and an unknown command, exit 2', () => {
  const cut = makeCut();
  assert.strictEqual(runTool(cut, fakeIo(cut), ['guard']).status, 2);
  assert.strictEqual(runTool(cut, fakeIo(cut), ['guard', '--bump', 'resume']).status, 2);
  assert.strictEqual(runTool(cut, fakeIo(cut), ['publish']).status, 2);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
