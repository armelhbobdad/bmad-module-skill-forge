/**
 * Rehype plugin to transform markdown file links (.md) into page routes.
 *
 * Transforms (from a page whose source is `docs/troubleshooting.md`, base `/site/`):
 *   ./architecture.md          → /site/architecture/
 *   architecture.md            → /site/architecture/
 *   ./guide/index.md           → /site/guide/
 *   ../workflows.md#anchor    → /site/workflows/#anchor
 *   ./file.md?query=param      → /site/file/?query=param
 *   /docs/absolute/file.md     → /site/absolute/file/
 *
 * WHY THE OUTPUT IS ROOT-ABSOLUTE, NOT RELATIVE
 *
 * Astro builds with `format: 'directory'`, so `docs/troubleshooting.md` is
 * served at `/troubleshooting/` (a directory), not `/troubleshooting.html`.
 * An earlier version of this plugin rewrote `./architecture.md` to the
 * page-relative `./architecture/`, which the browser resolves against the
 * page's own directory: `/troubleshooting/architecture/`. That 404s. The
 * sibling page actually lives at `/architecture/`, one level up.
 *
 * Emitting a root-absolute route (base + path) sidesteps relative resolution
 * entirely and matches what the sidebar already emits. It is correct at any
 * nesting depth, whereas a relative rewrite would have to know how deep the
 * current page sits.
 *
 * WHY BARE LINKS ARE ACCEPTED
 *
 * `[gate model](workflows.md)` (no `./`) is a valid sibling link on GitHub,
 * which is the other place docs/ is read. The previous version only rewrote
 * hrefs beginning `./`, `../`, or `/`, so bare ones shipped verbatim and 404'd
 * on the site. They are treated as page-relative here, exactly as GitHub and
 * the file system treat them.
 *
 * Source paths are resolved relative to the docs content root so a link from a
 * nested page (`docs/_internal/STABILITY.md → ../architecture.md`) lands on the
 * same route as the equivalent link from a top-level page.
 *
 * External links (://, mailto:, tel:) and non-.md targets are left untouched.
 */

import { visit } from 'unist-util-visit';

/** Path segments that mark the start of the docs content root, longest first. */
const CONTENT_ROOT_MARKERS = ['/src/content/docs/', '/content/docs/', '/docs/'];

/**
 * The page's directory, relative to the docs content root, in POSIX form.
 *
 * Returns '' for a top-level page and e.g. '_internal' for a nested one.
 * Falls back to '' when the source path is unavailable (the flat-docs shape),
 * which keeps top-level links correct even without VFile path information.
 *
 * @param {string|undefined} filePath - Absolute source path of the page
 * @returns {string} POSIX-style directory, '' at the root
 */
function pageDirFromSource(filePath) {
  if (typeof filePath !== 'string' || !filePath) {
    return '';
  }

  const normalized = filePath.replace(/\\/g, '/');

  for (const marker of CONTENT_ROOT_MARKERS) {
    const at = normalized.lastIndexOf(marker);
    if (at !== -1) {
      const rel = normalized.slice(at + marker.length);
      const lastSlash = rel.lastIndexOf('/');
      return lastSlash === -1 ? '' : rel.slice(0, lastSlash);
    }
  }

  return '';
}

/**
 * Resolve `target` against `dir`, collapsing `.` and `..` segments.
 *
 * Segments that would escape the content root are dropped, mirroring how the
 * site serves docs/ as its root: there is nothing above it to address.
 *
 * @param {string} dir - Page directory relative to the content root
 * @param {string} target - Link target, relative or root-absolute
 * @returns {string} Normalized path relative to the content root
 */
function resolveAgainst(dir, target) {
  const fromRoot = target.startsWith('/');
  const base = fromRoot ? [] : dir.split('/').filter(Boolean);
  const out = base.slice();

  for (const segment of target.split('/')) {
    if (segment === '' || segment === '.') {
      continue;
    }
    if (segment === '..') {
      out.pop();
      continue;
    }
    out.push(segment);
  }

  return out.join('/');
}

/**
 * Split an href into its path, query, and anchor parts.
 *
 * @param {string} href - The raw href
 * @returns {{path: string, query: string, anchor: string}} The three parts
 */
function splitHref(href) {
  const q = href.indexOf('?');
  const h = href.indexOf('#');
  const first = Math.min(q === -1 ? Infinity : q, h === -1 ? Infinity : h);

  if (first === Infinity) {
    return { path: href, query: '', anchor: '' };
  }

  const path = href.slice(0, first);
  const suffix = href.slice(first);

  if (!suffix.startsWith('?')) {
    return { path, query: '', anchor: suffix };
  }

  const anchorAt = suffix.indexOf('#');
  return anchorAt === -1
    ? { path, query: suffix, anchor: '' }
    : { path, query: suffix.slice(0, anchorAt), anchor: suffix.slice(anchorAt) };
}

/**
 * Create a rehype plugin that turns Markdown `.md` links into page routes.
 *
 * @param {Object} options - Plugin options
 * @param {string} options.base - Base path for the deployment (e.g. '/site/')
 * @returns {function} A HAST tree transformer
 */
export default function rehypeMarkdownLinks(options = {}) {
  const base = options.base || '/';
  // Normalize to exactly one leading and one trailing slash.
  const normalizedBase = base === '/' ? '/' : `/${base.replace(/^\/+|\/+$/g, '')}/`;

  return (tree, file) => {
    const pageDir = pageDirFromSource(file?.path ?? file?.history?.[0]);

    visit(tree, 'element', (node) => {
      if (node.tagName !== 'a' || !node.properties?.href) {
        return;
      }

      const href = node.properties.href;

      if (typeof href !== 'string') {
        return;
      }

      // External and protocol links are never rewritten.
      if (href.includes('://') || href.startsWith('mailto:') || href.startsWith('tel:')) {
        return;
      }

      const { path, query, anchor } = splitHref(href);

      // Only .md targets become routes. A bare '#anchor' has no path at all.
      if (!path.endsWith('.md')) {
        return;
      }

      // The site serves docs/ as its root, so an absolute '/docs/x.md' and an
      // absolute '/x.md' address the same page.
      const target = path.startsWith('/docs/') ? path.slice('/docs'.length) : path;

      let resolved = resolveAgainst(pageDir, target);

      // 'index.md' is the directory itself; anything else keeps its own segment.
      // Match the whole basename, not a suffix: 'myindex.md' and 'reindex.md'
      // both END with 'index.md' but are ordinary pages, and treating them as
      // an index silently truncated them to '/my' and '/re'.
      const isIndex = resolved === 'index.md' || resolved.endsWith('/index.md');
      resolved = isIndex ? resolved.slice(0, -'index.md'.length) : `${resolved.slice(0, -'.md'.length)}/`;

      // Collapse any doubled slash from an empty resolution (root index.md).
      const route = `${normalizedBase}${resolved}`.replace(/\/{2,}/g, '/');

      node.properties.href = `${route}${query}${anchor}`;
    });
  };
}
