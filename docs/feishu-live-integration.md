# Feishu live integration — 2026-09-06

## Confirmed observations

- Production container is still running commit 558b386; all required configuration keys are present.
- The configured owner ID is a placeholder. A real send returned Feishu code 99992351; no card was delivered. The bot application is reachable and tenant authentication succeeds.
- Existing GitHub PAT can read the authenticated actor, repository, main commit, workflow runs and production environment. No credential replacement is currently required.
- The absent data/candidates directory returns 404. The fix verifies the parent is readable before returning an empty queue.
- New image freetoken-intake:51ae001c is built on FreeTokenLab. Previous image retained as freetoken-intake:rollback-558b386. No production container switch has occurred.
- 142 core Python tests and 16 real-SDK integration tests passed; GitHub PR build passed.

## Pending live acceptance

1. Merge PR 15 and recreate the bot container using the tested image (production change awaiting explicit approval after automatic review rejected it).
2. With bootstrap enabled, the intended owner sends the bootstrap identity command in a private chat. Bind the returned identity, disable bootstrap, and recreate the container so env_file changes take effect.
3. Verify status, help and empty candidate replies from real inbound messages.
4. Send selftest, then the six-digit confirmation from the bot card. Check the exact ticket-bound workflow reaches its production gate, is approved by the bot, completes successfully and updates its Feishu card.
5. A content publication remains separate: the self-test workflow does not modify content, merge a candidate PR or deploy a site.

No real API key values, owner IDs or confirmation codes are recorded here. Temporary WebSocket connection parameters were removed from the public archive logs; new SDK connection logging uses WARNING. Raw logs remain only in the ignored local private archive.
