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

/** Hosts/schemes that are never local links. */
const EXTERNAL = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;

/**
 * Read a `--flag value` pair out of an argv array.
 *
 * @param {string[]} argv - Arguments to search
 * @param {string} name - Flag name, including leading dashes
 * @returns {string|undefined} The value, or undefined when absent
 */
function flagValue(argv, name) {
  const at = argv.indexOf(name);
  return at === -1 ? undefined : argv[at + 1];
}

/**
 * Resolve where to look, from argv, defaulting to this repository.
 *
 * The directory overrides exist so the checks can be pointed at a fixture
 * tree. Without them every path derives from `__dirname` and the tool can
 * only ever inspect its own repo, which makes it untestable: the logic that
 * decides whether a merge is blocked would itself be unverified.
 *
 * @param {string[]} [argv] - Defaults to the real process arguments
 * @returns {{projectRoot: string, docsDir: string, buildDir: string, strict: boolean, verbose: boolean, requireBuild: boolean}} Config
 */
function resolveConfig(argv = process.argv.slice(2)) {
  const projectRoot = flagValue(argv, '--project-root') ?? path.resolve(__dirname, '..');

  return {
    projectRoot,
    docsDir: flagValue(argv, '--docs-dir') ?? path.join(projectRoot, 'docs'),
    buildDir: flagValue(argv, '--build-dir') ?? path.join(projectRoot, 'build', 'site'),
    strict: argv.includes('--strict'),
    verbose: argv.includes('--verbose'),
    requireBuild: argv.includes('--require-build'),
  };
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
function checkSource({ projectRoot, docsDir }, report) {
  const files = walk(docsDir, new Set(['.md']));

  for (const file of files) {
    const rel = path.relative(projectRoot, file);
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
      // whereas the rewriter treats docs/ as the site root, so `/architecture.md`
      // becomes the valid route /architecture/ while pointing at a repo-root
      // file that does not exist. The built pass only ever sees the route, so
      // it cannot notice. Resolve against the repo root, which is the surface
      // this pass is responsible for.
      //
      // Note `/docs/architecture.md` is CORRECT on both: repo-root
      // docs/architecture.md exists, and the rewriter strips the `/docs`
      // prefix. Existence is the test, not the prefix.
      const resolved = target.startsWith('/') ? path.join(projectRoot, target) : path.resolve(dir, target);

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
async function resolveBase({ projectRoot, buildDir }) {
  const rootIndex = path.join(buildDir, 'index.html');

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
    const mod = await import(`file://${path.join(projectRoot, 'website', 'src', 'lib', 'site-url.js')}`);
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
function checkBuilt({ projectRoot, buildDir }, base, report) {
  const pages = walk(buildDir, new Set(['.html']));

  for (const page of pages) {
    const rel = path.relative(projectRoot, page);
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
        resolved = path.join(buildDir, withoutBase);
      } else {
        resolved = path.resolve(pageDir, target);
      }

      // Never let a link escape the build root.
      if (!resolved.startsWith(buildDir + path.sep)) {
        report(rel, `${attr} escapes the site root: ${href}`);
        continue;
      }

      const candidate = target.endsWith('/') || !path.extname(resolved) ? path.join(resolved, 'index.html') : resolved;

      if (!fs.existsSync(candidate)) {
        report(rel, `${attr} resolves to nothing: ${href} (looked for ${path.relative(buildDir, candidate)})`);
      }
    }
  }

  return pages.length;
}

// ---------------------------------------------------------------------------

/**
 * Run both passes and return what happened, without touching the process.
 *
 * Separated from the CLI so tests can drive it against a fixture tree and
 * assert on the result rather than on stdout or an exit code.
 *
 * @param {object} cfg - From resolveConfig()
 * @param {(msg: string) => void} [log] - Output sink; defaults to console.log
 * @returns {Promise<{issues: Array<{file: string, detail: string}>, sourceCount: number, builtCount: number, haveBuild: boolean, missingRequiredBuild: boolean, ok: boolean}>} Outcome
 */
async function run(cfg, log = console.log) {
  const issues = [];
  const report = (file, detail) => issues.push({ file, detail });

  log(`\nValidating documentation links in: ${cfg.projectRoot}`);
  log(`Mode: ${cfg.strict ? 'STRICT (exit 1 on issues)' : 'ADVISORY'}`);
  log('');

  if (!fs.existsSync(cfg.docsDir)) {
    throw new Error(`docs/ not found at ${cfg.docsDir}`);
  }

  const sourceCount = checkSource(cfg, report);
  log(`Source pass:  ${sourceCount} markdown file(s) in docs/`);

  let builtCount = 0;
  const haveBuild = fs.existsSync(cfg.buildDir);
  let missingRequiredBuild = false;

  if (haveBuild) {
    const base = await resolveBase(cfg);
    builtCount = checkBuilt(cfg, base, report);
    log(`Built pass:   ${builtCount} page(s) in build/site (base ${base})`);

    // This pass is only as honest as the build it reads. Astro caches rendered
    // content in website/node_modules/.astro, and that cache survives both
    // `rm -rf website/.astro` and a rebuild, so a stale render can report a
    // clean pass against source that is actually broken (this bit the author
    // while writing this tool). CI is immune because `npm ci` starts cold.
    // Suppressed under --require-build, which is the CI path.
    if (!cfg.requireBuild) {
      log('');
      log('   Reading an existing build. If results look impossible, the render');
      log('   may be cached. Clear it and rebuild:');
      log('     rm -rf website/node_modules/.astro website/node_modules/.vite website/.astro build/site');
      log('     npm run docs:build');
    }
  } else if (cfg.requireBuild) {
    missingRequiredBuild = true;
    report('build/site', 'no build found, and --require-build was given. Run `npm run docs:build` first.');
  } else {
    log('Built pass:   SKIPPED (no build/site). This pass is what catches route bugs.');
    log('              Run `npm run docs:build` first, or pass --require-build to enforce it.');
  }

  log('');
  log('\u2500'.repeat(60));
  log('');

  if (issues.length === 0) {
    log('Summary:');
    log(`   Markdown files: ${sourceCount}`);
    log(`   Built pages:    ${builtCount}${haveBuild ? '' : ' (skipped)'}`);
    log('');

    // Never report an unqualified pass when the load-bearing pass did not run.
    // A green line that means "half the checks were skipped" is the exact
    // failure mode this tool exists to prevent, and reading one as a full pass
    // is how the broken links reached production in the first place.
    if (haveBuild) {
      log('   All documentation links valid!');
    } else {
      log('   Source links valid. THE BUILT-OUTPUT PASS DID NOT RUN, so');
      log('   route bugs (the class that shipped 404s) are unchecked here.');
      log('   Run `npm run docs:build` first for the full check. CI always does.');
    }
    log('');
  } else {
    const byFile = new Map();
    for (const issue of issues) {
      if (!byFile.has(issue.file)) {
        byFile.set(issue.file, []);
      }
      byFile.get(issue.file).push(issue.detail);
    }

    log(`Broken documentation links: ${issues.length}\n`);
    for (const [file, details] of byFile) {
      log(`  ${file}`);
      for (const detail of details) {
        log(`    - ${detail}`);
      }
    }
    log('');

    if (cfg.verbose) {
      log('A route that resolves to nothing is still valid HTML, so neither');
      log('Astro nor markdownlint will fail on it. That is why this check exists.\n');
    }
  }

  // --require-build is a fail-closed contract in its own right: the flag exists
  // to turn the skipped built pass into an error, so honouring it must not
  // depend on --strict also being passed. Everything else stays advisory.
  const ok = !(issues.length > 0 && (cfg.strict || missingRequiredBuild));

  return { issues, sourceCount, builtCount, haveBuild, missingRequiredBuild, ok };
}

module.exports = { resolveConfig, run, checkSource, checkBuilt, resolveBase, blankCode, assetUrls, walk };

/* c8 ignore start -- CLI entry point */
if (require.main === module) {
  run(resolveConfig())
    .then((result) => {
      if (!result.ok) {
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error(error.message);
      process.exit(1);
    });
}
/* c8 ignore stop */
