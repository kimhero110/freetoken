import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import OpenAI from 'openai';

const started = performance.now();
const result = { observed_status_code: null, protocol_valid: false, decision: 'failed', latency_ms: 0 };

try {
  const slug = process.argv[2] || '';
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Error('invalid configuration');
  const directory = path.dirname(fileURLToPath(import.meta.url));
  const config = JSON.parse(fs.readFileSync(path.join(directory, '..', 'capability_probe_config.json'), 'utf8'));
  const provider = config.providers?.[slug];
  const expected = config.tools?.openai_node;
  const apiKey = provider && process.env[provider.api_key_env];
  if (!provider || !expected || !apiKey) throw new Error('invalid configuration');
  const suffix = '/chat/completions';
  if (!provider.endpoint_url.endsWith(suffix)) throw new Error('invalid configuration');
  const client = new OpenAI({
    apiKey,
    baseURL: provider.endpoint_url.slice(0, -suffix.length),
    maxRetries: 0,
    timeout: 30_000,
    logLevel: 'off',
    fetchOptions: { redirect: 'manual' },
  });
  const response = await client.chat.completions.create({
    model: provider.model,
    messages: [{ role: 'user', content: 'Reply with OK.' }],
    max_tokens: 16,
    stream: false,
  });
  result.observed_status_code = 200;
  result.protocol_valid = response?.choices?.[0]?.message?.role === 'assistant' &&
    typeof response.choices[0].message.content === 'string' && response.choices[0].message.content.trim().length > 0;
  result.decision = result.protocol_valid ? 'live' : 'failed';
} catch (error) {
  if (Number.isInteger(error?.status) && error.status >= 100 && error.status <= 599) {
    result.observed_status_code = error.status;
  }
} finally {
  result.latency_ms = Math.min(120000, Math.max(0, Math.round(performance.now() - started)));
  process.stdout.write(JSON.stringify(result));
}
