/**
 * SKF Version Check
 * Async, non-blocking check against the npm registry.
 * Returns a promise that resolves to an update notice string (or null).
 */

const https = require('node:https');
const chalk = require('chalk');

const PACKAGE_NAME = 'bmad-module-skill-forge';
const REGISTRY_URL = `https://registry.npmjs.org/${PACKAGE_NAME}/latest`;
const TIMEOUT_MS = 3000;
// The first x.y or x.y.z in a string: `0.45`, `v3.0.0-rc.1`, `ast-grep 0.42.2`.
const VERSION_IN_TEXT = /(\d+)\.(\d+)(?:\.(\d+))?/;

function fetchLatestVersion() {
  return new Promise((resolve) => {
    const req = https.get(REGISTRY_URL, { timeout: TIMEOUT_MS }, (res) => {
      if (res.statusCode !== 200) {
        resolve(null);
        res.resume();
        return;
      }

      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve(json.version || null);
        } catch {
          resolve(null);
        }
      });
    });

    req.on('error', () => resolve(null));
    req.on('timeout', () => {
      req.destroy();
      resolve(null);
    });
  });
}

/** The first x.y or x.y.z in `text`, as written there, or null. */
function findVersion(text) {
  const match = VERSION_IN_TEXT.exec(String(text ?? ''));
  return match ? match[0] : null;
}

/**
 * True when `latest` is newer than `current`. Each is read as the first x.y
 * or x.y.z it holds, a missing part as 0, so `0.45` and `ast-grep 0.42.2`
 * both compare with `0.45.3`; a string with neither is never newer.
 */
function compareVersions(current, latest) {
  const parse = (text) => {
    const match = VERSION_IN_TEXT.exec(String(text ?? ''));
    return match ? match.slice(1, 4).map((part) => Number(part ?? 0)) : null;
  };
  const [from, to] = [parse(current), parse(latest)];
  if (!from || !to) return false;
  const index = from.findIndex((part, position) => part !== to[position]);
  return index !== -1 && to[index] > from[index];
}

/**
 * Start an async version check. Call the returned function after your
 * command finishes to print the update notice (if any).
 */
function startVersionCheck(currentVersion) {
  const checkPromise = fetchLatestVersion().then((latestVersion) => {
    if (!latestVersion || !compareVersions(currentVersion, latestVersion)) {
      return null;
    }
    return (
      '\n' +
      chalk.hex('#F59E0B')(`  Update available: ${chalk.dim(currentVersion)} → ${chalk.hex('#FBBF24').bold(latestVersion)}`) +
      '\n' +
      chalk.dim(`  Run: npx bmad-module-skill-forge@latest install`) +
      '\n'
    );
  });

  return async function printIfReady() {
    try {
      const notice = await checkPromise;
      if (notice) {
        process.stderr.write(notice);
      }
    } catch {
      // Never block or fail the CLI for a version check
    }
  };
}

module.exports = { startVersionCheck, compareVersions, findVersion, TIMEOUT_MS };
