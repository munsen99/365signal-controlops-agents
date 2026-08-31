# PR15.2 market presence and discovery

Status: implemented, **non-financial**.

```
MARKET PRESENCE: PASS
COUNTERPARTY DISCOVERY: PASS
MARKET INTELLIGENCE: PASS
CAPITAL-BEARING ACTIONS: NONE
WALLET AUTHORITY EXPANSION: NONE
PR16: NOT STARTED
```

This is not PR16. It does not bid, accept, submit, fund escrow, or sign.

## Presence

`aea.marketplace.presence.ServiceProfile` is a structured advertisement for Econo.

Pinned closed: `custody_delegation=false`, `arbitrary_signing=false`, `public_hosting_supported=false`, `requires_policy_approval=true`, `human_operator_required=true`. Capabilities are the existing text envelope. Settlement is USDC on Base or Solana. Minimum net reward is $2.

## Discovery

`aea.marketplace.discovery.ReadOnlyDiscoveryClient` is GET-only against allow-listed HTTPS origins. It strips/never sends `Authorization`, `X-API-Key`, or `X-PAYMENT`. POST/PUT/PATCH/DELETE are rejected.

## Intelligence

Observations record marketplace, poster, reward, funded flag, hosting/account/custody requirements, and age. `classify_opportunity` emits explicit classes including `ELIGIBLE`, `UNFUNDED`, `STALE`, `HOSTING_REQUIREMENT_UNSUPPORTED`, `CUSTODY_REQUIREMENT_REJECTED`, and `VENDOR_CLARIFICATION_REQUIRED`. `concentration` treats one poster publishing many jobs as `HIGH`, not independent demand.

workpnp remains the preferred future adapter candidate if eligible funded text work appears. MoltJobs remains blocked pending vendor clarification. No new live adapters were added.
