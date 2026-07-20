/**
 * Validate documentation links, in the source AND in the built site.
 *
 * WHY THIS EXISTS
 *
 * `docs/` is read in two places: rendered on GitHub, and published as the
 * site. A link can be valid in one and dead in the other, and nothing fails
 * on it: an href that resolves nowhere is still valid HTML, so Astro builds
 * clean and markdownlint has no opinion. `validate-doc-links.js` covers the
 * source side (site-absolute targets and anchors) but never sees the built
 * output, so a link that is correct in the Markdown and wrong as a route
 * passes every check and ships.
 *
 * A source-only check is therefore NOT sufficient, and that is the lesson
 * this tool encodes. Rewriting happens between the Markdown and the page:
 * `website/src/rehype-markdown-links.js` turns `.md` targets into routes, so
 * a bug there produces hrefs that look right in source and 404 in a browser.
 * Only resolving the BUILT output against the file tree catches that class.
 *
 * So there are two passes:
 *
 *   1. SOURCE  (docs/ *.md) - a relative `.md` target must exist on disk.
 *              Cheap, and catches a typo before a build is needed.
 *   2. BUILT   (build/site/ *.html) - every internal href must resolve to a
 *              real file. This is the pass that catches plugin bugs, base-path
 *              bugs, and anything else that only manifests as a route.
 *
 * The built pass is skipped with a warning when no build is present, so the
 * tool stays usable locally without a build step. CI builds the site, so the
 * pass runs there. Use --require-build to make a missing build an error.
 *
 * Usage:
 *   node tools/validate-docs-links.js [--strict] [--verbose] [--require-build]
 */

const fs = require('node:fs');
const path = require('node:path');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const DOCS_DIR = path.join(PROJECT_ROOT, 'docs');
const BUILD_DIR = path.join(PROJECT_ROOT, 'build', 'site');

const STRICT = process.argv.includes('--strict');
const VERBOSE = process.argv.includes('--verbose');
const REQUIRE_BUILD = process.argv.includes('--require-build');

/**
 * Whether to print the stale-cache hint. Suppressed under --require-build,
 * which is the CI path: CI installs cold, so its build is never stale.
 */
const STALE_HINT = !REQUIRE_BUILD;

/** Hosts/schemes that are never local links. */
const EXTERNAL = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;

const issues = [];

/**
 * Record a problem.
 *
 * @param {string} file - Repo-relative file the problem is in
 * @param {string} detail - What is wrong
 */
function report(file, detail) {
  issues.push({ file, detail });
}

/**
 * Recursively collect files with one of the given extensions.
 *
 * @param {string} dir - Directory to walk
 * @param {Set<string>} exts - Extensions to keep, with leading dot
 * @param {string[]} [out] - Accumulator
 * @returns {string[]} Absolute paths
 */
function walk(dir, exts, out = []) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }

  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.git') {
        continue;
      }
      walk(full, exts, out);
    } else if (exts.has(path.extname(entry.name))) {
      out.push(full);
    }
  }

  return out;
}

/** Strip the query and anchor from an href, returning the path portion. */
function pathPortion(href) {
  const q = href.indexOf('?');
  const h = href.indexOf('#');
  const first = Math.min(q === -1 ? Infinity : q, h === -1 ? Infinity : h);
  return first === Infinity ? href : href.slice(0, first);
}

// ---------------------------------------------------------------------------
// Pass 1: source
// ---------------------------------------------------------------------------

/** Markdown inline links: the target inside `](...)`. */
const MD_LINK = /\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;

/**
 * Blank out code so a link that is merely *shown* is not read as a real one.
 *
 * `MD_LINK` is a regex over raw text, so it cannot tell a link from a picture
 * of a link. Without this, documenting the link convention itself, e.g. a
 * ```markdown block containing [label](./example.md), fails the build as a
 * broken link, and the only way to appease it is to create the placeholder
 * file. (`tools/validate-file-refs.js` does NOT do this, so it carries the
 * same latent false positive; worth fixing there too if it ever fires.)
 *
 * Fences are tracked line by line rather than matched as a pair, so an
 * unterminated fence blanks to end of file instead of silently reverting to
 * prose scanning. Inline spans are only stripped outside a fence, so a stray
 * backtick inside a block cannot pair with one outside it. Line count is
 * preserved, which keeps byte offsets usable if this ever reports positions.
 *
 * @param {string} text - Raw Markdown
 * @returns {string} The same text with fenced blocks and code spans blanked
 */
function blankCode(text) {
  let fence = null;

  return text
    .split('\n')
    .map((line) => {
      const marker = line.match(/^\s{0,3}(`{3,}|~{3,})/);

      if (fence) {
        // A closing fence is the same character, and at least as long.
        if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length) {
          fence = null;
        }
        return '';
      }
      if (marker) {
        fence = marker[1];
        return '';
      }

      // Inline spans: a run of N backticks closes on a run of N.
      return line.replaceAll(/(`+)[^`]*\1/g, ' ');
    })
    .join('\n');
}

/**
 * Check that every relative `.md` target in docs/ exists on disk.
 *
 * Deliberately does NOT enforce a `./` prefix. The plugin accepts bare links,
 * and GitHub renders them correctly, so requiring the prefix would be style,
 * not correctness. What matters is that the target exists.
 */
function checkSource() {
  const files = walk(DOCS_DIR, new Set(['.md']));

  for (const file of files) {
    const rel = path.relative(PROJECT_ROOT, file);
    const dir = path.dirname(file);
    const text = blankCode(fs.readFileSync(file, 'utf8'));

    for (const match of text.matchAll(MD_LINK)) {
      const target = pathPortion(match[1]);

      if (!target || target.startsWith('#') || EXTERNAL.test(target)) {
        continue;
      }
      if (!target.endsWith('.md')) {
        continue;
      }
      // Root-absolute targets mean different things on the two surfaces, and
      // this pass owns the GitHub one. GitHub resolves `/x.md` against the
      // REPOSITORY root (it rewrites the href to /<owner>/<repo>/blob/<ref>/x.md),
      // whereas the rewriter treats docs/ as the site root, so `/agents.md`
      // becomes the valid route /agents/ while pointing at a repo-root file
      // that does not exist. The built pass only ever sees the route, so it
      // cannot notice. Resolve against the repo root, which is the surface
      // this pass is responsible for.
      //
      // Note `/docs/agents.md` is CORRECT on both: repo-root docs/agents.md
      // exists, and the rewriter strips the `/docs` prefix. Existence is the
      // test, not the prefix.
      const resolved = target.startsWith('/') ? path.join(PROJECT_ROOT, target) : path.resolve(dir, target);

      if (!fs.existsSync(resolved)) {
        report(
          rel,
          target.startsWith('/')
            ? `root-absolute link target does not exist at the repository root, so it is dead on GitHub: ${match[1]}`
            : `link target does not exist: ${match[1]}`,
        );
      }
    }
  }

  return files.length;
}

// ---------------------------------------------------------------------------
// Pass 2: built output
// ---------------------------------------------------------------------------

/** Normalize a URL pathname into a base with exactly one trailing slash. */
function asBase(pathname) {
  if (!pathname || pathname === '/') {
    return '/';
  }
  return pathname.endsWith('/') ? pathname : `${pathname}/`;
}

/**
 * Resolve the base path the build on disk was actually produced with.
 *
 * Read from the ARTIFACT, not the environment. The environment can disagree
 * with the build (a site built with SITE_URL set, then validated without it),
 * and that disagreement makes every absolute href look broken: a loud, and
 * entirely false, failure. The root page's canonical URL is written by the
 * build itself, so it cannot drift from the output it describes.
 *
 * Falls back to the environment, then to '/', when no canonical is present.
 *
 * @returns {Promise<string>} The base path, e.g. '/repo/' or '/'
 */
async function resolveBase() {
  const rootIndex = path.join(BUILD_DIR, 'index.html');

  if (fs.existsSync(rootIndex)) {
    const html = fs.readFileSync(rootIndex, 'utf8');
    const canonical =
      html.match(/<link[^>]+rel="canonical"[^>]+href="([^"]+)"/i) || html.match(/<meta[^>]+property="og:url"[^>]+content="([^"]+)"/i);

    if (canonical) {
      try {
        return asBase(new URL(canonical[1]).pathname);
      } catch {
        // Not an absolute URL; fall through to the environment.
      }
    }
  }

  try {
    const mod = await import(`file://${path.join(PROJECT_ROOT, 'website', 'src', 'lib', 'site-url.js')}`);
    return asBase(new URL(mod.getSiteUrl()).pathname);
  } catch {
    return '/';
  }
}

/**
 * Every URL a page asks the browser to fetch: navigations AND subresources.
 *
 * `href` alone is not the whole surface. A missing `src` is the same defect
 * with a worse symptom: the browser fetches it without the user clicking, and
 * a 404 script or image degrades the page silently. This matters here because
 * assets under `website/public/` are copied verbatim and referenced by
 * hand-written string paths (see `mermaid-lightbox.js` in astro.config.mjs),
 * so renaming one leaves a green build and a dead reference on every page.
 *
 * `srcset` is a comma-separated candidate list where each entry is a URL
 * optionally followed by a width/density descriptor, so it is split apart.
 * The build emits no `srcset` today, only SVGs, but adding one raster image
 * to the docs would change that without touching this file.
 *
 * @param {string} html - Full page source
 * @returns {Array<{attr: string, url: string}>} References, in document order
 */
function assetUrls(html) {
  const refs = [];

  // `src` here never matches `srcset=`, which continues with `set=`.
  for (const match of html.matchAll(/\s(href|src)="([^"]*)"/g)) {
    refs.push({ attr: match[1], url: match[2] });
  }

  for (const match of html.matchAll(/\ssrcset="([^"]*)"/g)) {
    for (const candidate of match[1].split(',')) {
      const url = candidate.trim().split(/\s+/)[0];
      if (url) {
        refs.push({ attr: 'srcset', url });
      }
    }
  }

  return refs;
}

/**
 * Verify every internal reference in the built site resolves to a real file.
 *
 * Covers navigations (`href`) and subresources (`src`, `srcset`) alike: both
 * are URLs the page promises the browser it can fetch.
 *
 * A route ending in `/` must have an `index.html`; anything else must exist
 * as a file. Relative URLs are resolved against the page's own directory,
 * which is precisely how a browser resolves them, and precisely the step that
 * the earlier page-relative bug failed.
 *
 * @param {string} base - Deployment base path
 * @returns {number} Number of HTML pages checked
 */
function checkBuilt(base) {
  const pages = walk(BUILD_DIR, new Set(['.html']));

  for (const page of pages) {
    const rel = path.relative(PROJECT_ROOT, page);
    const html = fs.readFileSync(page, 'utf8');
    // The page's URL directory, e.g. build/site/troubleshooting/index.html
    // is served at /troubleshooting/, so relative links resolve from there.
    const pageDir = path.dirname(page);

    const seen = new Set();

    for (const { attr, url: href } of assetUrls(html)) {
      if (!href || href.startsWith('#') || EXTERNAL.test(href) || seen.has(href)) {
        continue;
      }
      seen.add(href);

      const target = pathPortion(href);
      if (!target) {
        continue;
      }

      let resolved;
      if (target.startsWith('/')) {
        // Root-absolute: strip the base, then read from the build root.
        let withoutBase = target;
        if (base !== '/' && target.startsWith(base)) {
          withoutBase = `/${target.slice(base.length)}`;
        } else if (base !== '/') {
          report(rel, `absolute ${attr} is missing the base path ${base}: ${href}`);
          continue;
        }
        resolved = path.join(BUILD_DIR, withoutBase);
      } else {
        resolved = path.resolve(pageDir, target);
      }

      // Never let a link escape the build root.
      if (!resolved.startsWith(BUILD_DIR)) {
        report(rel, `${attr} escapes the site root: ${href}`);
        continue;
      }

      const candidate = target.endsWith('/') || !path.extname(resolved) ? path.join(resolved, 'index.html') : resolved;

      if (!fs.existsSync(candidate)) {
        report(rel, `${attr} resolves to nothing: ${href} (looked for ${path.relative(BUILD_DIR, candidate)})`);
      }
    }
  }

  return pages.length;
}

// ---------------------------------------------------------------------------

async function main() {
  console.log(`\nValidating documentation links in: ${PROJECT_ROOT}`);
  console.log(`Mode: ${STRICT ? 'STRICT (exit 1 on issues)' : 'ADVISORY'}`);
  console.log();

  if (!fs.existsSync(DOCS_DIR)) {
    console.error(`docs/ not found at ${DOCS_DIR}`);
    process.exit(1);
  }

  const sourceCount = checkSource();
  console.log(`Source pass:  ${sourceCount} markdown file(s) in docs/`);

  let builtCount = 0;
  const haveBuild = fs.existsSync(BUILD_DIR);
  let missingRequiredBuild = false;

  if (haveBuild) {
    const base = await resolveBase();
    builtCount = checkBuilt(base);
    console.log(`Built pass:   ${builtCount} page(s) in build/site (base ${base})`);

    // This pass is only as honest as the build it reads. Astro caches rendered
    // content in website/node_modules/.astro, and that cache survives both
    // `rm -rf website/.astro` and a rebuild, so a stale render can report a
    // clean pass against source that is actually broken (this bit the author
    // while writing this tool). CI is immune because `npm ci` starts cold.
    if (STALE_HINT) {
      console.log();
      console.log('   Reading an existing build. If results look impossible, the render');
      console.log('   may be cached. Clear it and rebuild:');
      console.log('     rm -rf website/node_modules/.astro website/node_modules/.vite website/.astro build/site');
      console.log('     npm run docs:build');
    }
  } else if (REQUIRE_BUILD) {
    missingRequiredBuild = true;
    report('build/site', 'no build found, and --require-build was given. Run `npm run docs:build` first.');
  } else {
    console.log('Built pass:   SKIPPED (no build/site). This pass is what catches route bugs.');
    console.log('              Run `npm run docs:build` first, or pass --require-build to enforce it.');
  }

  console.log();
  console.log('─'.repeat(60));
  console.log();

  if (issues.length === 0) {
    console.log('Summary:');
    console.log(`   Markdown files: ${sourceCount}`);
    console.log(`   Built pages:    ${builtCount}${haveBuild ? '' : ' (skipped)'}`);
    console.log();

    // Never report an unqualified pass when the load-bearing pass did not run.
    // A green line that means "half the checks were skipped" is the exact
    // failure mode this tool exists to prevent, and reading one as a full pass
    // is how the broken links reached production in the first place.
    if (haveBuild) {
      console.log('   All documentation links valid!');
    } else {
      console.log('   Source links valid. THE BUILT-OUTPUT PASS DID NOT RUN, so');
      console.log('   route bugs (the class that shipped 404s) are unchecked here.');
      console.log('   Run `npm run docs:build` first for the full check. CI always does.');
    }
    console.log();
    return;
  }

  const byFile = new Map();
  for (const issue of issues) {
    if (!byFile.has(issue.file)) {
      byFile.set(issue.file, []);
    }
    byFile.get(issue.file).push(issue.detail);
  }

  console.log(`Broken documentation links: ${issues.length}\n`);
  for (const [file, details] of byFile) {
    console.log(`  ${file}`);
    for (const detail of details) {
      console.log(`    - ${detail}`);
    }
  }
  console.log();

  if (VERBOSE) {
    console.log('A route that resolves to nothing is still valid HTML, so neither');
    console.log('Astro nor markdownlint will fail on it. That is why this check exists.\n');
  }

  // --require-build is a fail-closed contract in its own right: the flag exists
  // to turn the skipped built pass into an error, so honouring it must not
  // depend on --strict also being passed. Everything else stays advisory.
  if (STRICT || missingRequiredBuild) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
