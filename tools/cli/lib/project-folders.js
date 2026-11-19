/**
 * SKF Project Folders - Resolves the folder values config.yaml holds.
 *
 * Mirrors `resolve_folder` in src/shared/scripts/skf-preflight.py, the rule
 * every workflow reads the folders with, so change the two together. The
 * BMAD Method installer writes a folder value as `{project-root}/<value>`
 * (src/module.yaml's `result`): a whole leading `{project-root}` segment,
 * followed by `/`, `\` or the end of the value, is the project root. A
 * relative value is joined to the project root and an absolute value stays
 * where it points.
 */

const path = require('node:path');

const PROJECT_ROOT_RE = /^\{project-root\}(?:[/\\]+|$)/;

// The text of the .gitkeep the installer writes in an output folder it creates.
const GITKEEP = '# This file ensures the directory is tracked by git\n';

/**
 * Return the absolute path of a folder value from config.yaml.
 *
 * @param {string} projectDir - Project root
 * @param {string} value - The folder value as config.yaml holds it
 */
function resolveProjectFolder(projectDir, value) {
  return path.resolve(projectDir, String(value).replace(PROJECT_ROOT_RE, ''));
}

module.exports = { GITKEEP, PROJECT_ROOT_RE, resolveProjectFolder };
