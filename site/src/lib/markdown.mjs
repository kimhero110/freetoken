import { Marked, Renderer } from 'marked';

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function safeUrl(value, image = false) {
  const url = String(value ?? '').trim();
  if (!url || /[\u0000-\u001f\u007f]/.test(url)) return null;
  if (url.startsWith('//')) return null;
  if (/^(?:\/|\.\/|\.\.\/|#)/.test(url)) return url;
  if (/^https?:\/\//i.test(url)) return url;
  if (!image && /^mailto:/i.test(url)) return url;
  return null;
}

function createSlugger() {
  const counts = new Map();
  return (text) => {
    const base = String(text ?? '')
      .toLowerCase()
      .replace(/<[^>]*>/g, '')
      .replace(/[^\w\u4e00-\u9fa5]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'section';
    const count = counts.get(base) ?? 0;
    counts.set(base, count + 1);
    return count === 0 ? base : `${base}-${count}`;
  };
}

export function renderSafeMarkdown(markdown) {
  const source = String(markdown ?? '');
  const tocSlug = createSlugger();
  const toc = [...source.matchAll(/^(#{2,3})\s+(.+)$/gm)].map((match) => ({
    level: match[1].length,
    text: match[2].trim(),
    id: tocSlug(match[2].trim()),
  }));

  const headingSlug = createSlugger();
  const renderer = new Renderer();
  renderer.html = ({ text }) => escapeHtml(text);
  renderer.link = function ({ href, title, tokens }) {
    const cleanHref = safeUrl(href);
    const text = this.parser.parseInline(tokens);
    if (!cleanHref) return `<span>${text}</span>`;
    const external = /^https?:\/\//i.test(cleanHref);
    const rel = external ? ' rel="nofollow noopener noreferrer" target="_blank"' : '';
    const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
    return `<a href="${escapeHtml(cleanHref)}"${rel}${titleAttr}>${text}</a>`;
  };
  renderer.image = ({ href, title, text }) => {
    const cleanHref = safeUrl(href, true);
    if (!cleanHref) return '';
    const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
    return `<img src="${escapeHtml(cleanHref)}" alt="${escapeHtml(text)}"${titleAttr} loading="lazy" />`;
  };
  renderer.heading = function ({ depth, text, tokens }) {
    const content = this.parser.parseInline(tokens);
    const id = headingSlug(text);
    return `<h${depth} id="${escapeHtml(id)}">${content}</h${depth}>\n`;
  };

  const parser = new Marked({ renderer });
  return { html: parser.parse(source), toc };
}
