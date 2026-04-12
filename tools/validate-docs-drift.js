/**
 * Documentation Drift Validator
 *
 * Verifies that SKF docs agree with the canonical oh-my-skills output on
 * every version number, commit SHA, and library reference the docs cite.
 *
 * What it checks:
 * - Every skill listed in `docs/_data/pinned.yaml` actually exists at the
 *   claimed version and commit in $OMS/skills/<name>/<version>/<name>/metadata.json
 * - The metadata.json `version` field matches the anchor `version`
 * - The metadata.json `source_commit` field matches the anchor `source_commit`
 * - Every `.md` file under `docs/` is grepped for `<library> v?<x.y.z>` strings;
 *   any that don't match the currently-pinned version for that library are flagged
 * - Known illustrative libraries (hono, drizzle-orm, ...) are whitelisted and
 *   allowed to carry any version number
 *
 * Usage:
 *   node tools/validate-docs-drift.js             # validate, exit 1 on drift
 *   OMS=/path/to/oh-my-skills node tools/validate-docs-drift.js
 *
 * Exit codes:
 *   0 — no drift detected
 *   1 — drift found; fix the docs or update docs/_data/pinned.yaml
 *   2 — infrastructure failure (anchors file missing, oh-my-skills path
 *       unreachable, yaml parse error)
 */

const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');

const SKF_ROOT = path.resolve(__dirname, '..');
const DOCS_DIR = path.join(SKF_ROOT, 'docs');
const ANCHORS_PATH = path.join(DOCS_DIR, '_data', 'pinned.yaml');

function loadAnchors() {
  if (!fs.existsSync(ANCHORS_PATH)) {
    console.error(`error: anchors file not found at ${ANCHORS_PATH}`);
    process.exit(2);
  }
  try {
    return yaml.load(fs.readFileSync(ANCHORS_PATH, 'utf8'));
  } catch (error) {
    console.error(`error: could not parse ${ANCHORS_PATH}: ${error.message}`);
    process.exit(2);
  }
}

function resolveOmsPath(anchors) {
  if (process.env.OMS) {
    return path.resolve(process.env.OMS);
  }
  return path.resolve(SKF_ROOT, anchors.oh_my_skills_path);
}

function checkCanonicalFiles(anchors, omsPath) {
  const errors = [];
  if (!fs.existsSync(omsPath) || !fs.statSync(omsPath).isDirectory()) {
    errors.push(
      `CRITICAL: oh_my_skills_path does not resolve to a directory: ${omsPath}`,
      `  hint: set OMS=/path/to/oh-my-skills or edit docs/_data/pinned.yaml`,
    );
    return errors;
  }

  for (const [skillName, spec] of Object.entries(anchors.skills)) {
    const metadataPath = path.join(omsPath, 'skills', skillName, spec.version, skillName, 'metadata.json');

    if (!fs.existsSync(metadataPath)) {
      errors.push(`MISSING: ${skillName}@${spec.version} — expected ${metadataPath}`);
      continue;
    }

    let metadata;
    try {
      metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
    } catch (error) {
      errors.push(`UNPARSEABLE: ${metadataPath} — ${error.message}`);
      continue;
    }

    if (metadata.version !== spec.version) {
      errors.push(`VERSION_DRIFT: ${skillName} — anchors say ${spec.version}, ` + `metadata.json says ${metadata.version}`);
    }

    if (metadata.source_commit !== spec.source_commit) {
      const anchorShort = (spec.source_commit || '').slice(0, 12);
      const realShort = (metadata.source_commit || '').slice(0, 12);
      errors.push(`COMMIT_DRIFT: ${skillName} — anchors say ${anchorShort}, ` + `metadata.json says ${realShort}`);
    }

    if (metadata.confidence_tier !== spec.confidence_tier) {
      errors.push(`TIER_DRIFT: ${skillName} — anchors say ${spec.confidence_tier}, ` + `metadata.json says ${metadata.confidence_tier}`);
    }

    if (metadata.source_authority !== spec.source_authority) {
      errors.push(
        `AUTHORITY_DRIFT: ${skillName} — anchors say ${spec.source_authority}, ` + `metadata.json says ${metadata.source_authority}`,
      );
    }
  }

  return errors;
}

function getMarkdownFiles(dir) {
  const files = [];
  function walk(currentDir) {
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name.startsWith('_')) continue;
      const fullPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile() && entry.name.endsWith('.md')) {
        files.push(fullPath);
      }
    }
  }
  walk(dir);
  return files;
}

function checkDocsForStaleVersions(anchors) {
  const errors = [];

  // Build map: library-name → current-version
  const libVersions = Object.fromEntries(Object.values(anchors.skills).map((spec) => [spec.library, spec.version]));
  const libs = Object.keys(libVersions);
  if (libs.length === 0) return errors;

  const illustrative = new Set(anchors.illustrative_libraries || []);

  // Pattern: <library-name><whitespace or @>v?<semver>
  // Word-boundary anchored to avoid partial matches inside other words.
  const libPattern = String.raw`\b(` + libs.map((l) => l.replaceAll(/[.*+?^${}()|[\\]\\\\]/g, String.raw`\\$&`)).join('|') + ')';
  const versionPattern = String.raw`[\s@]+v?(\d+\.\d+\.\d+)`;
  const regex = new RegExp(libPattern + versionPattern, 'gi');

  for (const mdFile of getMarkdownFiles(DOCS_DIR)) {
    const content = fs.readFileSync(mdFile, 'utf8');
    const lines = content.split('\n');
    for (const [idx, line] of lines.entries()) {
      for (const match of line.matchAll(regex)) {
        const lib = match[1].toLowerCase();
        if (illustrative.has(lib)) continue;
        const found = match[2];
        const expected = libVersions[lib];
        if (expected && found !== expected) {
          const relPath = path.relative(SKF_ROOT, mdFile);
          errors.push(`STALE_VERSION: ${relPath}:${idx + 1} — ${lib} v${found} (expected v${expected})`);
        }
      }
    }
  }

  return errors;
}

function main() {
  const anchors = loadAnchors();
  const omsPath = resolveOmsPath(anchors);

  const errors = [...checkCanonicalFiles(anchors, omsPath), ...checkDocsForStaleVersions(anchors)];

  if (errors.length > 0) {
    console.error('DRIFT DETECTED:\n');
    for (const err of errors) {
      console.error(`  - ${err}`);
    }
    console.error(`\n${errors.length} drift finding(s). Fix the docs or update docs/_data/pinned.yaml.`);
    console.error('\nAnchors file: docs/_data/pinned.yaml');
    console.error(`Checked against: ${omsPath}`);
    process.exit(1);
  }

  const skillCount = Object.keys(anchors.skills).length;
  console.log(`OK: ${skillCount} skills checked against ${omsPath}, no drift.`);
  process.exit(0);
}

main();
