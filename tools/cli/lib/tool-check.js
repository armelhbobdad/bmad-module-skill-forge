/**
 * SKF Tool Check
 * Probes the tools SKF runs (the list in src/shared/tool-requirements.yaml)
 * in parallel when a command starts, and prints one line per tool once the
 * command's own work is done: the version found, its status against the
 * tool's minimum and, when it is not ok, how to upgrade or install it.
 *
 * Each probe runs a binary resolved on PATH outside the project folder, with
 * no shell and fixed arguments, and never npx, which can download. A .cmd or
 * .bat shim on Windows runs through cmd.exe. A missing, hanging or failing
 * probe reads as unknown: nothing here throws or changes an exit code.
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const chalk = require('chalk');
const yaml = require('js-yaml');
const { TIMEOUT_MS, compareVersions, findVersion } = require('./version-check');

const PACKAGE_REQUIREMENTS = path.join(__dirname, '..', '..', '..', 'src', 'shared', 'tool-requirements.yaml');
// The copy the installer writes: the minimums of the SKF version the workflows run.
const PROJECT_REQUIREMENTS = path.join('_bmad', 'skf', 'shared', 'tool-requirements.yaml');
const MINIMUM = /^\d+(?:\.\d+)*$/;
// SKF runs these through npx when they are not installed, so a probe reads a
// binary on PATH only, and a missing one is no gap.
const NPX_TOOLS = new Set(['tessl', 'skill_check']);
// ccc has no --version: `uv tool list` names each package uv installed, with its version.
const CCC_PACKAGE = /^cocoindex-code v(\S+)/m;
const MAX_OUTPUT = 64 * 1024;
const STYLES = { ok: chalk.green, upgrade: chalk.yellow, unknown: chalk.yellow, missing: chalk.red, optional: chalk.dim };

/** The tools of a tool-requirements.yaml by key (mappings only), or null when it cannot be read. */
function readTools(file) {
  try {
    const tools = yaml.load(fs.readFileSync(file, 'utf8'))?.tools;
    if (!tools || typeof tools !== 'object' || Array.isArray(tools)) return null;
    return Object.fromEntries(Object.entries(tools).filter(([, tool]) => tool && typeof tool === 'object' && !Array.isArray(tool)));
  } catch {
    return null;
  }
}

/** An environment variable, its name matched case-insensitively on Windows. */
function envValue(env, name) {
  if (process.platform !== 'win32') return env[name];
  const key = Object.keys(env).find((candidate) => candidate.toUpperCase() === name.toUpperCase());
  return key === undefined ? undefined : env[key];
}

function realpath(file) {
  try {
    return fs.realpathSync.native(file);
  } catch {
    return file;
  }
}

/** True when `target` is `folder` or lies inside it. */
function isInside(target, folder) {
  const relative = path.relative(folder, target);
  return !path.isAbsolute(relative) && relative.split(path.sep)[0] !== '..';
}

function isRunnable(file) {
  try {
    if (!fs.statSync(file).isFile()) return false;
    if (process.platform !== 'win32') fs.accessSync(file, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

/**
 * The absolute path of `name` on PATH, or null. A PATH folder in or under the
 * project, a relative PATH entry (a shell reads it from the project folder)
 * and a binary whose real path lies in the project are all skipped, so a
 * binary planted in the repository never runs. On Windows each PATHEXT
 * extension is tried, never the bare name.
 */
function resolveOutsideProject(name, { env, projectDir }) {
  const project = [path.resolve(projectDir), realpath(path.resolve(projectDir))];
  const inProject = (file) => project.some((folder) => isInside(file, folder));
  const extensions = process.platform === 'win32' ? (envValue(env, 'PATHEXT') || '.COM;.EXE;.BAT;.CMD').split(';').filter(Boolean) : [''];
  for (const entry of String(envValue(env, 'PATH') || '').split(path.delimiter)) {
    const dir = entry.replaceAll('"', '');
    if (!path.isAbsolute(dir) || inProject(dir) || inProject(realpath(dir))) continue;
    for (const extension of extensions) {
      const file = path.join(dir, name + extension);
      if (isRunnable(file) && !inProject(realpath(file))) return file;
    }
  }
  return null;
}

/**
 * How to run `file` with `args`: the file itself, or, for a .cmd or .bat shim
 * on Windows (Node refuses to spawn one without a shell), cmd.exe with the
 * command line fixed here. null when that line would not be safe: a path
 * cmd.exe would expand (`%`, `!`) or an argument that is not a plain word.
 */
function commandFor(file, args, platform = process.platform, env = process.env) {
  if (platform !== 'win32' || !/\.(?:cmd|bat)$/i.test(file)) return { file, args, options: {} };
  if (/[%!"]/.test(file) || !args.every((arg) => /^[\w.-]+$/.test(arg))) return null;
  const shell = envValue(env, 'ComSpec') || path.win32.join(envValue(env, 'SystemRoot') || String.raw`C:\Windows`, 'System32', 'cmd.exe');
  return { file: shell, args: ['/d', '/s', '/c', `""${file}" ${args.join(' ')}"`], options: { windowsVerbatimArguments: true } };
}

/** Stop a probe that is still running, so it neither holds the command open nor outlives it. */
function stop(child) {
  try {
    child.kill('SIGKILL');
  } catch {
    // Already gone
  }
  child.stdout?.destroy();
  child.unref();
}

/**
 * Run one probe. Resolves { ok, stdout } and never rejects: a probe that
 * cannot start, exits non-zero or outlives the timeout (it is then killed)
 * is not ok.
 */
function run(command, context) {
  return new Promise((resolve) => {
    let stdout = '';
    let timer;
    let child;
    const finish = (ok) => {
      clearTimeout(timer);
      if (child) context.running.delete(child);
      resolve({ ok, stdout });
    };
    // The report is already taken: a probe chained after it starts nothing.
    if (context.stopped) {
      finish(false);
      return;
    }
    try {
      child = spawn(command.file, command.args, {
        cwd: context.cwd,
        env: context.env,
        stdio: ['ignore', 'pipe', 'ignore'],
        windowsHide: true,
        ...command.options,
      });
    } catch {
      finish(false);
      return;
    }
    context.running.add(child);
    timer = setTimeout(() => {
      stop(child);
      finish(false);
    }, context.timeoutMs);
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      if (stdout.length < MAX_OUTPUT) stdout += chunk;
    });
    child.on('error', () => finish(false));
    child.on('close', (code) => finish(code === 0));
  });
}

/** The first x.y or x.y.z that `file` prints when run with `args`, or null. */
async function versionOf(file, args, context) {
  const command = commandFor(file, args, process.platform, context.env);
  if (!command) return null;
  const { ok, stdout } = await run(command, context);
  return ok ? findVersion(stdout) : null;
}

/** One tool: { found, version }, the version null when it cannot be read. */
async function probe(key, tool, context) {
  if (key === 'node') return { found: true, version: process.versions.node };
  if (key === 'python') {
    // The interpreter uv runs SKF's helpers with. --system leaves out a
    // virtual environment, whose interpreter would be the project's to run.
    const uv = resolveOutsideProject('uv', context);
    const version = uv ? await versionOf(uv, ['python', 'find', '--system', '--show-version'], context) : null;
    if (version) return { found: true, version };
  }
  if (key === 'ccc') {
    if (!resolveOutsideProject('ccc', context)) return { found: false };
    const uv = resolveOutsideProject('uv', context);
    const command = uv && commandFor(uv, ['tool', 'list'], process.platform, context.env);
    const { ok, stdout } = command ? await run(command, context) : { ok: false, stdout: '' };
    const match = ok ? CCC_PACKAGE.exec(stdout) : null;
    return { found: true, version: match ? findVersion(match[1]) : null };
  }
  const [name, ...args] = Array.isArray(tool.version_command) ? tool.version_command.map(String) : [];
  const file = name ? resolveOutsideProject(name, context) : null;
  if (!file) return { found: false };
  return { found: true, version: args.length > 0 ? await versionOf(file, args, context) : null };
}

/**
 * The minimum of each tool, from the project's copy of the list when there is
 * one (the SKF version its workflows run), else from the package's own.
 */
function minimums(projectDir, tools) {
  const source = readTools(path.join(projectDir, PROJECT_REQUIREMENTS)) || tools;
  return Object.fromEntries(
    Object.keys(tools).map((key) => {
      const value = source[key]?.minimum;
      return [key, typeof value === 'string' && MINIMUM.test(value) ? value : null];
    }),
  );
}

/** One report row per tool, in the list's order. A tool that has not answered yet was found and reads as unknown. */
function rowsFor(tools, answers, floors) {
  return Object.entries(tools).map(([key, tool]) => {
    const row = { key, name: String(tool.name || key), version: null, minimum: floors[key] };
    const answer = answers.get(key) || { found: true, version: null };
    if (!answer.found) {
      const tiers = Array.isArray(tool.tiers) ? tool.tiers : [];
      if (NPX_TOOLS.has(key)) return { ...row, status: 'optional', label: 'optional, runs through npx' };
      if (tool.kind === 'tier' && tiers.length > 0)
        return { ...row, status: 'optional', label: `optional, ${tiers[0]} tier`, hint: tool.install_url };
      if (tool.kind === 'tier' || tool.kind === 'optional')
        return { ...row, status: 'optional', label: 'optional', hint: tool.install_url };
      return { ...row, status: 'missing', label: 'missing', hint: tool.install_url };
    }
    if (!answer.version) {
      return { ...row, status: 'unknown', label: 'installed, version unknown', hint: row.minimum ? tool.upgrade : undefined };
    }
    // A minimum may name a major alone (Node.js 22); compareVersions reads x.y.
    const floor = row.minimum && !row.minimum.includes('.') ? `${row.minimum}.0` : row.minimum;
    if (floor && compareVersions(answer.version, floor)) {
      return { ...row, version: answer.version, status: 'upgrade', label: `upgrade to >= ${row.minimum}`, hint: tool.upgrade };
    }
    return { ...row, version: answer.version, status: 'ok', label: 'ok' };
  });
}

/** The report: a heading, then one aligned line per tool. */
function formatReport(rows) {
  const width = (pick) => Math.max(0, ...rows.map((row) => pick(row).length));
  const nameWidth = width((row) => row.name);
  const versionWidth = width((row) => row.version || '-');
  const labelWidth = width((row) => (row.hint ? row.label : ''));
  const lines = [chalk.white.bold('  Tools')];
  for (const row of rows) {
    const style = STYLES[row.status];
    const status = row.hint ? `${style(row.label.padEnd(labelWidth))}  ${chalk.dim(row.hint)}` : style(row.label);
    lines.push(`    ${row.name.padEnd(nameWidth)}  ${(row.version || '-').padEnd(versionWidth)}  ${status}`);
  }
  return lines;
}

/**
 * Start every probe now. The returned rows() waits for them at most
 * `timeoutMs` more, stops any still running and resolves the report rows,
 * or null when the package's tool list cannot be read. rows.stop() stops
 * the probes still running and starts no more, without a report.
 */
function beginCheck({ projectDir = process.cwd(), env = process.env, timeoutMs = TIMEOUT_MS, requirements = PACKAGE_REQUIREMENTS } = {}) {
  const tools = readTools(requirements);
  // Probes run from the filesystem root, so no tool reads the project's own
  // configuration or runs its virtual environment.
  const context = { env, projectDir, timeoutMs, cwd: path.parse(path.resolve(projectDir)).root, running: new Set(), stopped: false };
  const answers = new Map();
  const probes = Object.entries(tools || {}).map(([key, tool]) =>
    probe(key, tool, context).then(
      (answer) => answers.set(key, answer),
      () => answers.set(key, { found: true, version: null }),
    ),
  );
  const stopAll = () => {
    context.stopped = true;
    for (const child of context.running) stop(child);
  };
  async function rows() {
    if (!tools) return null;
    let timer;
    const waited = new Promise((resolve) => {
      timer = setTimeout(resolve, timeoutMs);
    });
    await Promise.race([Promise.all(probes), waited]);
    clearTimeout(timer);
    stopAll();
    return rowsFor(tools, answers, minimums(projectDir, tools));
  }
  return Object.assign(rows, { stop: stopAll });
}

/** Probe every tool and resolve the report rows (see beginCheck). */
function checkTools(options) {
  return beginCheck(options)();
}

/**
 * Start an async tool check, with the shape of startVersionCheck: call the
 * returned function after the command's own work to print the report. It
 * waits at most about 3 s for the probes and never throws. A command that
 * ends without the report calls its stop() instead, so no probe outlives
 * the CLI; after the report, stop() does nothing.
 */
function startToolCheck(options) {
  let rows;
  try {
    rows = beginCheck(options);
  } catch {
    rows = Object.assign(async () => null, { stop() {} });
  }
  async function printIfReady() {
    try {
      const found = await rows();
      console.log(found ? `${formatReport(found).join('\n')}\n` : chalk.dim('  Tools: not checked, the tool list could not be read\n'));
    } catch {
      // Never block or fail the CLI for a tool check
    }
  }
  return Object.assign(printIfReady, { stop: rows.stop });
}

module.exports = { startToolCheck, checkTools, commandFor, formatReport, resolveOutsideProject };
