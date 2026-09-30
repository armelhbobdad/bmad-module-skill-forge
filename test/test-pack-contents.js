/**
 * Tests for the npm package's file list
 *
 * What ships is decided by the .npmignore blocklist: package.json has no
 * `files` allowlist, so a new maintainer-only file ships unless someone adds
 * a rule for it. This file packs the working tree with `npm pack --dry-run
 * --json --ignore-scripts`, leaves out the files git ignores there, and fails
 * on every packed path outside ALLOWED, and on every REQUIRED file missing
 * from the pack, naming each one. `npm run test:install` runs it, so the
 * validate job of quality.yaml runs it on Linux and Windows for every pull
 * request; paths are compared with forward slashes on both.
 *
 * The same rule also runs on fixed lists, and on throwaway packages that
 * carry the repository's package.json and .npmignore: one holding the
 * maintainer-only files those must keep out, and one with stray files they
 * miss plus an added rule that drops files the package needs.
 *
 * A new file the package must ship outside ALLOWED goes into ALLOWED, and
 * into REQUIRED when the package cannot do without it. A new maintainer-only
 * file takes an .npmignore rule instead.
 */

const assert = require('node:assert');
const { spawnSync, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const REPO = path.join(__dirname, '..');

/** The paths the package may ship: `<folder>/**` takes every file under the folder, any other entry is one file. */
const ALLOWED = [
  'src/**',
  'tools/cli/**',
  'tools/skf-npx-wrapper.js',
  'docs/**',
  '.claude-plugin/marketplace.json',
  'package.json',
  'README.md',
  'LICENSE',
];

/** Maintainer-only files inside an ALLOWED folder. */
const EXCLUDED = new Set(['docs/_internal/RELEASING.md']);

/**
 * Files the package must ship: the npx wrapper that package.json's bin points
 * at, the CLI it runs, the module config the installer reads and the tool
 * version list it copies to _bmad/skf/shared/, without which the installed
 * package cannot run, and the public API contract, which says it ships.
 */
const REQUIRED = [
  'tools/skf-npx-wrapper.js',
  'tools/cli/skf-cli.js',
  'src/module.yaml',
  'src/shared/tool-requirements.yaml',
  'docs/_internal/STABILITY.md',
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

/** Whether the package may ship `file`, a path from the package root with forward slashes. */
function isAllowed(file) {
  if (EXCLUDED.has(file)) return false;
  return ALLOWED.some((pattern) => (pattern.endsWith('/**') ? file.startsWith(pattern.slice(0, -2)) : file === pattern));
}

/**
 * One message per problem with a pack list: each packed path the package may
 * not ship, in sorted order, then each REQUIRED file the list lacks. Empty
 * when the list is right. A backslash reads as a forward slash, so a Windows
 * list compares the same.
 */
function packProblems(files) {
  const packed = files.map((file) => file.replaceAll('\\', '/')).toSorted();
  return [
    ...packed.filter((file) => !isAllowed(file)).map((file) => `packed, but not a file the package may ship: ${file}`),
    ...REQUIRED.filter((file) => !packed.includes(file)).map((file) => `missing from the pack, and the package needs it: ${file}`),
  ];
}

/**
 * The paths `npm pack` puts in the package built from `root`, with forward
 * slashes. --ignore-scripts keeps the prepare script (husky) from running.
 * Under `npm run`, npm_execpath is npm's own CLI script, which this node runs
 * without a shell on every platform; run directly, the test starts the npm on
 * PATH through a shell, which Windows needs for npm.cmd.
 */
function packedFiles(root) {
  const args = ['pack', '--dry-run', '--json', '--ignore-scripts'];
  const options = { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 };
  const npmCli = process.env.npm_execpath;
  const result =
    npmCli && /npm-cli\.c?js$/.test(npmCli)
      ? spawnSync(process.execPath, [npmCli, ...args], options)
      : spawnSync(`npm ${args.join(' ')}`, { ...options, shell: true });
  if (result.error) throw result.error;
  assert.strictEqual(result.status, 0, `npm pack exited ${result.status} in ${root}:\n${result.stderr}`);
  const [pack] = JSON.parse(result.stdout);
  return pack.files.map((file) => file.path.replaceAll('\\', '/'));
}

/** The environment git runs in, plus `extra`: no GIT_DIR, GIT_INDEX_FILE or GIT_WORK_TREE from a hook, so git finds the checkout from its working folder. */
function gitEnv(extra = {}) {
  const env = { ...process.env, ...extra };
  for (const key of ['GIT_DIR', 'GIT_INDEX_FILE', 'GIT_WORK_TREE']) delete env[key];
  return env;
}

/**
 * `files` without the paths git ignores in `root`. npm reads the root
 * .npmignore in place of .gitignore, so a pack of a working tree also takes
 * the local files .gitignore keeps out of commits (.mcp.json, .serena/,
 * coverage/ and the like), which the fresh checkout a release packs does not
 * have. check-ignore never reports a tracked file, so every committed file is
 * still checked. Outside a git checkout, or without git, `files` comes back
 * whole.
 */
function withoutGitIgnored(root, files, env = gitEnv()) {
  const result = spawnSync('git', ['check-ignore', '--stdin', '-z'], { cwd: root, env, input: files.join('\0'), encoding: 'utf8' });
  // Exit 0: git ignores some of the paths, 1: none of them; 128: no git checkout.
  if (result.error || (result.status !== 0 && result.status !== 1)) return files;
  const ignored = new Set(result.stdout.split('\0'));
  return files.filter((file) => !ignored.has(file));
}

/**
 * A throwaway package with the repository's package.json and .npmignore (plus
 * `extraRules`, appended) and the given files, each holding its own path.
 */
function makePackage(files, extraRules = []) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pack-contents-'));
  tmpRoots.push(root);
  fs.copyFileSync(path.join(REPO, 'package.json'), path.join(root, 'package.json'));
  const rules = fs.readFileSync(path.join(REPO, '.npmignore'), 'utf8');
  fs.writeFileSync(path.join(root, '.npmignore'), [rules, ...extraRules, ''].join('\n'));
  for (const file of files) {
    const target = path.join(root, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, `${file}\n`);
  }
  return root;
}

/** Files the package ships, at least one per ALLOWED entry. */
const SHIPPED = [
  '.claude-plugin/marketplace.json',
  'LICENSE',
  'README.md',
  'docs/_data/pinned.yaml',
  'docs/_internal/STABILITY.md',
  'docs/index.md',
  'src/module.yaml',
  'src/shared/tool-requirements.yaml',
  'src/skf-setup/SKILL.md',
  'src/skf-setup/references/report.md',
  'tools/cli/lib/installer.js',
  'tools/cli/skf-cli.js',
  'tools/skf-npx-wrapper.js',
];

/** Maintainer-only files, each kept out by a rule in .npmignore. */
const MAINTAINER_ONLY = [
  '.gitattributes',
  '.github/workflows/quality.yaml',
  '.iwe/config.toml',
  '.nvmrc',
  'CHANGELOG.md',
  'CONTRIBUTING.md',
  '_bmad-output/plan.json',
  'changes/some-change.yaml',
  'docs/_internal/RELEASING.md',
  'eslint.config.mjs',
  'memory/some-note.md',
  'release-audits/v1.0.0-launch-audit.md',
  'skills/reports/report.md',
  'src/shared/scripts/__pycache__/helper.cpython-311.pyc',
  'test/test-pack-contents.js',
  'tools/changes.js',
  'tools/check-required-checks.js',
  'tools/covered-surfaces.js',
  'tools/release-state.js',
  'tools/validate-no-em-dash.js',
  'tools/validate-skills.js',
  'website/package.json',
];

// --- The rule, on fixed lists ---

test('a path under an allowed folder ships, and a maintainer file next to one does not', () => {
  for (const file of ['src/skf-setup/SKILL.md', 'tools/cli/lib/ui.js', 'tools/skf-npx-wrapper.js', 'docs/_internal/STABILITY.md']) {
    assert.ok(isAllowed(file), file);
  }
  for (const file of [
    'docs/_internal/RELEASING.md',
    'tools/changes.js',
    'tools/client.js',
    'tools/lib/helper.js',
    'changes/x.yaml',
    'srcx/a.js',
    '.gitattributes',
    '.nvmrc',
    'LICENSE.md',
  ]) {
    assert.ok(!isAllowed(file), file);
  }
});

test('each problem names its file: a path outside the list, then a required file missing', () => {
  const files = REQUIRED.filter((file) => file !== 'src/module.yaml');
  assert.deepStrictEqual(packProblems([...files, 'tools/validate-no-em-dash.js', '.nvmrc']), [
    'packed, but not a file the package may ship: .nvmrc',
    'packed, but not a file the package may ship: tools/validate-no-em-dash.js',
    'missing from the pack, and the package needs it: src/module.yaml',
  ]);
  assert.deepStrictEqual(packProblems(REQUIRED), []);
});

test('a Windows list with backslashes compares like one with forward slashes', () => {
  const windows = [...REQUIRED, 'src/skf-setup/SKILL.md'].map((file) => file.replaceAll('/', '\\'));
  assert.deepStrictEqual(packProblems(windows), []);
  assert.deepStrictEqual(packProblems([...windows, String.raw`tools\changes.js`]), [
    'packed, but not a file the package may ship: tools/changes.js',
  ]);
});

test('package.json declares no main, and its bin runs a required file', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(REPO, 'package.json'), 'utf8'));
  assert.ok(
    !('main' in pkg),
    "package.json declares main: require() of the package would run the CLI against the caller's arguments (docs/_internal/STABILITY.md, Programmatic API)",
  );
  for (const target of Object.values(pkg.bin)) {
    assert.ok(REQUIRED.includes(target.replace(/^\.\//, '')), `the bin target ${target} is not in REQUIRED`);
  }
});

// --- Files git ignores ---

test('the files git ignores in a checkout are left out, and a tracked or unignored file is kept', () => {
  const files = ['.mcp.json', 'coverage/baseline.json', 'coverage/lcov.info', 'src/module.yaml'];
  const root = makePackage(files);
  fs.writeFileSync(path.join(root, '.gitignore'), '.mcp.json\ncoverage/\n');
  const git = (...args) => execFileSync('git', args, { cwd: root, env: gitEnv(), stdio: 'pipe' });
  git('init', '-q');
  git('add', '-f', 'coverage/baseline.json');
  assert.deepStrictEqual(withoutGitIgnored(root, files), ['coverage/baseline.json', 'src/module.yaml']);
});

test('outside a git checkout no file is left out', () => {
  const files = ['.mcp.json', 'src/module.yaml'];
  const root = makePackage(files);
  fs.writeFileSync(path.join(root, '.gitignore'), '.mcp.json\n');
  // git looks for a checkout no higher than `root`, even when the temp folder sits in one.
  assert.deepStrictEqual(withoutGitIgnored(root, files, gitEnv({ GIT_CEILING_DIRECTORIES: path.dirname(root) })), files);
});

// --- npm pack ---

test('the pack of this checkout holds only files the package may ship, and every file it needs', () => {
  const problems = packProblems(withoutGitIgnored(REPO, packedFiles(REPO)));
  assert.ok(
    problems.length === 0,
    `${problems.join('\n  ')}\n  Give a maintainer-only file an .npmignore rule; add a file the package must ship to ALLOWED (and REQUIRED) in test/test-pack-contents.js. A local file you do not commit drops out of this check once git ignores it.`,
  );
});

test("the repository's package.json and .npmignore keep every maintainer-only file out", () => {
  const packed = packedFiles(makePackage([...SHIPPED, ...MAINTAINER_ONLY]));
  assert.deepStrictEqual(packed.toSorted(), [...SHIPPED, 'package.json'].toSorted());
  assert.deepStrictEqual(packProblems(packed), []);
});

test('stray files .npmignore misses, and required files too broad a rule drops, fail by name', () => {
  // A new root dotfile, a new top-level folder and a new tools/ subfolder;
  // then a rule meant for root config files that also drops the module's,
  // and one meant for internal docs that also drops the contract.
  const strays = ['.stray-dotfile', 'stray-folder/file.txt', 'tools/stray-folder/helper.js'];
  const root = makePackage([...SHIPPED, ...strays], ['*.yaml', 'docs/_internal/']);
  assert.deepStrictEqual(packProblems(packedFiles(root)), [
    'packed, but not a file the package may ship: .stray-dotfile',
    'packed, but not a file the package may ship: stray-folder/file.txt',
    'packed, but not a file the package may ship: tools/stray-folder/helper.js',
    'missing from the pack, and the package needs it: src/module.yaml',
    'missing from the pack, and the package needs it: src/shared/tool-requirements.yaml',
    'missing from the pack, and the package needs it: docs/_internal/STABILITY.md',
  ]);
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
