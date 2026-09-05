import assert from 'node:assert/strict';
import test from 'node:test';

import {
  generateSnippet,
  getCompatiblePlatforms,
  getOperationToolState,
  getToolState,
  normalizeChatOperation,
  VERIFICATION_LABELS,
} from '../src/lib/operation-generator.mjs';

function operation(status = 'documented') {
  return {
    id: 'chat_completions', protocol: 'openai',
    endpoint_url: 'https://api.example.com/openai/v1/chat/completions',
    models: ['safe-model'],
    auth: { type: 'bearer', header: 'Authorization', query_param: null, env_var: 'EXAMPLE_API_KEY' },
    verification: { status, checked_at: status === 'claimed' ? null : '2026-09-03', evidence_url: status === 'claimed' ? null : 'https://docs.example.com' },
  };
}

const tools = { curl: 'claimed', openai_python: 'documented', openai_node: 'live', cursor: 'unknown' };

function restOperation() {
  return {
    id: 'search', protocol: 'rest', endpoint_url: 'https://api.tavily.com/search', method: 'POST',
    request_body: { query: 'What is new?', search_depth: 'basic', max_results: 5 }, models: [],
    auth: { type: 'api_key_header', header: 'X-API-Key', query_param: null, env_var: 'TAVILY_API_KEY' },
    verification: { status: 'documented', checked_at: '2026-09-03', evidence_url: 'https://docs.tavily.com' },
  };
}

test('preserves the exact canonical endpoint and removes only the exact chat suffix', () => {
  const normalized = normalizeChatOperation(operation());
  assert.equal(normalized.endpoint_url, 'https://api.example.com/openai/v1/chat/completions');
  assert.equal(normalized.base_url, 'https://api.example.com/openai/v1');
  assert.match(generateSnippet(operation(), 'safe-model', 'curl'), /api\.example\.com\/openai\/v1\/chat\/completions/);
  assert.doesNotMatch(generateSnippet(operation(), 'safe-model', 'curl'), /chat\/completions\/chat\/completions/);
});

test('references environment variables and never embeds a supplied-looking literal key', () => {
  for (const format of ['curl', 'python', 'node', 'freellmapi']) {
    const output = generateSnippet(operation(), 'safe-model', format, { apiKey: 'sk-literal-secret' });
    assert.match(output, /EXAMPLE_API_KEY/);
    assert.doesNotMatch(output, /sk-literal-secret|YOUR_API_KEY/);
  }
});

test('rejects shell metacharacters, unsafe auth, unknown models, and unsupported operations', () => {
  assert.throws(() => normalizeChatOperation({ ...operation(), endpoint_url: 'https://api.example.com/$(whoami)/chat/completions' }), /unsafe/);
  assert.throws(() => normalizeChatOperation({ ...operation(), endpoint_url: 'https://api.example.com/{account_id}/chat/completions' }), /unsafe/);
  assert.throws(() => generateSnippet(operation(), 'safe-model; rm -rf', 'curl'), /unsafe/);
  assert.throws(() => generateSnippet(operation(), 'other-model', 'curl'), /not offered/);
  assert.throws(() => normalizeChatOperation({ ...operation(), id: 'search' }), /Only OpenAI/);
  assert.throws(() => normalizeChatOperation({ ...operation(), auth: { ...operation().auth, env_var: 'bad key' } }), /authentication/);
});

test('only documented and recently live operations are executable', () => {
  assert.doesNotThrow(() => normalizeChatOperation(operation('documented')));
  const live = operation('live');
  live.verification.checked_at = new Date().toISOString().slice(0, 10);
  assert.doesNotThrow(() => normalizeChatOperation(live));
  for (const status of ['claimed', 'failed', 'unknown']) assert.throws(() => normalizeChatOperation(operation(status)), /verification/);
  live.verification.checked_at = '2020-01-01';
  assert.throws(() => normalizeChatOperation(live), /stale/);
});

test('unknown application tools are disabled with multilingual reasons', () => {
  const en = getToolState(tools, 'cursor', 'en');
  const zh = getToolState(tools, 'cursor', 'zh');
  assert.equal(en.enabled, false);
  assert.equal(zh.enabled, false);
  assert.match(en.reason, /unknown/i);
  assert.match(zh.reason, /未知/);
  assert.match(VERIFICATION_LABELS.en.documented, /documentation checked/i);
  assert.match(VERIFICATION_LABELS.zh.claimed, /文档未核查/);
});

test('compatible platform selection handles empty and excludes inactive or unsupported entries', () => {
  assert.deepEqual(getCompatiblePlatforms([]), []);
  assert.deepEqual(getCompatiblePlatforms(null), []);
  const base = { slug: 'example', name: 'Example', status: 'active', capabilities: { operations: [operation()], tools } };
  assert.equal(getCompatiblePlatforms([base]).length, 1);
  assert.equal(getCompatiblePlatforms([{ ...base, status: 'expired' }]).length, 0);
  assert.equal(getCompatiblePlatforms([{ ...base, capabilities: { operations: [operation()], tools: {} } }]).length, 0);
  assert.equal(getCompatiblePlatforms([{ ...base, capabilities: { operations: [{ ...operation(), endpoint_url: 'https://api.example.com/{id}/chat/completions' }], tools } }]).length, 0);
});

test('Python and Node snippets include bounded one-shot calls and safe failing exits', () => {
  const python = generateSnippet(operation(), 'safe-model', 'python');
  assert.match(python, /timeout=30\.0/);
  assert.match(python, /max_retries=0/);
  assert.match(python, /APIStatusError/);
  assert.match(python, /APIConnectionError, APITimeoutError/);
  assert.doesNotMatch(python, /response\.text|error\.body|api_key="/);
  assert.match(python, /SystemExit\(1\)/);

  const node = generateSnippet(operation(), 'safe-model', 'node');
  assert.match(node, /timeout: 30000/);
  assert.match(node, /maxRetries: 0/);
  assert.doesNotMatch(node, /AbortController/);
  assert.match(node, /error\?\.name, error\?\.status, error\?\.request_id/);
  assert.doesNotMatch(node, /error\?\.message|error\.body/);
  assert.match(node, /process\.exitCode = 1/);
});

test('cURL has explicit timeouts and fail handling but never retries a POST', () => {
  const curl = generateSnippet(operation(), 'safe-model', 'curl');
  assert.match(curl, /--fail --silent/);
  assert.doesNotMatch(curl, /--fail-with-body/);
  assert.match(curl, /--connect-timeout 10 --max-time 30/);
  assert.match(curl, /"\$\{EXAMPLE_API_KEY:\?Set EXAMPLE_API_KEY/);
  assert.match(curl, /"max_tokens":64/);
  assert.doesNotMatch(curl, /--retry/);
});

test('documented REST search generates only a bounded authenticated cURL request', () => {
  const curl = generateSnippet(restOperation(), undefined, 'curl');
  assert.match(curl, /--request POST 'https:\/\/api\.tavily\.com\/search'/);
  assert.match(curl, /X-API-Key: \$\{TAVILY_API_KEY\}/);
  assert.match(curl, /"search_depth":"basic"/);
  assert.doesNotMatch(curl, /--retry|actual-secret/);
  assert.throws(() => generateSnippet(restOperation(), undefined, 'python'), /cURL only/);
  assert.equal(getOperationToolState({ curl: 'documented' }, 'curl', 'rest').enabled, true);
  assert.equal(getOperationToolState({}, 'freellmapi', 'rest').enabled, false);
});
