var e=new Set([`documented`,`live`]),t=2592e6,n=/^[A-Za-z0-9@._:/+-]{1,160}$/,r=/^[A-Z][A-Z0-9_]*$/,i=`/chat/completions`,a=Object.freeze({zh:Object.freeze({claimed:`平台声称支持，文档未核查`,documented:`已核查官方文档`,live:`真实调用已通过`,failed:`验证失败，不可用`,unknown:`状态未知，不可用`,unsupported:`明确不支持`}),en:Object.freeze({claimed:`Provider-claimed; documentation not checked`,documented:`Official documentation checked`,live:`Live API call passed`,failed:`Verification failed; unavailable`,unknown:`Status unknown; unavailable`,unsupported:`Explicitly unsupported`})});function o(e){if(typeof e!=`string`)throw TypeError(`Operation endpoint must be a URL`);let t;try{t=new URL(e)}catch{throw TypeError(`Operation endpoint must be a valid URL`)}if(t.protocol!==`https:`||!t.hostname||t.username||t.password||t.search||t.hash||/[\s{}'"`$\\;&|<>\r\n]/.test(e))throw TypeError(`Operation endpoint is unsafe`);return e}function s(n){if(!n||n.id!==`search`||n.protocol!==`rest`||n.method!==`POST`)throw TypeError(`Only documented REST POST search operations are supported`);let i=o(n.endpoint_url),a=n.auth;if(!a||a.type!==`api_key_header`||a.query_param!==null||typeof a.header!=`string`||!/^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(a.header)||!r.test(a.env_var||``))throw TypeError(`REST search requires safe API-key header authentication`);let s=n.request_body;if(!s||Object.getPrototypeOf(s)!==Object.prototype||JSON.stringify(s).length>8192)throw TypeError(`REST search requires a bounded JSON request body`);let c=n.verification;if(!c||!e.has(c.status))throw TypeError(`Operation verification does not permit generated requests`);if(c.status===`live`){let e=Date.parse(`${c.checked_at||``}T00:00:00Z`);if(!Number.isFinite(e)||Date.now()-e>t)throw TypeError(`Live operation verification is stale`)}return Object.freeze({id:n.id,protocol:n.protocol,endpoint_url:i,method:n.method,request_body:structuredClone(s),models:Object.freeze([`default request`]),auth:Object.freeze({...a}),verification:Object.freeze({...c})})}function c(e){if(typeof e!=`string`||!n.test(e))throw TypeError(`Model is unsupported or unsafe`);return e}function l(n){if(!n||n.id!==`chat_completions`||n.protocol!==`openai`)throw TypeError(`Only OpenAI Chat Completions operations are supported`);let a=o(n.endpoint_url);if(!a.endsWith(i))throw TypeError(`OpenAI Chat Completions endpoint must end with /chat/completions`);if(!Array.isArray(n.models)||n.models.length===0)throw TypeError(`Chat Completions operation requires at least one model`);let s=n.models.map(c),l=n.auth;if(!l||l.type!==`bearer`||l.header!==`Authorization`||l.query_param!==null||!r.test(l.env_var||``))throw TypeError(`Only bearer authentication with a safe environment variable is supported`);let u=n.verification;if(!u||!e.has(u.status))throw TypeError(`Operation verification does not permit generated requests`);if(u.status===`live`){let e=Date.parse(`${u.checked_at||``}T00:00:00Z`);if(!Number.isFinite(e)||Date.now()-e>t)throw TypeError(`Live operation verification is stale`)}return Object.freeze({id:n.id,protocol:n.protocol,endpoint_url:a,base_url:a.slice(0,-17),models:Object.freeze([...s]),auth:Object.freeze({type:l.type,header:l.header,query_param:l.query_param,env_var:l.env_var}),verification:Object.freeze({status:u.status,checked_at:u.checked_at??null,evidence_url:u.evidence_url??null})})}function u(t,n,r=`en`){let i=r===`zh`?`zh`:`en`;if(n===`freellmapi`)return{enabled:!0,status:`unknown`,reason:i===`zh`?`未核验的本地聚合配置；并非平台官方验证的集成`:`Unverified local aggregator configuration; not a provider-verified integration`};let o=t?.[n]||`unknown`;return{enabled:e.has(o),status:o,reason:a[i][o]||a[i].unknown}}function d(e,t){let n=c(t);if(!e.models.includes(n))throw TypeError(`Model is not offered by this operation`);return n}function f(e){if(/[\r\n\0]/.test(e))throw TypeError(`Unsafe shell value`);return`'${e.replaceAll(`'`,`'"'"'`)}'`}function p(e,t){let n=JSON.stringify({model:t,messages:[{role:`user`,content:`Reply with one short sentence.`}],max_tokens:64});return`: "\${${e.auth.env_var}:?Set ${e.auth.env_var} in your environment}"
curl --fail --silent --show-error \\
  --connect-timeout 10 --max-time 30 \\
  --request POST ${f(e.endpoint_url)} \\
  --header 'Content-Type: application/json' \\
  --header "Authorization: Bearer \${${e.auth.env_var}}" \\
  --data ${f(n)}`}function m(e,t,n,r=`en`){return n===`rest`&&t!==`curl`?{enabled:!1,status:`unsupported`,reason:(r===`zh`?`zh`:`en`)==`zh`?`此 REST 操作目前仅生成 cURL`:`This REST operation currently generates cURL only`}:u(e,t,r)}function h(e){let t=JSON.stringify(e.request_body);return`: "\${${e.auth.env_var}:?Set ${e.auth.env_var} in your environment}"
curl --fail --silent --show-error \\
  --connect-timeout 10 --max-time 30 \\
  --request ${e.method} ${f(e.endpoint_url)} \\
  --header 'Content-Type: application/json' \\
  --header "${e.auth.header}: \${${e.auth.env_var}}" \\
  --data ${f(t)}`}function g(e,t){return`import os
import sys
from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError

ENV_VAR = ${JSON.stringify(e.auth.env_var)}
if not os.environ.get(ENV_VAR):
    raise RuntimeError(f"Set {ENV_VAR} in your environment")

client = OpenAI(
    api_key=os.environ[ENV_VAR],
    base_url=${JSON.stringify(e.base_url)},
    timeout=30.0,
    max_retries=0,
)

try:
    response = client.chat.completions.create(
        model=${JSON.stringify(t)},
        messages=[{"role": "user", "content": "Reply with one short sentence."}],
        max_tokens=64,
    )
    print(response.choices[0].message.content)
except APIStatusError as error:
    print(type(error).__name__, error.status_code, error.request_id, file=sys.stderr)
    raise SystemExit(1)
except (APIConnectionError, APITimeoutError) as error:
    print(type(error).__name__, getattr(error, "status_code", None), getattr(error, "request_id", None), file=sys.stderr)
    raise SystemExit(1)`}function _(e,t){return`import OpenAI from "openai";

const envVar = ${JSON.stringify(e.auth.env_var)};
if (!process.env[envVar]) throw new Error(\`Set \${envVar} in your environment\`);

const client = new OpenAI({
  apiKey: process.env[envVar],
  baseURL: ${JSON.stringify(e.base_url)},
  timeout: 30000,
  maxRetries: 0,
});

try {
  const response = await client.chat.completions.create({
    model: ${JSON.stringify(t)},
    messages: [{ role: "user", content: "Reply with one short sentence." }],
    max_tokens: 64,
  });
  console.log(response.choices[0].message.content);
} catch (error) {
  console.error(error?.name, error?.status, error?.request_id);
  process.exitCode = 1;
}`}function v(e,t){return JSON.stringify({note:`Unverified local configuration; not provider-verified`,protocol:`openai`,endpoint_url:e.endpoint_url,api_key_env:e.auth.env_var,models:[t]},null,2)}function y(e,t,n){if(e?.protocol===`rest`){let t=s(e);if(n===`curl`)return h(t);throw TypeError(`REST search currently supports cURL only`)}let r=l(e),i=d(r,t);if(n===`curl`)return p(r,i);if(n===`python`)return g(r,i);if(n===`node`)return _(r,i);if(n===`freellmapi`)return v(r,i);throw TypeError(`Unsupported generator format`)}var b=document.getElementById(`code-generator`);if(b instanceof HTMLElement&&b.dataset.platforms){let e=b.dataset.lang===`zh`?`zh`:`en`,t=JSON.parse(b.dataset.platforms),n=b.querySelector(`#select-platform`),r=b.querySelector(`#select-model`),i=b.querySelector(`#code-output-text`),o=b.querySelector(`#generated-code`),s=b.querySelector(`#operation-badge`),c=b.querySelector(`#tool-support-message`),l=b.querySelector(`#app-support-message`),u=b.querySelector(`#output-file-name`),d=b.querySelector(`#btn-copy-code`),f=[...b.querySelectorAll(`.code-gen-tab`)],p=e=>e.getAttribute(`aria-disabled`)!==`true`,h=f.find(p)?.dataset.tab||``,g=()=>t.find(e=>e.slug===n?.value)||t[0],_=()=>f.filter(p);function v(e){!e||!p(e)||(f.forEach(t=>{let n=t===e;t.classList.toggle(`active`,n),t.setAttribute(`aria-selected`,String(n)),t.tabIndex=n?0:-1}),h=e.dataset.tab||``,o?.setAttribute(`aria-labelledby`,e.id),u&&(u.textContent=e.dataset.file||``),S())}function x(){let t=g();if(!t)return;r&&r.replaceChildren(...t.operation.models.map(e=>{let t=document.createElement(`option`);return t.value=e,t.textContent=e,t})),s&&(s.textContent=a[e][t.operation.verification.status],s.className=`verification-badge level-${t.operation.verification.status}`),f.forEach(n=>{let r=m(t.tools,n.dataset.tool,t.operation.protocol,e);n.setAttribute(`aria-disabled`,String(!r.enabled)),n.title=r.reason}),l&&(l.textContent=f.filter(n=>!m(t.tools,n.dataset.tool,t.operation.protocol,e).enabled).map(n=>`${n.dataset.label}: ${m(t.tools,n.dataset.tool,t.operation.protocol,e).reason}`).join(` · `));let n=f.find(e=>e.dataset.tab===h&&p(e));n||=_()[0],v(n)}function S(){let t=g(),n=f.find(e=>e.dataset.tab===h);if(!t||!n||!i)return;let a=m(t.tools,n.dataset.tool,t.operation.protocol,e);c&&(c.textContent=a.reason),i.textContent=y(t.operation,r?.value,h)}n?.addEventListener(`change`,x),r?.addEventListener(`change`,S),f.forEach(e=>{e.addEventListener(`click`,()=>v(e)),e.addEventListener(`keydown`,t=>{let n=_(),r=n.indexOf(e),i;t.key===`ArrowRight`&&(i=n[(r+1)%n.length]),t.key===`ArrowLeft`&&(i=n[(r-1+n.length)%n.length]),t.key===`Home`&&(i=n[0]),t.key===`End`&&(i=n.at(-1)),i&&(t.preventDefault(),v(i),i.focus())})}),d?.addEventListener(`click`,async()=>{let t=e===`zh`?`复制代码`:`Copy code`;try{if(!navigator.clipboard)throw Error(`Clipboard unavailable`);await navigator.clipboard.writeText(i?.textContent||``),d.textContent=e===`zh`?`已复制`:`Copied`}catch{d.textContent=e===`zh`?`复制失败，请手动选择`:`Copy failed; select manually`,d.setAttribute(`aria-live`,`polite`)}window.setTimeout(()=>{d.textContent=t},1600)}),x()}