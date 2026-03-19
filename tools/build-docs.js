/**
 * SKF (Skill Forge) Documentation Build Pipeline
 *
 * Generates LLM-friendly files, creates downloadable bundles,
 * and builds the Astro+Starlight site.
 *
 * Build outputs:
 *   build/artifacts/     - With llms.txt, llms-full.txt, ZIPs
 *   build/site/          - Final Astro output (deployable)
 */

const { execSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const archiver = require('archiver');

// =============================================================================
// Configuration
// =============================================================================

const PROJECT_ROOT = path.dirname(__dirname);
const BUILD_DIR = path.join(PROJECT_ROOT, 'build');

const SITE_URL = process.env.SITE_URL || 'https://armelhbobdad.github.io/bmad-module-skill-forge';
const REPO_URL = 'https://github.com/armelhbobdad/bmad-module-skill-forge';

// llms-full.txt is consumed by AI agents as context. Most LLMs have ~200k token limits.
// 600k chars ≈ 150k tokens (safe margin).
const LLM_MAX_CHARS = 600_000;
const LLM_WARN_CHARS = 500_000;

const LLM_EXCLUDE_PATTERNS = ['changelog', 'downloads/'];

// =============================================================================
// Main Entry Point
// =============================================================================

async function main() {
  console.log();
  printBanner('SKF Documentation Build Pipeline');
  console.log();
  console.log(`Project root: ${PROJECT_ROOT}`);
  console.log(`Build directory: ${BUILD_DIR}`);
  console.log();

  // Check for broken internal links before building
  checkDocLinks();

  cleanBuildDirectory();

  const docsDir = path.join(PROJECT_ROOT, 'docs');
  const artifactsDir = await generateArtifacts(docsDir);
  const siteDir = buildAstroSite();

  printBuildSummary(docsDir, artifactsDir, siteDir);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

// =============================================================================
// Pipeline Stages
// =============================================================================

async function generateArtifacts(docsDir) {
  printHeader('Generating LLM files and download bundles');

  const outputDir = path.join(BUILD_DIR, 'artifacts');
  fs.mkdirSync(outputDir, { recursive: true });

  generateLlmsTxt(outputDir);
  generateLlmsFullTxt(docsDir, outputDir);
  await generateDownloadBundles(outputDir);

  console.log();
  console.log(`  \u001B[32m✓\u001B[0m Artifact generation complete`);

  return outputDir;
}

function buildAstroSite() {
  printHeader('Building Astro + Starlight site');

  const siteDir = path.join(BUILD_DIR, 'site');
  const artifactsDir = path.join(BUILD_DIR, 'artifacts');

  runAstroBuild();
  copyArtifactsToSite(artifactsDir, siteDir);

  console.log();
  console.log(`  \u001B[32m✓\u001B[0m Astro build complete`);

  return siteDir;
}

// =============================================================================
// LLM File Generation
// =============================================================================

function generateLlmsTxt(outputDir) {
  console.log('  → Generating llms.txt...');

  const content = [
    '# Skill Forge (SKF) Documentation',
    '',
    '> Turn code and docs into instructions AI agents can actually follow.',
    '',
    `Documentation: ${SITE_URL}`,
    `Repository: ${REPO_URL}`,
    `Full docs: ${SITE_URL}/llms-full.txt`,
    '',
    '## Quick Start',
    '',
    `- **[Getting Started](${SITE_URL}/getting-started/)** - Installation and first steps`,
    '',
    '## Core Workflows',
    '',
    `- **[Setup Forge (SF)](${SITE_URL}/workflows/#setup-forge-sf)** - Initialize forge environment`,
    `- **[Brief Skill (BS)](${SITE_URL}/workflows/#brief-skill-bs)** - Scope and design a skill`,
    `- **[Create Skill (CS)](${SITE_URL}/workflows/#create-skill-cs)** - Compile a skill from brief`,
    `- **[Quick Skill (QS)](${SITE_URL}/workflows/#quick-skill-qs)** - Fast skill, no brief needed`,
    `- **[Stack Skill (SS)](${SITE_URL}/workflows/#stack-skill-ss)** - Consolidated project stack skill`,
    `- **[Update Skill (US)](${SITE_URL}/workflows/#update-skill-us)** - Regenerate after changes`,
    `- **[Audit Skill (AS)](${SITE_URL}/workflows/#audit-skill-as)** - Drift detection`,
    `- **[Test Skill (TS)](${SITE_URL}/workflows/#test-skill-ts)** - Verify completeness`,
    `- **[Export Skill (EX)](${SITE_URL}/workflows/#export-skill-ex)** - Package for distribution`,
    `- **[Analyze Source (AN)](${SITE_URL}/workflows/#analyze-source-an)** - Discover what to skill`,
    '',
    '---',
    '',
    '## Quick Links',
    '',
    `- [Full Documentation (llms-full.txt)](${SITE_URL}/llms-full.txt) - Complete docs for AI context`,
    `- [Source Bundle](${SITE_URL}/downloads/skf-sources.zip) - Complete source code`,
    `- [Prompts Bundle](${SITE_URL}/downloads/skf-prompts.zip) - Agent prompts and workflows`,
    '',
  ].join('\n');

  const outputPath = path.join(outputDir, 'llms.txt');
  fs.writeFileSync(outputPath, content, 'utf-8');
  console.log(`    Generated llms.txt (${content.length.toLocaleString()} chars)`);
}

function generateLlmsFullTxt(docsDir, outputDir) {
  console.log('  → Generating llms-full.txt...');

  const date = new Date().toISOString().split('T')[0];
  const files = getAllMarkdownFiles(docsDir);

  const output = [
    '# Skill Forge (SKF) Documentation (Full)',
    '',
    '> Complete documentation for AI consumption',
    `> Generated: ${date}`,
    `> Repository: ${REPO_URL}`,
    '',
  ];

  let fileCount = 0;
  let skippedCount = 0;

  for (const mdPath of files) {
    if (shouldExcludeFromLlm(mdPath)) {
      skippedCount++;
      continue;
    }

    const fullPath = path.join(docsDir, mdPath);
    try {
      const content = readMarkdownContent(fullPath);
      output.push(`<document path="${mdPath}">`, content, '</document>', '');
      fileCount++;
    } catch (error) {
      console.error(`    Warning: Could not read ${mdPath}: ${error.message}`);
    }
  }

  const result = output.join('\n');
  validateLlmSize(result);

  const outputPath = path.join(outputDir, 'llms-full.txt');
  fs.writeFileSync(outputPath, result, 'utf-8');

  const tokenEstimate = Math.floor(result.length / 4).toLocaleString();
  console.log(
    `    Processed ${fileCount} files (skipped ${skippedCount}), ${result.length.toLocaleString()} chars (~${tokenEstimate} tokens)`,
  );
}

function getAllMarkdownFiles(dir, baseDir = dir) {
  const files = [];

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      files.push(...getAllMarkdownFiles(fullPath, baseDir));
    } else if (entry.name.endsWith('.md')) {
      const relativePath = path.relative(baseDir, fullPath);
      files.push(relativePath);
    }
  }

  return files;
}

function shouldExcludeFromLlm(filePath) {
  const pathParts = filePath.split(path.sep);
  if (pathParts.some((part) => part.startsWith('_'))) return true;

  return LLM_EXCLUDE_PATTERNS.some((pattern) => filePath.includes(pattern));
}

function readMarkdownContent(filePath) {
  let content = fs.readFileSync(filePath, 'utf-8');

  if (content.startsWith('---')) {
    const end = content.indexOf('---', 3);
    if (end !== -1) {
      content = content.slice(end + 3).trim();
    }
  }

  return content;
}

function validateLlmSize(content) {
  const charCount = content.length;

  if (charCount > LLM_MAX_CHARS) {
    console.error(`    ERROR: Exceeds ${LLM_MAX_CHARS.toLocaleString()} char limit`);
    process.exit(1);
  } else if (charCount > LLM_WARN_CHARS) {
    console.warn(`    \u001B[33mWARNING: Approaching ${LLM_WARN_CHARS.toLocaleString()} char limit\u001B[0m`);
  }
}

// =============================================================================
// Download Bundle Generation
// =============================================================================

async function generateDownloadBundles(outputDir) {
  console.log('  → Generating download bundles...');

  const downloadsDir = path.join(outputDir, 'downloads');
  fs.mkdirSync(downloadsDir, { recursive: true });

  await generateSourcesBundle(downloadsDir);
  await generatePromptsBundle(downloadsDir);
}

async function generateSourcesBundle(downloadsDir) {
  const srcDir = path.join(PROJECT_ROOT, 'src');
  if (!fs.existsSync(srcDir)) return;

  const zipPath = path.join(downloadsDir, 'skf-sources.zip');
  await createZipArchive(srcDir, zipPath, ['__pycache__', '.pyc', '.DS_Store', 'node_modules']);

  const size = (fs.statSync(zipPath).size / 1024 / 1024).toFixed(1);
  console.log(`    skf-sources.zip (${size}M)`);
}

async function generatePromptsBundle(downloadsDir) {
  const srcDir = path.join(PROJECT_ROOT, 'src');
  if (!fs.existsSync(srcDir)) return;

  const zipPath = path.join(downloadsDir, 'skf-prompts.zip');
  await createZipArchive(srcDir, zipPath, ['docs', '.DS_Store', '__pycache__', 'node_modules']);

  const size = Math.floor(fs.statSync(zipPath).size / 1024);
  console.log(`    skf-prompts.zip (${size}K)`);
}

// =============================================================================
// Astro Build
// =============================================================================

function runAstroBuild() {
  console.log('  → Running astro build...');
  execSync('npx astro build --root website', {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
    env: {
      ...process.env,
    },
  });
}

function copyArtifactsToSite(artifactsDir, siteDir) {
  console.log('  → Copying artifacts to site...');

  fs.copyFileSync(path.join(artifactsDir, 'llms.txt'), path.join(siteDir, 'llms.txt'));
  fs.copyFileSync(path.join(artifactsDir, 'llms-full.txt'), path.join(siteDir, 'llms-full.txt'));

  const downloadsDir = path.join(artifactsDir, 'downloads');
  if (fs.existsSync(downloadsDir)) {
    copyDirectory(downloadsDir, path.join(siteDir, 'downloads'));
  }
}

// =============================================================================
// Build Summary
// =============================================================================

function printBuildSummary(docsDir, artifactsDir, siteDir) {
  console.log();
  printBanner('Build Complete!');
  console.log();
  console.log('Build artifacts:');
  console.log(`  Source docs:     ${docsDir}`);
  console.log(`  Generated files: ${artifactsDir}`);
  console.log(`  Final site:      ${siteDir}`);
  console.log();
  console.log(`Deployable output: ${siteDir}/`);
  console.log();

  listDirectoryContents(siteDir);
}

function listDirectoryContents(dir) {
  const entries = fs.readdirSync(dir).slice(0, 15);

  for (const entry of entries) {
    const fullPath = path.join(dir, entry);
    const stat = fs.statSync(fullPath);

    if (stat.isFile()) {
      const sizeStr = formatFileSize(stat.size);
      console.log(`  ${entry.padEnd(40)} ${sizeStr.padStart(8)}`);
    } else {
      console.log(`  ${entry}/`);
    }
  }
}

function formatFileSize(bytes) {
  if (bytes > 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(1)}M`;
  } else if (bytes > 1024) {
    return `${Math.floor(bytes / 1024)}K`;
  }
  return `${bytes}B`;
}

// =============================================================================
// File System Utilities
// =============================================================================

function cleanBuildDirectory() {
  console.log('Cleaning previous build...');

  if (fs.existsSync(BUILD_DIR)) {
    fs.rmSync(BUILD_DIR, { recursive: true });
  }
  fs.mkdirSync(BUILD_DIR, { recursive: true });
}

function copyDirectory(src, dest, exclude = []) {
  if (!fs.existsSync(src)) return false;
  fs.mkdirSync(dest, { recursive: true });

  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (exclude.includes(entry.name)) continue;

    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      copyDirectory(srcPath, destPath, exclude);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
  return true;
}

function createZipArchive(sourceDir, outputPath, exclude = []) {
  return new Promise((resolve, reject) => {
    const output = fs.createWriteStream(outputPath);
    const archive = archiver('zip', { zlib: { level: 9 } });

    output.on('close', resolve);
    archive.on('error', reject);

    archive.pipe(output);

    const baseName = path.basename(sourceDir);
    archive.directory(sourceDir, baseName, (entry) => {
      for (const pattern of exclude) {
        if (entry.name.includes(pattern)) return false;
      }
      return entry;
    });

    archive.finalize();
  });
}

// =============================================================================
// Console Output Formatting
// =============================================================================

function printHeader(title) {
  console.log();
  console.log('┌' + '─'.repeat(62) + '┐');
  console.log(`│ ${title.padEnd(60)} │`);
  console.log('└' + '─'.repeat(62) + '┘');
}

function printBanner(title) {
  console.log('╔' + '═'.repeat(62) + '╗');
  console.log(`║${title.padStart(31 + title.length / 2).padEnd(62)}║`);
  console.log('╚' + '═'.repeat(62) + '╝');
}

// =============================================================================
// Link Checking
// =============================================================================

function checkDocLinks() {
  printHeader('Checking documentation links');

  try {
    execSync('node tools/validate-doc-links.js', {
      cwd: PROJECT_ROOT,
      stdio: 'inherit',
    });
  } catch {
    console.error('\n  \u001B[31m✗\u001B[0m Link check failed - fix broken links before building\n');
    process.exit(1);
  }
}
