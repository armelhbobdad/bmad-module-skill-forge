/**
 * IDE Skill Installer — Verbatim skill directory installation
 *
 * Replaces the legacy command-file generation approach with the BMAD standard:
 * skill directories (containing SKILL.md + supporting files) are copied directly
 * to each IDE's skills/ directory. IDEs read SKILL.md natively.
 *
 * Supports 23+ IDEs via platform-codes.yaml (config-driven, no IDE-specific code).
 */

const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

const PLATFORM_CODES_PATH = path.join(__dirname, 'platform-codes.yaml');

// OS/editor artifacts to filter during copy
const ARTIFACT_FILTER = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '._.DS_Store']);

/**
 * Load platform configuration from platform-codes.yaml.
 * Returns { platforms: { 'claude-code': { name, preferred, installer: { target_dir, legacy_targets } }, ... } }
 */
function loadPlatforms() {
  const content = fs.readFileSync(PLATFORM_CODES_PATH, 'utf8');
  return yaml.load(content);
}

/**
 * Get available platforms for UI display.
 * Returns array of { value: 'claude-code', label: 'Claude Code', preferred: true }
 */
function getAvailablePlatforms() {
  const config = loadPlatforms();
  return Object.entries(config.platforms)
    .filter(([, p]) => !p.suspended)
    .map(([code, p]) => ({
      value: code,
      label: p.name,
      preferred: p.preferred || false,
    }))
    .sort((a, b) => {
      // Preferred first, then alphabetical
      if (a.preferred !== b.preferred) return b.preferred ? 1 : -1;
      return a.label.localeCompare(b.label);
    });
}

/**
 * Get IDE auto-detection markers.
 * Returns { 'claude-code': ['.claude'], 'cursor': ['.cursor'], ... }
 *
 * Uses explicit detection_marker from platform config when available,
 * otherwise derives from the top-level directory of target_dir.
 * The derived marker only works when the IDE's config directory exists
 * independently of the installer (e.g. .claude/ exists before SKF install).
 */
function getDetectionMarkers() {
  const config = loadPlatforms();
  const markers = {};
  for (const [code, p] of Object.entries(config.platforms)) {
    if (p.suspended) continue;
    const targetDir = p.installer?.target_dir;
    if (!targetDir) continue;
    if (p.installer.detection_marker) {
      markers[code] = [p.installer.detection_marker];
    } else {
      // Derive from target_dir — works when top-level dir is the IDE's own config dir
      const topDir = '.' + targetDir.split('/')[0].replace(/^\./, '');
      markers[code] = [topDir];
    }
  }
  return markers;
}

/**
 * Install skill directories to all selected IDEs.
 *
 * @param {string} projectDir - Project root directory
 * @param {string} skfDir - Path to installed SKF module (e.g., {projectDir}/_bmad/skf)
 * @param {string[]} ideCodes - Array of IDE codes (e.g., ['claude-code', 'cursor'])
 * @returns {{ installed: number, ides: string[], directories: string[] }}
 */
async function installSkillsToIdes(projectDir, skfDir, ideCodes) {
  if (!ideCodes || ideCodes.length === 0) return { installed: 0, ides: [], directories: [] };

  const config = loadPlatforms();
  let totalInstalled = 0;
  const processedIdes = [];
  const allDirectories = [];

  // Copy filter: skip OS artifacts
  const copyFilter = (src) => !ARTIFACT_FILTER.has(path.basename(src));

  for (const ideCode of ideCodes) {
    const platform = config.platforms[ideCode];
    if (!platform || !platform.installer?.target_dir) continue;

    const targetDir = path.join(projectDir, platform.installer.target_dir);

    // Clean legacy targets first (old command files from previous SKF installs)
    await cleanLegacyTargets(projectDir, platform);

    // Clean existing SKF skills from this IDE (for update/reinstall)
    await cleanSkfSkills(targetDir);

    // Ensure target directory exists
    await fs.ensureDir(targetDir);

    // Copy all skf-* skill directories from the installed module
    if (await fs.pathExists(skfDir)) {
      const entries = await fs.readdir(skfDir, { withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;

        // Copy skill directories (skf-*) and supporting resources (knowledge/, shared/)
        if (entry.name.startsWith('skf-') || entry.name === 'knowledge' || entry.name === 'shared') {
          const src = path.join(skfDir, entry.name);
          const dest = path.join(targetDir, entry.name);
          await fs.copy(src, dest, { filter: copyFilter });
          totalInstalled++;
        }
      }
    }

    allDirectories.push(platform.installer.target_dir);
    processedIdes.push(ideCode);
  }

  return { installed: totalInstalled, ides: processedIdes, directories: allDirectories };
}

/**
 * Remove legacy command files from old IDE target directories.
 * Handles migration from command-file approach to skill-directory approach.
 */
async function cleanLegacyTargets(projectDir, platform) {
  const legacyTargets = platform.installer?.legacy_targets || [];

  for (const legacyDir of legacyTargets) {
    const fullPath = path.join(projectDir, legacyDir);
    if (!(await fs.pathExists(fullPath))) continue;

    try {
      const files = await fs.readdir(fullPath);
      for (const file of files) {
        // Remove SKF-specific command files from legacy directories
        if (file.startsWith('bmad-skf-') || file.startsWith('bmad-agent-skf-')) {
          await fs.remove(path.join(fullPath, file));
        }
      }

      // Remove empty directories
      const remaining = await fs.readdir(fullPath);
      if (remaining.length === 0) {
        await fs.remove(fullPath);
        // Also try to remove empty parent
        const parentDir = path.dirname(fullPath);
        try {
          const parentRemaining = await fs.readdir(parentDir);
          if (parentRemaining.length === 0) await fs.remove(parentDir);
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* non-critical, continue */
    }
  }
}

/**
 * Remove existing SKF skill directories from an IDE target.
 * Called before reinstalling to ensure clean state.
 */
async function cleanSkfSkills(targetDir) {
  if (!(await fs.pathExists(targetDir))) return;

  try {
    const entries = await fs.readdir(targetDir);
    for (const entry of entries) {
      // Only remove SKF-owned directories (skf-*, knowledge, shared)
      if (entry.startsWith('skf-') || entry === 'knowledge' || entry === 'shared') {
        await fs.remove(path.join(targetDir, entry));
      }
    }
  } catch {
    /* non-critical */
  }
}

/**
 * Remove all SKF skills from all known IDE directories.
 * Used during uninstall.
 */
async function removeAllSkfSkills(projectDir) {
  const config = loadPlatforms();
  const removed = [];

  for (const [, platform] of Object.entries(config.platforms)) {
    if (!platform.installer?.target_dir) continue;
    const targetDir = path.join(projectDir, platform.installer.target_dir);
    if (await fs.pathExists(targetDir)) {
      await cleanSkfSkills(targetDir);
      // Also clean legacy targets
      await cleanLegacyTargets(projectDir, platform);
      removed.push(platform.installer.target_dir);
    }
  }

  return removed;
}

module.exports = { installSkillsToIdes, getAvailablePlatforms, getDetectionMarkers, removeAllSkfSkills, loadPlatforms };
