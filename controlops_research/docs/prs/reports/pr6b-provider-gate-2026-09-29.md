# PR6B provider gate — 2026-09-29

```text
DISCOVERY_PROVIDER_MISSING
```

Live acceptance: BLOCKED — provider dependency not satisfied.

Reviewer decision: PENDING.

## What was inspected

| Location | Result |
| --- | --- |
| `src/controlops_research/research/` | PR6A modules only. No discovery adapter. |
| Workspace config and docs for `BING_`, `SEARCH_API`, `SERPAPI`, `BRAVE_SEARCH`, `GOOGLE_CSE`, `DISCOVERY_` | No matches. |
| `docs/prs/PR6-implementation-design/03-discovery-dependency.md` | Discovery recorded as missing. No vendor approved. |
| `docs/prs/PR7-learn-discovery.md` | Placeholder. Status NOT STARTED. Reviewer decision PENDING. Not an adapter, and PR6B forbids starting PR7. |
| This implementation task | Names no provider and does not accept external question disclosure. |

## Stop

No provider-specific code was written. No URL was invented. No search page was fetched. PR5-R and PR6A source were not modified. Nothing was committed.

Two further contracts are already in the way of a later implementation pass, and this gate does not resolve them:

- `tests/test_pr6a_acceptance.py` `test_research_package_has_no_lmstudio_client_or_discovery` fails if any `research/` filename contains `discover`.
- `research/seeds.py` `canonical_seed` upgrades port-less HTTP to HTTPS and keeps userinfo, explicit ports, and all query parameters. The PR6B shared `canonical_seed_url` contract rejects HTTP, userinfo, and an explicit non-443 port, and strips only the five locked `utm_*` parameters. PR6A fetches the `canonical_seed` string. Unifying the two changes accepted PR6A behaviour.

The status document is `docs/prs/PR6B-microsoft-discovery.md`.
