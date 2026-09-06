# PR15.5 the402 readiness watch

Date: 2026-09-06
Status: read-only, unauthenticated, non-financial

Run:

```bash
scripts/the402-readiness
scripts/the402-readiness --json
```

The command performs exactly two bounded public requests:

```text
GET /health
GET /v1/postings?limit=20
```

It has no generic request method, credential input, mutation method, wallet access,
or signer access. `--onboarding-complete` is an operator assertion used only to
select post-onboarding demand states; it does not read credentials or authenticate.

States:

- `PLATFORM_PAUSED`: health explicitly says paused; onboarding is blocked.
- `ONBOARDING_READY`: unpaused, but operator onboarding is not asserted complete.
- `NO_ELIGIBLE_DEMAND`: unpaused and onboarded, but no conservative candidate.
- `PR16_CANDIDATE_FOUND`: at least one conservative candidate; human review only.
- `UNKNOWN`: transport/schema/identity failure; fail closed.

An eligible posting must explicitly establish every material fact: actionable
status, funded/escrowed state, Base chain ID 8453, canonical Base USDC, external
provider payout, supported text/JSON work, no provider capital or escrow funding,
no custody, no wallet/EIP-712/EIP-3009 signing, no approval/permit, no unsupported
public hosting, a known provider fee, and net reward of at least 2 USDC. Missing
fields reject conservatively.

Exit codes:

- `0`: probe succeeded, including paused or no-demand states;
- `1`: network/HTTP/system failure;
- `2`: malformed or incomplete untrusted response (`UNKNOWN`).

The command never registers, bids, accepts, submits, authenticates, signs, or moves
capital. A candidate means `REVIEW_REQUIRED`, never authorization for PR16.
