# Feishu live integration — 2026-09-06

## Observed, rather than assumed

- PR 15 is merged. The owner identity supplied in the private chat is bound and bootstrap is disabled.
- Feishu tenant authentication works. Real owner identity replies and an outbound status card were delivered.
- IM card content must contain the inner card object. Passing the webhook envelope caused 230099 / 200621; reply, create and patch now share the corrected serializer.
- The owner’s real self-test command was found in private-chat history but absent from the daemon journal. Its original message was recovered once, with owner, text, age and message identity checked. No confirmation was synthesized.
- A subsequent real confirmation reached the WebSocket handler and dispatched ticket se-2a4a49916a, run 33981580789, on main commit 509fc3880fe4787362d16372530778a903bdd7ac.
- That run reached production approval. The approval POST returned 403: Resource not accessible by personal access token. GET current_user_can_approve=true did not prove token write permission.
- GitHub requires repository Deployments write for review-pending-deployments, in addition to Actions write for dispatch/cancel. The daemon previously misclassified every 403 as rate limiting and retried without a useful failure reply.

## Changes under PR 16

- Correct IM serialization, stable message-ID deduplication, read-receipt event handler and credential-safe connection logging.
- Permanent permission failures finish immediately with an actionable card and attempt to cancel only the verified ticket run. Write requests are not blindly retried.
- Repeated gate polls do not reset the watchdog deadline; timeout retains the phase the watchdog can cancel.
- Startup reports interrupted in-flight tracking without replaying approvals or submissions; interrupted candidate approvals remain blocked against duplication until an administrator reconciles them.
- PR checks have their own concurrency group so a waiting production publication cannot block bot-fix verification.
- Offline regression covers owner confirmation through dispatch, gate and completion, real SDK card request bodies, permission rejection, timeout timestamp and restart semantics. Offline mocks do not constitute live acceptance.

## Remaining live acceptance

The existing repository-scoped token needs Deployments: Read and write. Do not replace it with a broader local credential. Do not remove required reviewers. Permission expansion needs owner approval. After that, verify the exact confirmed self-test run or a newly owner-confirmed ticket passes the gate and updates its Feishu card.

The unrelated main website publication run 33980406917 is outside this bot test. A self-test does not change content or deploy the website.

No credentials, owner IDs, chat IDs or confirmation codes are recorded here. Raw diagnostics remain in ignored private storage.

Reference: https://docs.github.com/en/rest/actions/workflow-runs#review-pending-deployments-for-a-workflow-run
