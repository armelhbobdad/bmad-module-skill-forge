/**
 * Fix Documentation Links
 *
 * Converts relative markdown links to repo-relative paths with .md extension.
 * This ensures links work both in GitHub and on the Astro/Starlight site
 * (the rehype plugin transforms /docs/path/file.md → /path/file/ at build time).
 *
 * - ./file.md → /docs/current/path/file.md
 * - ../other/file.md → /docs/resolved/path/file.md
 * - /path/file/ → /docs/path/file.md (or /docs/path/file/index.md if it's a directory)
 *
 * Usage:
 *   node tools/fix-doc-links.js           # Dry run (shows what would change)
 *   node tools/fix-doc-links.js --write   # Actually write changes
 */

const fs = require('node:fs');
const path = require('node:path');

const DOCS_ROOT = path.resolve(__dirname, '../docs');
const DRY_RUN = !process.argv.includes('--write');

const ALL_MARKDOWN_LINKS_REGEX = /\[([^\]]*)\]\(([^)]+)\)/g;

/**
 * Get all markdown files in docs directory, excluding _* directories/files
 */
function getMarkdownFiles(dir) {
  const files = [];

  function walk(currentDir) {
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);

      if (entry.name.startsWith('_')) {
        continue;
      }

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

/**
 * Convert a markdown link href to repo-relative path with .md extension
 *
 * @param {string} href - The original href
 * @param {string} currentFilePath - Absolute path to the file containing this link
 * @returns {string|null} - Repo-relative path, or null if shouldn't be converted
 */
function convertToRepoRelative(href, currentFilePath) {
  if (href.includes('://') || href.startsWith('mailto:') || href.startsWith('tel:')) {
    return null;
  }

  if (href.startsWith('#')) {
    return null;
  }

  let anchor = '';
  let query = '';
  let pathPortion = href;

  const hashIndex = href.indexOf('#');
  const queryIndex = href.indexOf('?');

  if (hashIndex !== -1 || queryIndex !== -1) {
    const firstDelimiter = Math.min(hashIndex === -1 ? Infinity : hashIndex, queryIndex === -1 ? Infinity : queryIndex);
    pathPortion = href.slice(0, Math.max(0, firstDelimiter));

    const suffix = href.slice(Math.max(0, firstDelimiter));
    const anchorInSuffix = suffix.indexOf('#');

    if (suffix.startsWith('?')) {
      if (anchorInSuffix === -1) {
        query = suffix;
      } else {
        query = suffix.slice(0, Math.max(0, anchorInSuffix));
        anchor = suffix.slice(Math.max(0, anchorInSuffix));
      }
    } else {
      anchor = suffix;
    }
  }

  const ext = path.extname(pathPortion).toLowerCase();
  if (ext && ext !== '.md' && !pathPortion.endsWith('/')) {
    return null;
  }

  const isDirectoryPath = pathPortion.endsWith('/');

  let absolutePath;

  if (pathPortion.startsWith('/docs/')) {
    absolutePath = path.join(path.dirname(DOCS_ROOT), pathPortion);
  } else if (pathPortion.startsWith('/')) {
    absolutePath = path.join(DOCS_ROOT, pathPortion);
  } else {
    const currentDir = path.dirname(currentFilePath);
    absolutePath = path.resolve(currentDir, pathPortion);
  }

  let repoRelative = '/docs/' + path.relative(DOCS_ROOT, absolutePath);
  repoRelative = repoRelative.split(path.sep).join('/');

  if (isDirectoryPath) {
    const relativeDir = repoRelative.slice(6);
    const normalizedDir = relativeDir === '' || relativeDir === '.' ? '' : relativeDir;
    const indexPath = path.join(DOCS_ROOT, normalizedDir, 'index.md');
    const filePath = normalizedDir ? path.join(DOCS_ROOT, normalizedDir + '.md') : null;

    if (fs.existsSync(indexPath)) {
      repoRelative = repoRelative.endsWith('/') ? repoRelative + 'index.md' : repoRelative + '/index.md';
    } else if (filePath && fs.existsSync(filePath)) {
      repoRelative = repoRelative + '.md';
    } else {
      repoRelative = repoRelative.endsWith('/') ? repoRelative + 'index.md' : repoRelative + '/index.md';
    }
  } else if (!repoRelative.endsWith('.md')) {
    repoRelative = repoRelative + '.md';
  }

  return repoRelative + query + anchor;
}

/**
 * Process a single markdown file, skipping links inside fenced code blocks
 */
function processFile(filePath) {
  const original = fs.readFileSync(filePath, 'utf-8');
  const changes = [];

  const codeBlocks = [];
  const CODE_PLACEHOLDER = '\u0000CODE_BLOCK_';

  let contentWithPlaceholders = original.replaceAll(/```[\s\S]*?```/g, (match) => {
    const index = codeBlocks.length;
    codeBlocks.push(match);
    return `${CODE_PLACEHOLDER}${index}\u0000`;
  });

  contentWithPlaceholders = contentWithPlaceholders.replaceAll(ALL_MARKDOWN_LINKS_REGEX, (match, linkText, href) => {
    const newHref = convertToRepoRelative(href, filePath);

    if (newHref === null) {
      return match;
    }

    if (newHref !== href) {
      changes.push({ from: href, to: newHref });
      return `[${linkText}](${newHref})`;
    }

    return match;
  });

  const updated = contentWithPlaceholders.replaceAll(
    new RegExp(`${CODE_PLACEHOLDER}(\\d+)\u0000`, 'g'),
    (match, index) => codeBlocks[parseInt(index, 10)],
  );

  return {
    changed: changes.length > 0,
    original,
    updated,
    changes,
  };
}

/**
 * Validate that a repo-relative link points to an existing file
 */
function validateLink(repoRelativePath) {
  const checkPath = repoRelativePath.split('#')[0].split('?')[0];
  const relativePath = checkPath.startsWith('/docs/') ? checkPath.slice(6) : checkPath.slice(1);
  return fs.existsSync(path.join(DOCS_ROOT, relativePath));
}

// Main execution
console.log(`\nScanning docs in: ${DOCS_ROOT}`);
console.log(`Mode: ${DRY_RUN ? 'DRY RUN (use --write to apply changes)' : 'WRITE MODE'}\n`);

const files = getMarkdownFiles(DOCS_ROOT);
console.log(`Found ${files.length} markdown files (excluding _* paths)\n`);

let totalChanges = 0;
let filesChanged = 0;
const brokenLinks = [];

for (const filePath of files) {
  const relativePath = path.relative(DOCS_ROOT, filePath);
  const result = processFile(filePath);

  if (result.changed) {
    filesChanged++;
    totalChanges += result.changes.length;

    console.log(`\n${relativePath}`);
    for (const change of result.changes) {
      const isValid = validateLink(change.to);
      const status = isValid ? '  ' : '! ';

      console.log(`${status}  ${change.from}`);
      console.log(`    -> ${change.to}`);

      if (!isValid) {
        brokenLinks.push({
          file: relativePath,
          link: change.to,
          original: change.from,
        });
      }
    }

    if (!DRY_RUN) {
      fs.writeFileSync(filePath, result.updated, 'utf-8');
    }
  }
}

console.log(`\n${'─'.repeat(60)}`);
console.log(`\nSummary:`);
console.log(`   Files scanned: ${files.length}`);
console.log(`   Files with changes: ${filesChanged}`);
console.log(`   Total link updates: ${totalChanges}`);

if (brokenLinks.length > 0) {
  console.log(`\n!  Potential broken links (${brokenLinks.length}):`);
  for (const bl of brokenLinks) {
    console.log(`   ${bl.file}: ${bl.link}`);
  }
}

if (DRY_RUN && totalChanges > 0) {
  console.log(`\nRun with --write to apply these changes`);
}

console.log('');
