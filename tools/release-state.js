/**
 * Release State
 *
 * What release.yaml may do about the version main carries (issue #566).
 * Once the bot PR of a cut dispatched from main merges, main's package.json
 * holds the new version V, and the tag, the npm publish and the GitHub
 * Release still have to run. A run that stops in that window (a failed
 * publish, a required check that fails after an admin merge, a
 * cancellation) leaves a V that npm never received, and every later
 * version_bump bumps past it. This tool reads main, npm, the tag, the
 * GitHub Release and the merged bot PR, and decides.
 *
 * Commands:
 *   resume   What version_bump=resume still has to do for V. When the tag
 *            vV, V on npm and the GitHub Release are all there, nothing:
 *            the run exits without publishing. Otherwise it needs the one
 *            merged bot PR titled "release: bump to vV" (from this
 *            repository's release/bot/ branch into main) and refuses:
 *            - a dispatch ref other than main, or a V that is not a valid
 *              semantic version;
 *            - no such PR, or more than one;
 *            - a release commit (the PR's head, the tree a normal run
 *              publishes) whose package.json holds another version, or a
 *              merge commit main does not reach;
 *            - a release commit main does not reach while the merge commit
 *              does not follow the commit the release was cut from (a
 *              squash or rebase merge after main moved);
 *            - a tag that points anywhere but the commit the Create and
 *              push tag step would use: the merge commit when its first
 *              parent is the release commit's (main did not move while the
 *              release waited), else the release commit;
 *            - when npm does not have V, a required check (the Default
 *              ruleset's list) whose newest run on the release commit is
 *              not green (success, skipped or neutral, as in the Wait for
 *              required status checks step);
 *            - when the GitHub Release is missing, no stable tag before vV
 *              reachable from the release commit, or for a stable V no
 *              dated "## [V]" heading in its CHANGELOG.md: the notes would
 *              have no --base or no --date.
 *            Each refusal says why and, where there is one, what to do
 *            instead. Otherwise it writes the step outputs
 *            RESUME_OUTPUTS: done, what to do (create_tag, publish,
 *            create_release), the PR, the tag anchor, and the --base and
 *            --date of the release notes: the last stable tag before vV
 *            reachable from the release commit, and the date of V's
 *            CHANGELOG.md heading there (a prerelease has none, so the
 *            release commit's date, in UTC).
 *   guard    --bump <type>. Refuses a version_bump that gives a higher
 *            major.minor than V while main's history holds the release
 *            commit of V ("release: bump to vV", or the squash subject
 *            "release: bump to vV (#<n>)") and npm does not have V: the bump
 *            would skip past a cut that resume can still publish. A bump
 *            within V's major.minor (patch, the prereleases) passes without
 *            a lookup, and so does a V that no release commit carries (a
 *            hand bump such as 3.0.0-rc.0).
 *
 * Every lookup goes through an io object (git, gh, npm, sleep), so the
 * tests give the state without a network. A failed lookup is tried again,
 * six times ten seconds apart, and then the command exits 2 without a
 * decision.
 *
 * Usage:
 *   node tools/release-state.js resume [--ref <ref>] [--repo <owner/repo>]
 *   node tools/release-state.js guard --bump <alpha|beta|rc|patch|minor|major>
 *
 * --ref defaults to $GITHUB_REF and --repo to $GITHUB_REPOSITORY; --root
 * <dir> reads another checkout (the tests use this). The step outputs go to
 * $GITHUB_OUTPUT and the report to $GITHUB_STEP_SUMMARY when they are set.
 * Outside Actions, where neither is, both commands only print (resume may
 * fetch the bot PR's commits), so a maintainer can run them on an
 * up-to-date main checkout to see what a dispatch would do
 * (docs/_internal/RELEASING.md).
 *
 * Exit codes:
 *   0  resume: the outputs are written (nothing to do included); guard: the
 *      bump is allowed
 *   1  refused: the message says why and, where there is one, what to do
 *      instead
 *   2  cannot run: a bad argument, or a lookup that kept failing
 */

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
// Dev-only tool: semver is a devDependency, and changes.js needs yaml as well
// (both release.yaml steps that run this tool come after npm ci).
const semver = require('semver');
const { BUMPS, nextVersion } = require('./changes.js');

const MAIN_REF = 'refs/heads/main';
const TRIES = 6;
const RETRY_MS = 10_000;
const SHA = /^[0-9a-f]{40}$/;
// The release commit's subject, which is also its bot PR's title, and the
// temp branch, as release.yaml writes them (Commit version bump, Open bot
// PR, Push commit to temp branch); test-release-workflow.py checks the
// workflow against both.
const BOT_SUBJECT_PREFIX = 'release: bump to v';
const BOT_BRANCH_PREFIX = 'release/bot/v';
// The conclusions the Wait for required status checks step counts as green;
// any other one is not. Keep the two in step (test-release-workflow.py
// compares them).
const GREEN_CONCLUSIONS = ['success', 'skipped', 'neutral'];
const GREEN = new Set(GREEN_CONCLUSIONS);
const SCENARIO = 'docs/_internal/RELEASING.md, Scenario H';
// Every output of `resume`, in the order it writes them; release.yaml reads them as steps.resume.outputs.<name>.
const RESUME_OUTPUTS = [
  'version',
  'done',
  'create_tag',
  'publish',
  'create_release',
  'pr_number',
  'head_sha',
  'merge_sha',
  'anchor',
  'anchor_kind',
  'base',
  'date',
];

class ToolError extends Error {
  constructor(message, exitCode = 2) {
    super(message);
    this.exitCode = exitCode;
  }
}

// --- Commands the lookups run ---

function runCommand(command, args, root) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    // npm is a .cmd shim on Windows, which only a shell runs; the arguments are fixed words.
    shell: command === 'npm' && process.platform === 'win32',
  });
  if (result.error) return { status: null, stdout: '', stderr: result.error.message };
  return { status: result.status, stdout: result.stdout || '', stderr: result.stderr || '' };
}

/** The real git, gh and npm, run in the checkout; the tests pass their own. */
function defaultIo(root) {
  return {
    git: (args) => runCommand('git', ['-c', 'core.quotePath=false', ...args], root),
    gh: (args) => runCommand('gh', args, root),
    npm: (args) => runCommand('npm', args, root),
    sleep: (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms),
  };
}

function firstLine(text) {
  return String(text || '')
    .trim()
    .split('\n')[0];
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function short(sha) {
  return String(sha || '').slice(0, 7);
}

function escapeRegExp(text) {
  return text.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

/**
 * Run a lookup until it answers: TRIES tries, RETRY_MS apart. `attempt`
 * returns {ok: true, value} or {ok: false, error}.
 */
function retry(io, what, attempt) {
  let error = '';
  for (let tryNumber = 1; tryNumber <= TRIES; tryNumber += 1) {
    const result = attempt();
    if (result.ok) return result.value;
    error = result.error;
    if (tryNumber < TRIES) {
      console.log(`${what} failed (try ${tryNumber} of ${TRIES}); retrying: ${error}`);
      io.sleep(RETRY_MS);
    }
  }
  throw new ToolError(`${what} failed ${TRIES} times (${error}). Nothing was decided; dispatch again.`);
}

function failure(result, tool) {
  return { ok: false, error: firstLine(result.stderr) || `${tool} exited with ${result.status}` };
}

// --- Lookups ---

function readPackage(root) {
  const pkg = parseJson(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  if (!pkg || typeof pkg.name !== 'string') throw new ToolError('package.json has no package name.');
  return { name: pkg.name, version: typeof pkg.version === 'string' ? pkg.version : '' };
}

/** A valid semantic version in its canonical form, as the version step of release.yaml requires. */
function isCanonicalVersion(version) {
  return typeof version === 'string' && semver.valid(version) === version;
}

/** Every version of the package on npm. */
function npmVersions(io, name) {
  return retry(io, `Reading the versions of ${name} on npm`, () => {
    const result = io.npm(['view', name, 'versions', '--json']);
    const data = result.status === 0 ? parseJson(result.stdout) : null;
    // npm prints a lone version as a string, not as a list.
    if (typeof data === 'string') return { ok: true, value: [data] };
    if (Array.isArray(data) && data.every((version) => typeof version === 'string')) return { ok: true, value: data };
    return failure(result, 'npm');
  });
}

/** The commit a tag points at on origin, the tag object peeled, or null when origin has no such tag. */
function remoteTag(io, tag) {
  return retry(io, `Looking up the tag ${tag} on origin`, () => {
    const result = io.git(['ls-remote', 'origin', `refs/tags/${tag}`, `refs/tags/${tag}^{}`]);
    if (result.status !== 0) return failure(result, 'git');
    const refs = new Map();
    for (const line of result.stdout.split('\n')) {
      const [sha, ref] = line.trim().split('\t');
      if (SHA.test(sha || '') && ref) refs.set(ref, sha);
    }
    return { ok: true, value: refs.get(`refs/tags/${tag}^{}`) || refs.get(`refs/tags/${tag}`) || null };
  });
}

/** Whether the GitHub Release of a tag exists (gh answers HTTP 404 when it does not). */
function releaseExists(io, repo, tag) {
  return retry(io, `Looking up the GitHub Release ${tag}`, () => {
    const result = io.gh(['api', `repos/${repo}/releases/tags/${tag}`]);
    if (result.status === 0) {
      const data = parseJson(result.stdout);
      if (data && data.tag_name === tag) return { ok: true, value: true };
      return { ok: false, error: 'the answer names no release' };
    }
    if (/\(HTTP 404\)/.test(result.stderr)) return { ok: true, value: false };
    return failure(result, 'gh');
  });
}

/** The merged bot PRs of a version, each {number, branch, headSha, mergeSha}. */
function mergedBotPrs(io, repo, version) {
  const title = `${BOT_SUBJECT_PREFIX}${version}`;
  const found = retry(io, `Looking up the merged bot PR "${title}"`, () => {
    const result = io.gh([
      'pr',
      'list',
      '--repo',
      repo,
      '--state',
      'merged',
      '--base',
      'main',
      '--search',
      `"${title}" in:title`,
      '--json',
      'number,title,headRefName,headRefOid,mergeCommit,isCrossRepository',
      '--limit',
      '50',
    ]);
    const data = result.status === 0 ? parseJson(result.stdout) : null;
    return Array.isArray(data) ? { ok: true, value: data } : failure(result, 'gh');
  });
  // The search matches words, so the title is compared exactly; the branch is the one release.yaml pushes.
  return found
    .filter(
      (pr) =>
        pr &&
        pr.title === title &&
        pr.isCrossRepository === false &&
        String(pr.headRefName || '').startsWith(`${BOT_BRANCH_PREFIX}${version}-`) &&
        SHA.test(pr.headRefOid || '') &&
        pr.mergeCommit &&
        SHA.test(pr.mergeCommit.oid || ''),
    )
    .map((pr) => ({ number: pr.number, branch: pr.headRefName, headSha: pr.headRefOid, mergeSha: pr.mergeCommit.oid }));
}

function ghJson(io, what, args, valid) {
  return retry(io, what, () => {
    const result = io.gh(args);
    const data = result.status === 0 ? parseJson(result.stdout) : null;
    return data !== null && valid(data) ? { ok: true, value: data } : failure(result, 'gh');
  });
}

/** The required status checks of the Default ruleset, found by name as the Wait for required status checks step does. */
function requiredContexts(io, repo) {
  const rulesets = ghJson(io, `Listing the rulesets of ${repo}`, ['api', `repos/${repo}/rulesets`], Array.isArray);
  const ruleset = rulesets.find((candidate) => candidate && candidate.name === 'Default');
  if (!ruleset) throw new ToolError(`${repo} has no ruleset named "Default", so its required checks are unknown.`);
  const detail = ghJson(
    io,
    'Reading the ruleset "Default"',
    ['api', `repos/${repo}/rulesets/${ruleset.id}`],
    (data) => typeof data === 'object' && Array.isArray(data.rules),
  );
  const contexts = detail.rules
    .filter((rule) => rule && rule.type === 'required_status_checks')
    .flatMap((rule) => ((rule.parameters && rule.parameters.required_status_checks) || []).map((check) => check.context))
    .filter((context) => typeof context === 'string' && context !== '');
  if (contexts.length === 0) throw new ToolError(`The ruleset "Default" of ${repo} lists no required status check.`);
  return contexts;
}

/** Every check-run on a commit, over every page. */
function checkRuns(io, repo, sha) {
  const pages = ghJson(
    io,
    `Reading the check-runs on ${sha}`,
    ['api', `repos/${repo}/commits/${sha}/check-runs?per_page=100`, '--paginate', '--slurp'],
    (data) => Array.isArray(data) && data.every((page) => page && Array.isArray(page.check_runs)),
  );
  return pages.flatMap((page) => page.check_runs);
}

function gitText(io, args) {
  const result = io.git(args);
  return result.status === 0 ? result.stdout.trim() : null;
}

function hasCommit(io, sha) {
  return io.git(['cat-file', '-e', `${sha}^{commit}`]).status === 0;
}

/** Fetch a commit the checkout lacks: a squash-merged PR's head is only on refs/pull/<n>/head. */
function ensureCommit(io, sha, refspec) {
  if (hasCommit(io, sha)) return;
  retry(io, `Fetching ${short(sha)} from origin`, () => {
    const result = io.git(['fetch', '--quiet', '--no-tags', 'origin', refspec]);
    if (hasCommit(io, sha)) return { ok: true, value: true };
    return result.status === 0 ? { ok: false, error: `origin ${refspec} does not hold ${sha}` } : failure(result, 'git');
  });
}

function isAncestor(io, ancestor, descendant) {
  const result = io.git(['merge-base', '--is-ancestor', ancestor, descendant]);
  if (result.status === 0 || result.status === 1) return result.status === 0;
  throw new ToolError(`git merge-base failed: ${firstLine(result.stderr)}`);
}

/** What git says about the bot PR's release commit and merge commit. */
function readCommits(io, pr) {
  ensureCommit(io, pr.headSha, `refs/pull/${pr.number}/head`);
  ensureCommit(io, pr.mergeSha, pr.mergeSha);
  const pkg = parseJson(gitText(io, ['show', `${pr.headSha}:package.json`]) || '');
  return {
    headVersion: pkg && typeof pkg.version === 'string' ? pkg.version : null,
    headParent: gitText(io, ['rev-parse', '--verify', '--quiet', `${pr.headSha}^1`]),
    mergeParent: gitText(io, ['rev-parse', '--verify', '--quiet', `${pr.mergeSha}^1`]),
    headInMerge: isAncestor(io, pr.headSha, pr.mergeSha),
    mergeOnMain: isAncestor(io, pr.mergeSha, 'HEAD'),
  };
}

/**
 * The last stable tag before v<version> reachable from a commit: the --base
 * of the notes, as for the cut itself. v<version> is excluded by name: when
 * main moved while the cut waited, the tag step put it on the release commit
 * itself, where git describe would otherwise name it.
 */
function stableTagBefore(io, version, commit) {
  return (
    gitText(io, ['describe', '--tags', '--abbrev=0', '--match', 'v[0-9]*', '--exclude', '*-*', '--exclude', `v${version}`, commit]) || null
  );
}

/** The date of the notes: V's CHANGELOG.md heading at the commit, or for a prerelease the commit's date in UTC. */
function notesDate(io, version, commit) {
  if (semver.prerelease(version) === null) {
    const changelog = gitText(io, ['show', `${commit}:CHANGELOG.md`]) || '';
    const heading = new RegExp(String.raw`^## \[${escapeRegExp(version)}\]\([^)]*\) \((\d{4}-\d{2}-\d{2})\)\s*$`, 'm');
    const match = changelog.match(heading);
    return match ? match[1] : null;
  }
  const when = new Date(gitText(io, ['log', '-1', '--format=%cI', commit]) || '');
  return Number.isNaN(when.getTime()) ? null : when.toISOString().slice(0, 10);
}

// --- resume ---

/**
 * Everything the resume decision reads. Lookups stop once the answer is
 * known: a ref other than main needs none, a complete release needs no bot
 * PR, and the required checks are read only when npm does not have V.
 */
function gatherResume(io, { root, ref, repo }) {
  const { name, version } = readPackage(root);
  const state = { ref, version };
  if (ref !== MAIN_REF || !isCanonicalVersion(version)) return state;
  if (!repo) throw new ToolError('resume needs --repo <owner/repo> or GITHUB_REPOSITORY.');
  const tag = `v${version}`;
  state.npm = npmVersions(io, name).includes(version);
  state.tag = remoteTag(io, tag);
  state.release = releaseExists(io, repo, tag);
  if (state.npm && state.tag && state.release) return state;
  state.prs = mergedBotPrs(io, repo, version);
  if (state.prs.length !== 1) return state;
  const [pr] = state.prs;
  state.commits = readCommits(io, pr);
  if (!state.npm) state.checks = { required: requiredContexts(io, repo), runs: checkRuns(io, repo, pr.headSha) };
  if (!state.release) {
    state.base = stableTagBefore(io, version, pr.headSha);
    state.date = notesDate(io, version, pr.headSha);
  }
  return state;
}

/** The required contexts whose newest check-run is not green: most-recent-wins and the GREEN set, as in the Wait step. */
function checksNotGreen(required, runs) {
  const problems = [];
  for (const context of required) {
    const newest = runs
      .filter((run) => run && run.name === context)
      .toSorted((a, b) => String(a.started_at || '').localeCompare(String(b.started_at || '')))
      .at(-1);
    if (!newest) problems.push(`${context} (no run)`);
    else if (newest.status !== 'completed') problems.push(`${context} (${newest.status})`);
    else if (!GREEN.has(newest.conclusion))
      problems.push(`${context} (${newest.conclusion}${newest.html_url ? `, ${newest.html_url}` : ''})`);
  }
  return problems;
}

function refuse(reason) {
  return { refusal: reason };
}

/**
 * What version_bump=resume does, from a state gatherResume shape.
 *
 * @returns {{refusal: string} | {done: true, version: string} | {done: false, version: string, createTag: boolean,
 *   publish: boolean, createRelease: boolean, pr: object, anchor: string, anchorKind: string, base: string|null,
 *   date: string|null}}
 */
function decideResume(state) {
  const { ref, version } = state;
  if (ref !== MAIN_REF) {
    return refuse(
      `version_bump=resume finishes the cut main carries, so it runs from main only; this run was dispatched from ${ref || 'an unknown ref'}.`,
    );
  }
  if (!isCanonicalVersion(version)) {
    return refuse(
      `main's package.json holds the version "${version}", which is not a valid semantic version, so there is no cut to finish.`,
    );
  }
  const tag = `v${version}`;
  if (state.tag && state.npm && state.release) return { done: true, version };
  const prs = state.prs || [];
  const title = `${BOT_SUBJECT_PREFIX}${version}`;
  if (prs.length === 0) {
    return refuse(
      `main carries ${version}, but no bot PR titled "${title}" was merged into main, so there is no release commit to finish. ` +
        `A version set by hand, such as 3.0.0-rc.0, is not a cut: dispatch its channel, which cuts the next one.`,
    );
  }
  if (prs.length > 1) {
    return refuse(
      `${prs.length} merged bot PRs are titled "${title}" (${prs.map((pr) => `#${pr.number}`).join(', ')}), so resume cannot tell which one to finish.`,
    );
  }
  const [pr] = prs;
  const commits = state.commits || {};
  if (commits.headVersion !== version) {
    return refuse(
      `the release commit ${short(pr.headSha)} of bot PR #${pr.number} holds the version ${commits.headVersion || '(none)'} in package.json, not ${version}.`,
    );
  }
  if (!commits.mergeOnMain) return refuse(`the merge commit ${short(pr.mergeSha)} of bot PR #${pr.number} is not on main.`);
  // The rule of the Create and push tag step of release.yaml, which compares
  // the merge commit's first parent with the dispatch commit, the release
  // commit's parent. Keep the two in step: a resumed cut must tag the commit
  // a cut that did not stop would have tagged.
  let anchor = pr.mergeSha;
  let anchorKind = 'merge commit';
  if (!commits.mergeParent || commits.mergeParent !== commits.headParent) {
    if (!commits.headInMerge) {
      return refuse(
        `main moved while the release of ${version} waited, and bot PR #${pr.number} was not merged with a merge commit, so its release commit ` +
          `${short(pr.headSha)} is not on main and has no commit to tag. Ship ${version} forward with version_bump=patch (${SCENARIO}).`,
      );
    }
    anchor = pr.headSha;
    anchorKind = 'release commit';
  }
  if (state.tag && state.tag !== anchor) {
    return refuse(
      `${tag} points at ${short(state.tag)}, not at the ${anchorKind} ${short(anchor)} of bot PR #${pr.number}, where the Create and push tag step puts it. ` +
        `Check it (git show ${tag}:package.json should hold ${version}); if it is wrong, delete it (git push --delete origin ${tag}) and dispatch resume again, which tags the ${anchorKind}.`,
    );
  }
  if (!state.npm) {
    if (!state.checks || state.checks.required.length === 0) {
      return refuse(`npm does not have ${version}, and the required checks on its release commit ${short(pr.headSha)} were not read.`);
    }
    const problems = checksNotGreen(state.checks.required, state.checks.runs);
    if (problems.length > 0) {
      // A check with no run never started on the release commit (say, the
      // PR merged before the run dispatched the checks), so it has no run
      // page to re-run it from.
      const unstarted = problems.some((problem) => problem.endsWith(' (no run)'))
        ? ` A check with no run never started there: start the checks with gh workflow run quality.yaml --ref ${pr.branch} ` +
          `(if that branch is gone, push it again first: git push origin ${pr.headSha}:refs/heads/${pr.branch}), then dispatch resume again.`
        : '';
      return refuse(
        `npm does not have ${version}, and not every required check on its release commit ${short(pr.headSha)} is green: ${problems.join('; ')}. ` +
          `Re-run a flaky check from its run page, then dispatch resume again; for a defect, fix it on main by pull request and ship ${version} forward with version_bump=patch (${SCENARIO}).${unstarted}`,
      );
    }
  }
  if (!state.release && !state.base) {
    return refuse(`no stable tag before ${tag} is reachable from the release commit ${short(pr.headSha)}, so the notes have no --base.`);
  }
  if (!state.release && !state.date) {
    return refuse(
      `CHANGELOG.md at the release commit ${short(pr.headSha)} has no dated "## [${version}]" heading, so the notes have no --date.`,
    );
  }
  return {
    done: false,
    version,
    createTag: !state.tag,
    publish: !state.npm,
    createRelease: !state.release,
    pr,
    anchor,
    anchorKind,
    base: state.release ? null : state.base,
    date: state.release ? null : state.date,
  };
}

/** The step outputs of a resume decision, keyed as RESUME_OUTPUTS. */
function resumeOutputs(plan) {
  const flag = (value) => (value ? 'true' : 'false');
  if (plan.done) {
    return { version: plan.version, done: 'true', create_tag: 'false', publish: 'false', create_release: 'false' };
  }
  return {
    version: plan.version,
    done: 'false',
    create_tag: flag(plan.createTag),
    publish: flag(plan.publish),
    create_release: flag(plan.createRelease),
    pr_number: String(plan.pr.number),
    head_sha: plan.pr.headSha,
    merge_sha: plan.pr.mergeSha,
    anchor: plan.anchor,
    anchor_kind: plan.anchorKind,
    base: plan.base || '',
    date: plan.date || '',
  };
}

/**
 * What resume does, one line per part, for the log and the step summary. The
 * lines name the resume run, not "this run": a maintainer also runs the
 * command by hand to read the tag's commit and the notes' --base and --date.
 */
function resumeLines(plan) {
  const tag = `v${plan.version}`;
  if (plan.done)
    return [
      `${tag} is tagged, ${plan.version} is on npm and the GitHub Release ${tag} exists: nothing to finish, and nothing is published.`,
    ];
  const { pr } = plan;
  return [
    `Bot PR #${pr.number}: release commit ${pr.headSha}, merge commit ${pr.mergeSha}.`,
    plan.createTag
      ? `Tag ${tag}: missing; resume tags the ${plan.anchorKind} ${plan.anchor}.`
      : `Tag ${tag}: on the ${plan.anchorKind} ${plan.anchor}; kept.`,
    plan.publish
      ? `npm ${plan.version}: missing; resume publishes it from the release commit, whose required checks are green.`
      : `npm ${plan.version}: published; not published again.`,
    plan.createRelease
      ? `GitHub Release ${tag}: missing; resume creates it, with the notes from ${plan.base} dated ${plan.date}.`
      : `GitHub Release ${tag}: exists; kept.`,
  ];
}

/**
 * What to do when the resume run fails after its resume step. Nothing later
 * in the run says it: the last step cleans up only after a cut that pushed a
 * temp branch, and the Summary step runs only when every step succeeded.
 */
function resumeRetry(plan) {
  const dryRun = plan.publish
    ? ` A pre-publish dry-run that rejects the package fails the same way on every dispatch: ship ${plan.version} forward with version_bump=patch instead (${SCENARIO}).`
    : '';
  return `If the resume run stops before it finishes, dispatch version_bump=resume again: it keeps what is done and does the rest.${dryRun}`;
}

// --- guard ---

/** main's release commit of the version: "release: bump to v<version>", or the subject a squash merge gives it. */
function releaseCommit(io, version) {
  const subject = `${BOT_SUBJECT_PREFIX}${version}`;
  const squashed = new RegExp(String.raw`^${escapeRegExp(subject)} \(#\d+\)$`);
  const result = io.git(['log', '--format=%H %s', '--fixed-strings', `--grep=${subject}`, 'HEAD']);
  if (result.status !== 0) throw new ToolError(`git log failed: ${firstLine(result.stderr)}`);
  for (const line of result.stdout.split('\n')) {
    const space = line.indexOf(' ');
    const text = line.slice(space + 1);
    if (space > 0 && (text === subject || squashed.test(text))) return line.slice(0, space);
  }
  return null;
}

/** True when `to` has a higher major.minor than `from`. */
function passesMinor(from, to) {
  return semver.major(to) > semver.major(from) || (semver.major(to) === semver.major(from) && semver.minor(to) > semver.minor(from));
}

/** Everything the guard reads; a bump within V's major.minor reads nothing. */
function gatherGuard(io, { root, bump }) {
  const { name, version } = readPackage(root);
  const state = { bump, version, next: nextVersion(version, bump) };
  if (!passesMinor(version, state.next)) return state;
  state.releaseCommit = releaseCommit(io, version);
  if (state.releaseCommit) state.npm = npmVersions(io, name).includes(version);
  return state;
}

/**
 * Whether a version_bump may go on, from a state gatherGuard shapes.
 *
 * @returns {{refusal: string} | {pass: string}}
 */
function decideGuard(state) {
  const { bump, version, next } = state;
  if (!passesMinor(version, next)) return { pass: `${bump} gives ${next}, within the major.minor of ${version}.` };
  if (!state.releaseCommit) {
    return {
      pass: `${bump} gives ${next}; main's ${version} came from no release run (no "${BOT_SUBJECT_PREFIX}${version}" commit), so no cut is left to finish.`,
    };
  }
  if (state.npm) return { pass: `${bump} gives ${next}; npm has ${version}, so no cut is left to finish.` };
  return refuse(
    `${bump} gives ${next}, past v${version}, which main carries from a merged release run (commit ${short(state.releaseCommit)}, ` +
      `"${BOT_SUBJECT_PREFIX}${version}") and which npm does not have. Finish v${version} first: dispatch release.yaml on main with ` +
      `version_bump=resume, which tags, publishes and creates the GitHub Release of v${version}, each only if missing. If v${version} ` +
      `cannot be published, ship it forward with version_bump=patch (${SCENARIO}).`,
  );
}

// --- Commands ---

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1] || null;
}

function annotate(env, level, message) {
  if (env.GITHUB_ACTIONS === 'true') console.log(`::${level}::${message.replaceAll('\n', ' ')}`);
}

function appendTo(file, text) {
  if (!file) return;
  fs.appendFileSync(file, text);
}

function runResume(root, argv, env, io) {
  const ref = argValue(argv, '--ref') || env.GITHUB_REF || '';
  const repo = argValue(argv, '--repo') || env.GITHUB_REPOSITORY || '';
  const plan = decideResume(gatherResume(io, { root, ref, repo }));
  if (plan.refusal) {
    console.log(`The resume path refuses: ${plan.refusal}`);
    console.log('Nothing was tagged, published or released.');
    annotate(env, 'error', `The resume path refuses: ${plan.refusal}`);
    appendTo(env.GITHUB_STEP_SUMMARY, `## Resume refused\n\n${plan.refusal}\n\nNothing was tagged, published or released.\n`);
    return 1;
  }
  const lines = resumeLines(plan);
  const retry = plan.done ? '' : resumeRetry(plan);
  console.log(
    [`Resume v${plan.version}, the version main carries:`, ...lines.map((line) => `  ${line}`), retry].filter(Boolean).join('\n'),
  );
  const outputs = resumeOutputs(plan);
  appendTo(
    env.GITHUB_OUTPUT,
    Object.entries(outputs)
      .map(([key, value]) => `${key}=${value}\n`)
      .join(''),
  );
  appendTo(
    env.GITHUB_STEP_SUMMARY,
    `## Resume v${plan.version}\n\n${lines.map((line) => `- ${line}`).join('\n')}\n${retry ? `\n${retry}\n` : ''}`,
  );
  return 0;
}

function runGuard(root, argv, env, io) {
  const bump = argValue(argv, '--bump');
  if (!bump) throw new ToolError(`guard needs --bump <${BUMPS.join('|')}>.`);
  const verdict = decideGuard(gatherGuard(io, { root, bump }));
  if (verdict.refusal) {
    console.log(`Refused: ${verdict.refusal}`);
    console.log('Nothing was committed.');
    annotate(env, 'error', verdict.refusal);
    appendTo(env.GITHUB_STEP_SUMMARY, `### Unpublished release on main\n\n**Refused:** ${verdict.refusal}\n`);
    return 1;
  }
  console.log(verdict.pass);
  return 0;
}

const USAGE = `Usage: node tools/release-state.js <command> [options]

  resume [--ref <ref>] [--repo <owner/repo>]   what version_bump=resume still has to do for main's version
  guard --bump <type>                          refuse a bump past a version main carries and npm does not have

  <type> is one of ${BUMPS.join(', ')}.
  --ref defaults to $GITHUB_REF, --repo to $GITHUB_REPOSITORY; --root <dir>
  reads another checkout. Outside Actions ($GITHUB_OUTPUT and
  $GITHUB_STEP_SUMMARY unset) both commands only print: run them on an
  up-to-date main checkout to see what a dispatch would do.`;

function main(argv = process.argv.slice(2), env = process.env, io = null) {
  const [command, ...rest] = argv;
  const root = path.resolve(argValue(rest, '--root') || path.join(__dirname, '..'));
  try {
    switch (command) {
      case 'resume': {
        return runResume(root, rest, env, io || defaultIo(root));
      }
      case 'guard': {
        return runGuard(root, rest, env, io || defaultIo(root));
      }
      case '--help':
      case '-h': {
        console.log(USAGE);
        return 0;
      }
      default: {
        if (command) console.error(`Unknown command: ${command}\n`);
        console.error(USAGE);
        return 2;
      }
    }
  } catch (error) {
    // changes.js's nextVersion throws its own error class, with the same exitCode.
    if (!error || !Number.isInteger(error.exitCode)) throw error;
    console.error(`error: ${error.message}`);
    annotate(env, 'error', error.message);
    return error.exitCode;
  }
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  BOT_BRANCH_PREFIX,
  BOT_SUBJECT_PREFIX,
  GREEN_CONCLUSIONS,
  MAIN_REF,
  RESUME_OUTPUTS,
  checksNotGreen,
  decideGuard,
  decideResume,
  gatherGuard,
  gatherResume,
  main,
  notesDate,
  passesMinor,
  releaseCommit,
  resumeOutputs,
};
