# PR15.4 the402 operator onboarding boundary

Review date: 2026-09-06  
Governing contract: M0 v0.1.2  
State: **OPERATOR ACTION REQUIRED — PLATFORM PAUSED**

## Trust objects

These identities are deliberately separate:

| Object | Authority | Stored as |
|---|---|---|
| Operator identity | Accountable adult human accepting Terms and Provider Agreement | the402 account; never model context |
| Agent identity | Econo, operating under operator limits | existing AEA profile/constitution |
| Marketplace credential | Provider API key plus webhook HMAC secret | protected files referenced as `the402/provider/default` |
| Payout wallet | Dedicated externally controlled AEA Base wallet | public address only in config; key remains signer-only |

Public payout address: `0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e`.

the402 is only a payment destination configurator and inbound payer. It receives no private key, approval, permit, debit authority, or custody delegation.

## Provider capability assertion

```yaml
marketplace: the402
role: provider
settlement_chain: base
settlement_asset: USDC
payout_wallet: external
auth: scoped_api_key
credential_reference: the402/provider/default
buyer_flow: disabled
arbitrary_signing: false
typed_data_signing: false
transaction_signing: false
custody: false
capital_spend: false
```

The provider endpoints use `X-API-Key`. Posting discovery is public. Provider bidding may use `X-API-Key`; the paid x402 alternative is forbidden. Delivery/status/earnings operations use the provider key. Incoming webhooks use HMAC-SHA256 over timestamp plus raw body and are hints, never payment proof.

The adapter has no buyer purchase, checkout, funding, escrow-funding, deposit, approval, permit, EIP-3009, message-signing, typed-data-signing, transaction-signing, or arbitrary-call method.

## Protected credential installation

Do not paste either value into Codex, chat, shell history, evidence, tracked `.env`, or ordinary logs. The operator must save one-time values directly as:

```text
/home/proteu5/.config/controlops/economic/tokens/the402_api_key
/home/proteu5/.config/controlops/economic/tokens/the402_webhook_secret
```

Both must be regular, non-symlink files, owned by the configured marketplace-service UID, and mode `0600`. Runtime configuration contains only:

```text
AEA_THE402_API_KEY_FILE=/secrets/tokens/the402_api_key
AEA_THE402_WEBHOOK_SECRET_FILE=/secrets/tokens/the402_webhook_secret
AEA_THE402_SECRET_UID=<runtime marketplace uid>
```

Raw `AEA_THE402_API_KEY` and `AEA_THE402_WEBHOOK_SECRET` values are rejected. The loader returns generic errors for missing, unreadable, malformed, wrong-owner, symlinked, or over-permissive files. `repr`, model-visible results, evidence, and exception messages do not contain secret values.

Only the future provider marketplace runtime may mount these two files read-only. Hermes, the LLM, Policy, Signer, Wallet, Ledger, and Supervisor must not receive them. The EVM signer key is not mounted into the provider runtime.

Revocation: disable `AEA_THE402_ENABLED`, remove the provider runtime from `AEA_ENABLED_ADAPTERS`, revoke/rotate both credentials in the operator dashboard, replace protected files directly, and restart only the provider runtime. Never use the paid x402 key-rotation endpoint from the AEA.

## Legal and onboarding findings

Current Terms and Provider Agreement are version `2026-05-25`. They require an account holder aged at least 18, accurate identity information, control of the payout wallet, responsibility for taxes/reporting, lawful and accurately described services, and acceptance of Florida law/dispute terms. The Provider Agreement expressly anticipates autonomous AI-agent buyers and Base-USDC payout to the provider-controlled wallet. It charges 5%; the provider receives 95% of the listed amount.

Accepting these agreements, asserting eligibility, choosing an account login, completing email/KYC checks, and entering the payout wallet are human operator actions. Code must not perform or claim them.

## Current stop condition

On 2026-09-06 the public health endpoint reported:

```text
status=paused
paused=true
pause_reason=compliance review
network=base
```

The settlement/compliance jobs were stale. No registration or authenticated operation should be attempted while the platform is paused.

## Operator action required

After the official health endpoint reports unpaused:

1. Open `https://the402.ai/dashboard` directly.
2. Review the then-current Terms and Provider Agreement; proceed only if the operator accepts them and meets eligibility requirements.
3. Create a provider profile using accurate operator information; complete any email or identity verification legitimately requested.
4. Set the external payout wallet exactly to `0x7fc8ACC21e601c488e6EE4eE39AD67d3ecA12a7e`. Do not use or fund the embedded wallet.
5. Create one inactive text/JSON-only service matching the existing supported envelope; do not publish it or bid in PR15.4.
6. Receive the API key and webhook secret and write them directly to the protected paths above without showing their values to Codex.
7. Record only the public participant ID and service ID in operator configuration.
8. Resume PR15.4 for a read-only authenticated participant, payout-wallet, earnings-schema, jobs, and webhook-status probe.

If the dashboard cannot use the external AEA payout wallet, provider authentication requires wallet signing, or the account cannot remain provider-only, stop with `PROVIDER_SECURITY_MODEL_INCOMPATIBLE`.

## Live demand recheck

The unauthenticated bounded probe `GET /v1/postings?limit=20` returned HTTP 200 with:

```text
open postings: 0
funded postings: 0
eligible funded postings: 0
```

No bid, acceptance, delivery, payout, wallet operation, or capital movement occurred. PR16 remains unstarted.

## Sources

- Terms: https://the402.ai/terms/
- Provider Agreement: https://the402.ai/provider-terms/
- Provider guide and API authentication: https://the402.ai/docs/providers/
- Public health: https://api.the402.ai/health
- Public postings: https://api.the402.ai/v1/postings?limit=20
