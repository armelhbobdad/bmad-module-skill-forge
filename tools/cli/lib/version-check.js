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

function compareVersions(current, latest) {
  const parse = (v) => v.replace(/^v/, '').split('.').map(Number);
  const [cMajor, cMinor, cPatch] = parse(current);
  const [lMajor, lMinor, lPatch] = parse(latest);

  if (lMajor > cMajor) return true;
  if (lMajor === cMajor && lMinor > cMinor) return true;
  if (lMajor === cMajor && lMinor === cMinor && lPatch > cPatch) return true;
  return false;
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

module.exports = { startVersionCheck, compareVersions };
