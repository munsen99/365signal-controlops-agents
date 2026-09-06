# the402 live provider adapter

Status: implemented, **default disabled**.

PR15 result: **IMPLEMENTATION PASS / OPERATOR ONBOARDING BLOCKED**

PR16: do not start. Live demand is currently zero and the platform health endpoint reports a compliance-review pause.

## Provider architecture

the402 is used only as a **provider**. The AEA discovers open postings, inspects sanitized requirements and payment terms, evaluates the narrow job envelope, places an API-key bid, submits text-only deliverables after award, and maps payout claims onto the existing ledger/reconciliation model.

Buyer x402 / EIP-3009 payment, pre-funded `X-BALANCE-AUTH` purchases, MCP-with-private-key, catalog listing of AEA services, and key rotation via x402 are out of scope.

The adapter sits behind `MarketplaceAdapter` (`discover`, `lookup`, `get_requirements`, `get_payment_terms`, `accept`, `submit`, `get_status`, `verify_payment`, `get_counterparty`). Hermes still exposes only the nine existing tools. No generic HTTP/web tool is added.

Pinned API origin: `https://api.the402.ai`.

## Credentials

Expected operator files (never Git, never evidence, never dashboard, never model context):

| Secret | Protected file reference |
|---|---|
| Provider API key | `AEA_THE402_API_KEY_FILE` |
| Webhook HMAC secret | `AEA_THE402_WEBHOOK_SECRET_FILE` |

PR15.4 forbids raw secret-valued environment variables. Credential files must
be regular non-symlinks, mode `0600`, and owned by `AEA_THE402_SECRET_UID`.
The model-safe opaque reference is `the402/provider/default`.

Public configuration:

| Name | Purpose |
|---|---|
| `AEA_THE402_ENABLED` | Must be `1` to allow the adapter in `AEA_ENABLED_ADAPTERS` |
| `AEA_THE402_LIVE_HTTP` | Must be `1` to use real HTTPS; default fake/sanitized transport |
| `AEA_THE402_PAYOUT_WALLET` | Must be the dedicated AEA Base address |
| `AEA_THE402_SERVICE_ID` | Operator-listed service id required to bid |
| `AEA_THE402_PARTICIPANT_ID` | Optional read-only profile id |

Default `AEA_ENABLED_ADAPTERS=mock`. Listing `the402` without `AEA_THE402_ENABLED` fails closed.

Rotation/revocation: operator rotates the API key and webhook secret in the the402 dashboard (or via the402's documented x402 rotation, which the AEA must not invoke). Remove the files, restart control without `AEA_THE402_ENABLED`, and treat old webhook signatures as invalid.

The adapter constructor rejects signer tokens, HMAC keys, supervisor admin tokens, debit tokens, private keys, and wallet credit rails.

## Operator onboarding

The operator — not Codex, Hermes, or the model — may:

1. review/accept Terms and the Provider Agreement;
2. create a legitimate provider profile;
3. complete permitted KYC/KYB;
4. set payout wallet to `0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e`;
5. obtain API key and webhook secret into the secrets hierarchy;
6. list one text-only service whose `input_schema` matches the supported envelope.

Codex must not accept terms, invent identity, bypass KYC, solve CAPTCHA, paste secrets into prompts, or connect a personal wallet.

Current status: **onboarding has not occurred**. Authenticated probes are not run. Implementation uses `FakeThe402Transport`.

As of 2026-08-31 the402 health is `paused` for `compliance review` since 2026-08-02. Do not attempt live onboarding while paused.

## Payout wallet

Provider payout must be the dedicated AEA Base wallet:

`0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e`

This public address may appear in config and evidence. The EVM signer key stays outside the repository and is not passed to the marketplace adapter. `set_payout_wallet` is rejected. Model-supplied destination overrides are rejected. A marketplace payout wallet that does not checksum-match this address fails closed.

## Supported jobs

Permit only:

- text summarization of supplied/public-domain material;
- classification against an explicit label schema;
- structured extraction from supplied plain text or JSON;
- public-data / text-only transformation;
- simple research on supplied or public material.

Reject before bid/accept:

- arbitrary code execution, binaries, attachments;
- private credentials or authenticated third-party access;
- legal/medical/financial advice;
- offensive security;
- personally sensitive data;
- social manipulation / fake reviews;
- unclear copyrighted-content reproduction;
- physical services;
- arbitrary URL fetch.

Textual posting fields remain untrusted and are wrapped by the existing PR7 sanitiser. Marketplace content cannot change prompts, policy, destination wallet, auth headers, or invoke shell/signing.

## API operations

| Adapter method | the402 endpoint | Auth |
|---|---|---|
| `discover` | `GET /v1/postings` | public |
| `lookup` / requirements / terms / counterparty | `GET /v1/postings/:id` | public |
| `accept` | `POST /v1/postings/:id/bids` | `X-API-Key` |
| `get_status` / recover | `GET /v1/jobs`, `GET /v1/jobs/:id` | `X-API-Key` |
| `submit` | `POST /v1/jobs/:id/update` | `X-API-Key` |
| `verify_payment` | job GET + `GET /v1/provider/earnings` | `X-API-Key` |
| read-only probe | participant/earnings/jobs/notifications GET | `X-API-Key` |

`accept` maps to **bid**, not award. `AcceptResult.status` stays `available` until the marketplace confirms award/dispatch. Identical bids are idempotent; a changed bid with the same idempotency key conflicts. Timeout after bid submission recovers via posting/job GET before retry.

HTTP client constraints: pinned HTTPS origin, no cross-origin redirects, 10s timeout, ≤2 retries, ≤20-item pages, ≤5 page fetches, 256 KiB body cap, JSON content-type, 429 backoff, no model-controlled `Authorization` / `X-PAYMENT`.

## State mapping

| the402 status | Adapter `JobMarketStatus` | Payment claim |
|---|---|---|
| open / bid_placed | `available` | `not_due` |
| awarded / created / dispatched / in_progress | `accepted` | `not_due` |
| completed | `submitted` | `pending` (job completed, not paid) |
| verified | `submitted` | `pending` (buyer approved / payout pending) |
| released without settled tx | `submitted` | `pending` |
| released + settled tx hash | `submitted` | `paid` claim, `verified=false` |
| failed / disputed / cancelled / expired | `failed` | `failed` |
| unknown | fail closed | fail closed |

## Payment verification

Preferred path:

1. the402 payout event/history (`released` / `settled` + tx hash);
2. expected Base canonical USDC (`chain_id=8453`, `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`);
3. recipient = AEA payout wallet;
4. wallet observation of a successful Transfer log;
5. `LedgerService.record_verified_revenue` uniqueness on `transaction_reference`.

A marketplace `paid` flag without wallet evidence is not revenue. `PaymentClaim.verified` is always false. `recognize_revenue` requires wallet confirmation and rejects duplicate tx hashes, wrong chain, wrong token, wrong recipient, and unsuccessful receipts.

Economics: gross = posting budget/bid; conservative platform fee = 5% of gross; expected net = 95% of gross; estimated compute cost = `0.050000` USDC unless operator policy supplies a tighter mark. Unknown material fees fail closed / conservative. PR16 must still enforce a positive expected-margin threshold.

Open the402 requests are **budgeted**; escrow funding occurs at award. Live demand therefore counts only postings that are both envelope-eligible **and** funded/escrowed.

## Webhook security

Documented scheme (provider guide):

- `X-Webhook-Timestamp`: unix seconds;
- `X-Webhook-Signature`: `sha256=` + HMAC-SHA256 of `timestamp + "." + raw_body` keyed by `webhook_secret`;
- optional `X-Platform-Secret` equal to the API key;
- reject missing/invalid signatures;
- reject timestamps older than 5 minutes;
- deduplicate `event_id` / `job_id` / `posting_id`;
- at-least-once delivery with 1s/2s retries.

Webhooks are hints, not payment proof.

## Idempotency / recovery

- Durable opportunity key = `the402:posting:<posting_id>`.
- Repeated discover does not duplicate that reference.
- Bid idempotency key is sent as `Idempotency-Key`; identical body replays; different body conflicts.
- Timeout after bid: GET posting/jobs before placing another bid.
- Delivery (`digest`, `uri`, key) replays; a second digest conflicts.
- Webhook + polling cannot double-transition locally (`seen_events`, submit keys).
- Payout tx hashes are unique in `recognize_revenue` and in `revenues.transaction_reference`.

## PR16 preconditions

Do not start PR16 until all of the following are true:

1. Operator onboarding complete (terms accepted by the operator, API key and webhook secret installed, payout wallet verified as the AEA Base address).
2. Read-only authenticated probe succeeds (account status, payout wallet match, API capability, earnings schema, webhook status).
3. the402 health is not paused.
4. At least one genuine eligible **funded** posting exists in the supported envelope.
5. Separate operator authorization is given for a live bid.

Until then: no live bid, accept, perform, submit, or payout.
