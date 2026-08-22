# M3 marketplace research and selection gate

Research date: 2026-08-22  
Governing contract: `m0-design-and-contracts.md` v0.1.2, section 8.3  
Outcome: **PR15 MARKETPLACE SELECTION: BLOCKED**

## Method and labels

This review used current official documentation, public API probes, published terms where available, and official source repositories. No account was created, no terms were accepted, no credential was obtained, and no job, bid, contract, payment, or deliverable was created.

Labels used below:

- **Fact**: directly stated by an official source or observed in a read-only probe.
- **Inference**: conclusion drawn from documented facts and the accepted AEA architecture.
- **Unverified**: material point for which no authoritative evidence was found.

Scores use `0` (absent/disqualifying), `1` (weak or materially unresolved), `2` (usable with constraints), and `3` (strong). A high total cannot override a hard disqualifier.

## Executive decision

No researched marketplace currently satisfies all mandatory requirements while preserving the accepted authority boundaries and the existing Solana-USDC wallet evidence path.

The nearest technical candidates are:

1. **AgentBazaar.dev** for Solana-USDC settlement. It is rejected at this gate because authenticated API calls require general wallet-message signatures made with the wallet private key; the AEA signer exposes only policy-approved `transfer_checked`, and adding generic `sign_message` is forbidden. Its documented public endpoints were also unavailable at the documented base URL, and no applicable published Terms or Privacy document was found.
2. **MoltJobs** for the most complete open-job lifecycle. It is rejected because earnings settle into a separate Turnkey-managed EVM wallet on Base (the CLI documentation also describes Polygon), outside the accepted isolated Solana signer/wallet and reconciliation path. Treating the marketplace API's balance or transaction claim as wallet-backed AEA revenue would weaken PR6/PR11 payment verification.

No live adapter was implemented or enabled. `AEA_ENABLED_ADAPTERS` remains mock-only.

## Scoring matrix

Abbreviations: discovery (`Disc`), acceptance (`Acc`), delivery (`Del`), payment observability (`Pay`), external demand (`Dem`), low-value suitability (`Low`), autonomous compatibility (`Auto`), terms/legal (`Legal`), identity/KYC (`ID`), payment rail/verification (`Rail`), security (`Sec`), API quality (`API`), economics (`Econ`), PR16 suitability (`P16`). Maximum is 42.

| Candidate | Disc | Acc | Del | Pay | Dem | Low | Auto | Legal | ID | Rail | Sec | API | Econ | P16 | Total | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| AgentBazaar.dev | 1 | 1 | 3 | 3 | 1 | 3 | 3 | 0 | 1 | 3 | 1 | 0 | 3 | 0 | 23 | REJECTED |
| MoltJobs | 3 | 2 | 3 | 3 | 2 | 2 | 3 | 1 | 2 | 1 | 2 | 3 | 2 | 0 | 29 | REJECTED |
| Virtuals ACP v2 | 2 | 2 | 3 | 3 | 2 | 2 | 3 | 3 | 1 | 0 | 1 | 3 | 2 | 0 | 27 | REJECTED |
| Olas Mech Marketplace | 1 | 1 | 3 | 3 | 2 | 3 | 3 | 2 | 1 | 0 | 1 | 3 | 2 | 0 | 25 | REJECTED |
| the402 | 1 | 1 | 3 | 3 | 1 | 3 | 3 | 1 | 2 | 0 | 2 | 3 | 3 | 0 | 26 | REJECTED |
| Upwork | 2 | 1 | 1 | 2 | 3 | 0 | 0 | 2 | 0 | 0 | 1 | 1 | 0 | 0 | 13 | REJECTED |
| Fiverr | 0 | 0 | 1 | 1 | 3 | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 9 | REJECTED |
| Amazon Mechanical Turk worker side | 0 | 0 | 2 | 2 | 3 | 3 | 0 | 2 | 1 | 0 | 2 | 0 | 2 | 0 | 17 | REJECTED |
| Gitcoin/typical GitHub bounty flows | 1 | 1 | 2 | 2 | 2 | 0 | 1 | 2 | 2 | 1 | 1 | 1 | 0 | 0 | 16 | REJECTED |

## Candidate findings

### AgentBazaar.dev — rejected

Documented strengths:

- **Fact:** The official documentation describes provider registration, task delivery over WebSocket, polling, or webhook, and result submission.
- **Fact:** Prices use six-decimal USDC micro-units; the provider receives 97% and the platform fee is 3%.
- **Fact:** Settlement is described as USDC on Solana, paid to the registered agent wallet after completion.
- **Fact:** The documented task envelope supports text plus optional files, and the polling/result API would map naturally to the existing marketplace methods after onboarding.

Hard blockers:

- **Fact:** Authentication requires `X-Wallet-Address`, `X-Wallet-Signature`, and a timestamped `agentbazaar:<action>:<timestamp>` message signed with the Solana private key. The official SDK expects a 64-byte Solana keypair path.
- **Inference:** Supplying `signer.key` to an adapter/SDK or adding generic message signing would violate the signer-only, narrow-transfer authority accepted in PR5/PR13/PR14.
- **Fact:** Read-only probes on 2026-08-22 returned 404 for the documented `https://agentbazaar.dev/health`, `/agents`, and `/jobs` paths. `https://api.agentbazaar.dev/health` returned HTTP 525 (TLS failure).
- **Fact:** the `.dev` service's `/terms` and `/privacy` paths returned 404, and its documentation index contains no legal documents.
- **Unverified:** whether the platform will issue a long-lived, receive-and-submit-only provider token through an operator onboarding route that does not require the AEA private key outside the signer.
- **Unverified:** enforceable operator identity, jurisdiction, dispute process, sanctions controls, and production service commitments.
- **Security:** documented files may be up to 100 MB and the broader API exposes email, uploads, swaps, and transaction-building. A future adapter would have to exclude all of these and support text-only tasks.

Reconsider only if the operator can accept published terms and obtain a scoped provider token bound to the existing public wallet without exporting the key or adding general signing authority, and the documented API passes a stable read-only probe.

### MoltJobs — rejected

Documented strengths:

- **Fact:** A public REST endpoint supports open-job discovery; the CLI/API document bidding, starting assigned work, submitting output plus proof hash, webhooks, and wallet transaction queries.
- **Fact:** The platform explicitly markets autonomous agent operation and provides 10 free bids per month and a documented 120 requests/minute platform limit.
- **Fact:** Jobs are funded before work and USDC is released from escrow after approval, with a transaction hash exposed through the API.
- **Fact:** A read-only probe of `GET https://api.moltjobs.io/v1/jobs?status=OPEN&limit=5` returned HTTP 200 and three records on 2026-08-22. Records included budget, acceptance criteria, escrow transaction, payment state, proof hash, deadline, and status fields.

Hard blockers:

- **Fact:** Official wallet documentation says registration provisions a Turnkey-managed EVM wallet and earnings settle in USDC on Base. Official CLI documentation currently describes Turnkey-managed Polygon addresses, an unresolved documentation inconsistency.
- **Inference:** This is a second wallet/signing authority outside the accepted Solana signer. The AEA's Solana wallet read service cannot independently verify or reconcile its Base/Polygon balance or transaction.
- **Inference:** Accepting the marketplace API's payment claim as revenue without corresponding accepted wallet evidence would recreate the fake-payment defect prohibited by M0 and Gate A.
- **Fact:** Withdrawal is a wallet mutation exposed through platform credentials. It cannot be exposed to the model, and bridging/sweeping into Solana is outside PR15 and the no-swaps/no-arbitrary-chain scope.
- **Unverified:** final Terms language, operator identity requirements, geography, tax treatment, and whether AI-produced work must be disclosed. A Terms link was visible but authoritative text was not retrievable through the research interfaces.

Reconsider only after an approved EVM wallet backend and isolated signer/reconciliation design exists, or if MoltJobs supports direct payout to the already-approved Solana USDC address with independently verifiable evidence.

### Virtuals Agent Commerce Protocol — rejected

- **Fact:** ACP is explicitly designed for agents and has programmatic discovery, job creation, provider submission, evaluation, escrow, and on-chain state.
- **Fact:** Published developer terms expressly cover integrating AI agents and using APIs/SDKs.
- **Fact:** ACP v2 documents an 80/20 provider/protocol split and USDC service-fee escrow.
- **Fact:** Current CLI/provider workflows require on-chain identities and marketplace actions signed through an EVM/Solana provider; the documented production job examples use Base chain IDs and ACP-managed signers.
- **Inference:** Integrating ACP provider actions would introduce a second transaction signer and a non-AEA settlement wallet. The broad CLI also includes cards, email, tokenization, token trading, and wallet operations that are explicitly outside the nine-tool boundary.
- **Rejected:** incompatible signing and settlement authority despite strong agent/terms compatibility.

### Olas Mech Marketplace — rejected

- **Fact:** Olas provides an on-chain request/response marketplace for agents, competitive takeover, reputation, and small per-request native/ERC-20 payments.
- **Fact:** Supported marketplace chains are Gnosis, Base, Polygon, and Optimism; USDC support is documented on some EVM chains, not Solana.
- **Fact:** Provider operation requires an EVM agent key/Safe, contract deployment/registration, event monitoring, and IPFS request/response handling.
- **Inference:** This requires another signing authority, arbitrary EVM contract actions, and a broad IPFS fetch surface. It does not fit the accepted Solana wallet or narrow signer contract.

### the402 — rejected

- **Fact:** the402 documents provider APIs/webhooks, agent-compatible automation, USDC escrow, a 5% buyer-paid fee, and prices as low as fractions of a cent.
- **Fact:** Its current payment rail is USDC on Base L2.
- **Inference:** It is primarily a provider catalog/inbound service model rather than an open pool of independently selectable work; genuine demand would arrive only after listing and promotion.
- **Rejected:** Base settlement cannot be reconciled by the accepted Solana wallet, and no approved second signer/custody design exists.

### Conventional marketplaces — rejected

#### Upwork

- **Fact:** compliant automation requires an approved API key and approved use case. Unauthorized scripts, scraping, background polling, browser/session token reuse, and automation outside approved scope may cause suspension.
- **Fact:** API access requires a valid human/company profile, address, photograph, verified payment method, and identity verification. There is no third-party sandbox.
- **Fact:** jobs must meet platform minimums; proposals/contracts and payment are designed around human freelancer/account obligations.
- **Rejected:** cannot pretend the agent is human, cannot assume API proposal/acceptance permission, values are generally unsuitable for a cents-scale experiment, and payout is not directly reconcilable Solana USDC.

#### Fiverr

- **Unverified:** no official seller-side API was found for autonomous discovery, acceptance, delivery, and payment verification.
- **Rejected:** browser automation or UI credential sharing would be required and is forbidden.

#### Amazon Mechanical Turk worker side

- **Fact/inference:** AWS documents requester APIs, but no supported worker API was found for autonomous task claiming and submission.
- **Rejected:** worker UI automation/CAPTCHA avoidance would be required; identity and payout are human-account based.

#### Gitcoin and typical GitHub bounty flows

- **Fact/inference:** bounties can represent genuine external demand and on-chain payout, but current flows are heterogeneous, frequently require manual proposals/repository permissions, and generally involve code execution or values well above the initial envelope.
- **Rejected:** no stable narrow API was verified for discover/accept/submit/payment across one provider, and customer-code execution is outside the initial live job envelope.

## Initial live job envelope if selection reopens

Only these job classes may be mapped into a future adapter:

- bounded text summarization of supplied, explicitly licensed text;
- classification against an explicit label schema;
- structured extraction from supplied plain text or JSON;
- transformation of public-domain or operator-verifiably licensed data;
- concise research using supplied material only, with no arbitrary URL fetching.

Reject before acceptance:

- attachments, binaries, archives, executables, macros, or customer code;
- arbitrary URLs or authenticated third-party resources;
- personal/sensitive data, credential handling, and unauthorized scraping;
- legal, medical, financial, trading, gambling, DeFi, security exploitation, social manipulation, reviews/engagement, academic cheating, or illegal content;
- unclear licensing or economically material unknown fees/settlement terms.

## Economics and payment-verification requirements

A future adapter must expose provider-stated gross reward, platform fee, payout fee, expected compute/API/network cost, settlement probability, and latency. Unknown fees or missing funded/escrow evidence must reject the job conservatively.

Payment status alone is never revenue. The acceptable event remains a unique finalized inbound transfer of canonical Solana USDC to the operator-fixed AEA wallet, matching the marketplace job/payment identity and reconciled by `LedgerService`. A marketplace status, invoice, escrow claim, custodial balance, or transaction hash on an unsupported chain is only a claim.

## Operator/vendor actions required before implementation

At least one of the following must occur before the PR15 selection gate can reopen:

1. **AgentBazaar:** publish applicable production Terms/Privacy documents; restore and stabilize the documented API; provide operator onboarding that issues a narrow provider poll/submit token bound to the existing AEA public wallet without requiring the private key outside the isolated signer or generic message signing; document payout transaction evidence and idempotency.
2. **MoltJobs/the402/Virtuals/Olas:** support direct canonical Solana-USDC payout to the AEA wallet, or land a separately reviewed wallet/signer/reconciliation milestone for their chain before marketplace integration.
3. Another marketplace must provide documented autonomous operation, open external demand, low-value supported work, a narrow credential, and independently verifiable Solana-USDC settlement without a second signing path.

No operator should create an account, accept terms, complete KYC, or provide credentials until the chosen platform passes this gate. Never provide a recovery phrase or private key to a marketplace SDK.

## Sources consulted

Official/primary sources:

- M0 v0.1.2: `autonomous_economic_agent/docs/m0-design-and-contracts.md`, section 8.3.
- AgentBazaar documentation index: https://docs.agentbazaar.dev/llms.txt
- AgentBazaar authentication: https://docs.agentbazaar.dev/authentication.md
- AgentBazaar tasks: https://docs.agentbazaar.dev/concepts/tasks.md
- AgentBazaar payments: https://docs.agentbazaar.dev/concepts/payments.md
- AgentBazaar receive-tasks guide: https://docs.agentbazaar.dev/guides/receive-tasks.md
- AgentBazaar API overview: https://docs.agentbazaar.dev/api-reference/overview.md
- MoltJobs product/API overview: https://moltjobs.io/
- MoltJobs CLI: https://moltjobs.io/docs/cli
- MoltJobs wallet and payment model: https://moltjobs.io/blog/agent-wallets-usdc-payments
- MoltJobs official MCP repository: https://github.com/Moltjobs/moltjobs-mcp
- Virtuals ACP developer agreement: https://app.virtuals.io/acp_developer_agreement.pdf
- Virtuals ACP concepts: https://whitepaper.virtuals.io/acp-product-resources/acp-concepts-terminologies-and-architecture
- Virtuals ACP v2 primer: https://whitepaper.virtuals.io/get-started-with-acp/acp-v2-a-primer
- Virtuals ACP CLI: https://github.com/Virtual-Protocol/acp-cli
- Olas Mech provider documentation: https://stack.olas.network/mech-tools-dev/
- Olas Mech client/payment documentation: https://stack.olas.network/mech-client/
- Olas marketplace contracts: https://github.com/valory-xyz/autonolas-marketplace
- the402 documentation: https://the402.ai/docs/
- the402 provider information: https://the402.ai/providers/
- Upwork automation policy: https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly
- Upwork API access requirements: https://support.upwork.com/hc/en-us/categories/360001180954-Apps
- Upwork prohibited jobs: https://support.upwork.com/hc/en-us/articles/1500007578942-What-kind-of-jobs-aren-t-allowed-on-Upwork

Supplementary discovery sources were used only to locate candidates; marketing/community assertions were not treated as selection evidence.

