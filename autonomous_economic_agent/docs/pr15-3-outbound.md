# PR15.3 outbound market experiment

```
PR15.3: BLOCKED
OUTBOUND SERVICE OFFER: READY
SAFE PUBLICATION VENUE: NONE
CAPITAL-BEARING ACTIONS: NONE
PR16: NOT STARTED
```

A canonical three-item research/analysis menu ($2 / $5 / $10 USDC) is derived from the PR15.2 `ServiceProfile`. Live publication was not performed.

## Venue decision

workpnp was preferred. Official `skill.md` still requires `POST /agents/register` (one-time API key) and a human email+X claim before posting. `POST /jobs` is buyer hiring and later x402 funding, not a worker catalog. Registering would place a secret in this process. That is outside the authorised side-effect.

the402 listing needs operator credentials and is paused. MoltJobs remains Turnkey/chain blocked. Hober and BotHire were not used to manufacture activity.

## What was implemented

`aea.marketplace.outbound` renders the offer, rejects bid/accept/submit/pay/escrow, classifies inbound interest (including `NO_RESPONSE`), and keeps negotiation text non-binding.

Evidence: `tests/e2e/evidence/m3/pr15-3-outbound-20260831/`.
