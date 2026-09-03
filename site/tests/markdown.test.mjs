import assert from 'node:assert/strict';
import test from 'node:test';

import { renderSafeMarkdown } from '../src/lib/markdown.mjs';

test('blocks executable and entity-obfuscated link protocols', () => {
  for (const payload of [
    '[click](javascript:alert(1))',
    '[click](java&#x73;cript:alert(1))',
    '[click](data:text/html,boom)',
    '[click](//evil.example/path)',
  ]) {
    const { html } = renderSafeMarkdown(payload);
    assert.doesNotMatch(html, /href=/i);
    assert.doesNotMatch(html, /javascript:/i);
  }
});

test('escapes raw HTML instead of trying to sanitize it with regular expressions', () => {
  const { html } = renderSafeMarkdown('<img src=x onerror="alert(1)">');
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<img/i);
});

test('adds matching unique heading ids and table-of-contents entries', () => {
  const { html, toc } = renderSafeMarkdown('## Same\n\n## Same');
  assert.deepEqual(toc.map((item) => item.id), ['same', 'same-1']);
  assert.match(html, /id="same"/);
  assert.match(html, /id="same-1"/);
});

test('keeps safe external links isolated from the opener', () => {
  const { html } = renderSafeMarkdown('[docs](https://example.com?a=1&b=2)');
  assert.match(html, /href="https:\/\/example\.com\?a=1&amp;b=2"/);
  assert.match(html, /rel="nofollow noopener noreferrer"/);
});
