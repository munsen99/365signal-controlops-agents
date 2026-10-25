# PR6B — Microsoft-only discovery door

## Status

```text
Implementation status: NOT IMPLEMENTED
Discovery provider: none
Provider approval basis: none. Repository and configuration inspection on 2026-09-29 found no approved discovery adapter and no operator-named provider.
Question sovereignty boundary: not accepted. No external provider was approved, and no research question was sent off the workstation. External discovery may disclose the operator's research question to the configured discovery provider. That disclosure is a governance boundary and is not incidental metadata.
Live acceptance: BLOCKED — provider dependency not satisfied
Regression status: not run. No source file and no test file was changed. PR5-R and PR6A were left as accepted.
Known limitations:
  - discovery ranking depends on the configured provider/index
  - discovery does not establish authority or truth
  - search snippets are not evidence
  - host policy constrains domains, not semantic relevance
  - PR6A performs the evidence-producing retrieval
  - no semantic entailment judge exists
  - an external provider may receive the operator research question
  - fully local/private discovery requires an approved on-box index or local discovery mechanism
Reviewer decision: PENDING
```

## Gate result

```text
DISCOVERY_PROVIDER_MISSING
```

The implement-time gate stopped this pass before any provider-specific code. No vendor was selected. No search-result HTML was scraped. No browser automation, Common Crawl crawl, or `microsoft.com` crawl was added. No URL was invented from model memory. No temporary or fake discovery provider was added.

Inspection covered:

- `controlops_research/src/controlops_research/research/` contains the accepted PR6A modules only: `allowlist.py`, `artefacts.py`, `extract.py`, `integrity.py`, `loop.py`, `packets.py`, `parse.py`, `retrieve.py`, `seeds.py`. There is no discovery adapter.
- Workspace configuration has no discovery endpoint, API key variable, provider identifier, or local index path (`BING_`, `SEARCH_API`, `SERPAPI`, `BRAVE_SEARCH`, `GOOGLE_CSE`, `DISCOVERY_` were absent).
- `docs/prs/PR6-implementation-design/03-discovery-dependency.md` records that discovery is missing and does not approve Bing, Google, DuckDuckGo, Common Crawl, or a browser client.
- `docs/prs/PR7-learn-discovery.md` is a placeholder. Its implementation result is `NOT STARTED`, reviewer decision `PENDING`, and its own text says the placeholder does not authorise implementation. This PR6B task forbids starting PR7. The PR3 citation catalogue is a local evidence register, not a Microsoft Learn search index.

PR6A remains the seeded loop: `run_research(question, seed_urls)`. Discovery results are not evidence. This document does not change that interface.

## Dependencies still open

A later pass needs an explicit operator decision on each of these. This pass does not choose among them.

1. Name one discovery provider, or an already approved on-box index, and record that approval. If the provider is external, explicitly accept that the operator research question leaves the workstation. If ControlOps must stay fully local, a hosted search API is not an acceptable substitute.
2. Supply the runtime configuration that provider needs (endpoint, key, identifier, or local index path). A missing value must fail before PR6A as `CONFIG_INVALID` or `DISCOVERY_PROVIDER_MISSING`.
3. The frozen PR6A test `test_research_package_has_no_lmstudio_client_or_discovery` asserts that `research/discover.py` is absent and that no file under `research/` has `discover` in its name. Every module name authorised for PR6B contains that substring, so adding them fails this test. The test file is outside the PR6B edit list. Changing the assertion would change a frozen PR6A acceptance check.
4. PR6A and the PR6B seed contract do not describe the same canonical URL. `canonical_seed` in `research/seeds.py` lower-cases the scheme and host, drops the fragment, upgrades a port-less `http` scheme to `https`, keeps userinfo, keeps an explicit port, and keeps every query parameter. `test_scheme_host_and_fragment_collapse_without_rewriting_path_or_query` requires `HTTP://Learn.Microsoft.com/path#frag` to be fetched as `https://learn.microsoft.com/path`. PR6B requires one shared `canonical_seed_url` that rejects HTTP, userinfo, and an explicit non-443 port, strips only `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, and `utm_content`, and is the exact string `run_research` fetches. One function cannot satisfy both contracts without changing accepted PR6A behaviour. Two functions would be a second canonicaliser. Section 27 of the PR6B task says to stop in that case.

## What this pass did not do

- No `research/discover.py`, provider module, artefact writer, or `run_discovered_research` entry point.
- No shared edit to `allowlist.py` or `seeds.py`.
- No PR6B unit tests, because those tests need a provider adapter or would be a temporary provider.
- No live discovery run and no manual seed list for the Entra MFA question.
- No change under `controlops_research/src/controlops_research/runtime/`.
- No jail, lock, probe, or infer change. The jail remains `--unshare-all`.
- No Graph, Azure, Postgres, Writer, trusted RAG, PR7, or PR11 work.
- No commit and no push.

The inspection record is `docs/prs/reports/pr6b-provider-gate-2026-09-29.md`.
