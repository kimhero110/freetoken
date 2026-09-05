const EXECUTABLE_LEVELS = new Set(['documented', 'live']);
const LIVE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
const MODEL_RE = /^[A-Za-z0-9@._:/+-]{1,160}$/;
const ENV_VAR_RE = /^[A-Z][A-Z0-9_]*$/;
const CHAT_SUFFIX = '/chat/completions';

export const VERIFICATION_LABELS = Object.freeze({
  zh: Object.freeze({
    claimed: '平台声称支持，文档未核查',
    documented: '已核查官方文档',
    live: '真实调用已通过',
    failed: '验证失败，不可用',
    unknown: '状态未知，不可用',
    unsupported: '明确不支持',
  }),
  en: Object.freeze({
    claimed: 'Provider-claimed; documentation not checked',
    documented: 'Official documentation checked',
    live: 'Live API call passed',
    failed: 'Verification failed; unavailable',
    unknown: 'Status unknown; unavailable',
    unsupported: 'Explicitly unsupported',
  }),
});

function assertSafeUrl(value) {
  if (typeof value !== 'string') throw new TypeError('Operation endpoint must be a URL');
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new TypeError('Operation endpoint must be a valid URL');
  }
  if (
    parsed.protocol !== 'https:' || !parsed.hostname || parsed.username || parsed.password ||
    parsed.search || parsed.hash || /[\s{}'"`$\\;&|<>\r\n]/.test(value)
  ) {
    throw new TypeError('Operation endpoint is unsafe');
  }
  return value;
}

function normalizeRestSearchOperation(operation) {
  if (!operation || operation.id !== 'search' || operation.protocol !== 'rest' || operation.method !== 'POST') {
    throw new TypeError('Only documented REST POST search operations are supported');
  }
  const endpointUrl = assertSafeUrl(operation.endpoint_url);
  const auth = operation.auth;
  if (!auth || auth.type !== 'api_key_header' || auth.query_param !== null ||
      typeof auth.header !== 'string' || !/^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(auth.header) ||
      !ENV_VAR_RE.test(auth.env_var || '')) {
    throw new TypeError('REST search requires safe API-key header authentication');
  }
  const body = operation.request_body;
  if (!body || Object.getPrototypeOf(body) !== Object.prototype || JSON.stringify(body).length > 8192) {
    throw new TypeError('REST search requires a bounded JSON request body');
  }
  const verification = operation.verification;
  if (!verification || !EXECUTABLE_LEVELS.has(verification.status)) {
    throw new TypeError('Operation verification does not permit generated requests');
  }
  if (verification.status === 'live') {
    const checkedAt = Date.parse(`${verification.checked_at || ''}T00:00:00Z`);
    if (!Number.isFinite(checkedAt) || Date.now() - checkedAt > LIVE_MAX_AGE_MS) {
      throw new TypeError('Live operation verification is stale');
    }
  }
  return Object.freeze({
    id: operation.id, protocol: operation.protocol, endpoint_url: endpointUrl, method: operation.method,
    request_body: structuredClone(body), models: Object.freeze(['default request']),
    auth: Object.freeze({ ...auth }), verification: Object.freeze({ ...verification }),
  });
}

function assertSafeModel(model) {
  if (typeof model !== 'string' || !MODEL_RE.test(model)) {
    throw new TypeError('Model is unsupported or unsafe');
  }
  return model;
}

export function normalizeChatOperation(operation) {
  if (!operation || operation.id !== 'chat_completions' || operation.protocol !== 'openai') {
    throw new TypeError('Only OpenAI Chat Completions operations are supported');
  }
  const endpointUrl = assertSafeUrl(operation.endpoint_url);
  if (!endpointUrl.endsWith(CHAT_SUFFIX)) {
    throw new TypeError('OpenAI Chat Completions endpoint must end with /chat/completions');
  }
  if (!Array.isArray(operation.models) || operation.models.length === 0) {
    throw new TypeError('Chat Completions operation requires at least one model');
  }
  const models = operation.models.map(assertSafeModel);
  const auth = operation.auth;
  if (
    !auth || auth.type !== 'bearer' || auth.header !== 'Authorization' ||
    auth.query_param !== null || !ENV_VAR_RE.test(auth.env_var || '')
  ) {
    throw new TypeError('Only bearer authentication with a safe environment variable is supported');
  }
  const verification = operation.verification;
  if (!verification || !EXECUTABLE_LEVELS.has(verification.status)) {
    throw new TypeError('Operation verification does not permit generated requests');
  }
  if (verification.status === 'live') {
    const checkedAt = Date.parse(`${verification.checked_at || ''}T00:00:00Z`);
    if (!Number.isFinite(checkedAt) || Date.now() - checkedAt > LIVE_MAX_AGE_MS) {
      throw new TypeError('Live operation verification is stale');
    }
  }
  return Object.freeze({
    id: operation.id,
    protocol: operation.protocol,
    endpoint_url: endpointUrl,
    base_url: endpointUrl.slice(0, -CHAT_SUFFIX.length),
    models: Object.freeze([...models]),
    auth: Object.freeze({
      type: auth.type,
      header: auth.header,
      query_param: auth.query_param,
      env_var: auth.env_var,
    }),
    verification: Object.freeze({
      status: verification.status,
      checked_at: verification.checked_at ?? null,
      evidence_url: verification.evidence_url ?? null,
    }),
  });
}

export function selectChatOperation(platform) {
  if (!platform || !['active', 'degraded'].includes(platform.status)) return null;
  for (const operation of platform.capabilities?.operations || []) {
    try {
      return normalizeChatOperation(operation);
    } catch {
      try {
        return normalizeRestSearchOperation(operation);
      } catch {
        // A platform may expose unrelated or non-executable operations first.
      }
    }
  }
  return null;
}

export function getToolState(tools, tool, lang = 'en') {
  const locale = lang === 'zh' ? 'zh' : 'en';
  if (tool === 'freellmapi') {
    return {
      enabled: true,
      status: 'unknown',
      reason: locale === 'zh'
        ? '未核验的本地聚合配置；并非平台官方验证的集成'
        : 'Unverified local aggregator configuration; not a provider-verified integration',
    };
  }
  const status = tools?.[tool] || 'unknown';
  return {
    enabled: EXECUTABLE_LEVELS.has(status),
    status,
    reason: VERIFICATION_LABELS[locale][status] || VERIFICATION_LABELS[locale].unknown,
  };
}

export function getCompatiblePlatforms(platforms) {
  if (!Array.isArray(platforms)) return [];
  return platforms.flatMap((platform) => {
    const operation = selectChatOperation(platform);
    if (!operation) return [];
    const tools = platform.capabilities?.tools || {};
    const applicableTools = operation.protocol === 'rest' ? ['curl'] : ['curl', 'openai_python', 'openai_node'];
    if (!applicableTools.some((tool) => getToolState(tools, tool).enabled)) return [];
    return [{
      slug: platform.slug,
      name: platform.name,
      name_en: platform.name_en,
      status: platform.status,
      quota: platform.free_quota?.amount ?? null,
      operation,
      tools,
    }];
  });
}

function requireModel(operation, model) {
  const safeModel = assertSafeModel(model);
  if (!operation.models.includes(safeModel)) throw new TypeError('Model is not offered by this operation');
  return safeModel;
}

function shellQuote(value) {
  if (/[\r\n\0]/.test(value)) throw new TypeError('Unsafe shell value');
  return `'${value.replaceAll("'", `'"'"'`)}'`;
}

function curlSnippet(operation, model) {
  const body = JSON.stringify({
    model,
    messages: [{ role: 'user', content: 'Reply with one short sentence.' }],
    max_tokens: 64,
  });
  return `: "\${${operation.auth.env_var}:?Set ${operation.auth.env_var} in your environment}"
curl --fail --silent --show-error \\
  --connect-timeout 10 --max-time 30 \\
  --request POST ${shellQuote(operation.endpoint_url)} \\
  --header 'Content-Type: application/json' \\
  --header "Authorization: Bearer \${${operation.auth.env_var}}" \\
  --data ${shellQuote(body)}`;
}

export function getOperationToolState(tools, tool, protocol, lang = 'en') {
  if (protocol === 'rest' && tool !== 'curl') {
    const locale = lang === 'zh' ? 'zh' : 'en';
    return {
      enabled: false,
      status: 'unsupported',
      reason: locale === 'zh' ? '此 REST 操作目前仅生成 cURL' : 'This REST operation currently generates cURL only',
    };
  }
  return getToolState(tools, tool, lang);
}

function restCurlSnippet(operation) {
  const body = JSON.stringify(operation.request_body);
  return `: "\${${operation.auth.env_var}:?Set ${operation.auth.env_var} in your environment}"
curl --fail --silent --show-error \\
  --connect-timeout 10 --max-time 30 \\
  --request ${operation.method} ${shellQuote(operation.endpoint_url)} \\
  --header 'Content-Type: application/json' \\
  --header "${operation.auth.header}: \${${operation.auth.env_var}}" \\
  --data ${shellQuote(body)}`;
}

function pythonSnippet(operation, model) {
  return `import os
import sys
from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError

ENV_VAR = ${JSON.stringify(operation.auth.env_var)}
if not os.environ.get(ENV_VAR):
    raise RuntimeError(f"Set {ENV_VAR} in your environment")

client = OpenAI(
    api_key=os.environ[ENV_VAR],
    base_url=${JSON.stringify(operation.base_url)},
    timeout=30.0,
    max_retries=0,
)

try:
    response = client.chat.completions.create(
        model=${JSON.stringify(model)},
        messages=[{"role": "user", "content": "Reply with one short sentence."}],
        max_tokens=64,
    )
    print(response.choices[0].message.content)
except APIStatusError as error:
    print(type(error).__name__, error.status_code, error.request_id, file=sys.stderr)
    raise SystemExit(1)
except (APIConnectionError, APITimeoutError) as error:
    print(type(error).__name__, getattr(error, "status_code", None), getattr(error, "request_id", None), file=sys.stderr)
    raise SystemExit(1)`;
}

function nodeSnippet(operation, model) {
  return `import OpenAI from "openai";

const envVar = ${JSON.stringify(operation.auth.env_var)};
if (!process.env[envVar]) throw new Error(\`Set \${envVar} in your environment\`);

const client = new OpenAI({
  apiKey: process.env[envVar],
  baseURL: ${JSON.stringify(operation.base_url)},
  timeout: 30000,
  maxRetries: 0,
});

try {
  const response = await client.chat.completions.create({
    model: ${JSON.stringify(model)},
    messages: [{ role: "user", content: "Reply with one short sentence." }],
    max_tokens: 64,
  });
  console.log(response.choices[0].message.content);
} catch (error) {
  console.error(error?.name, error?.status, error?.request_id);
  process.exitCode = 1;
}`;
}

function localAggregatorSnippet(operation, model) {
  return JSON.stringify({
    note: 'Unverified local configuration; not provider-verified',
    protocol: 'openai',
    endpoint_url: operation.endpoint_url,
    api_key_env: operation.auth.env_var,
    models: [model],
  }, null, 2);
}

export function generateSnippet(rawOperation, model, format) {
  if (rawOperation?.protocol === 'rest') {
    const operation = normalizeRestSearchOperation(rawOperation);
    if (format === 'curl') return restCurlSnippet(operation);
    throw new TypeError('REST search currently supports cURL only');
  }
  const operation = normalizeChatOperation(rawOperation);
  const safeModel = requireModel(operation, model);
  if (format === 'curl') return curlSnippet(operation, safeModel);
  if (format === 'python') return pythonSnippet(operation, safeModel);
  if (format === 'node') return nodeSnippet(operation, safeModel);
  if (format === 'freellmapi') return localAggregatorSnippet(operation, safeModel);
  throw new TypeError('Unsupported generator format');
}
