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

---

## M2b EVM-rail reassessment (2026-08-22)

Reassessment outcome: **PR15 REASSESSMENT: OPERATOR ONBOARDING REQUIRED**

This section preserves the original blocked decision above as historical evidence. It reassesses only candidates whose original result could have been affected by the accepted M2b EVM rail and Base Sepolia E3 settlement proof. No account was created, no terms were accepted, no wallet was connected, no bid or job was created, and no marketplace state or blockchain state was changed.

### Reassessment decision

**the402 is selected conditionally for the first narrow live adapter, subject to legitimate operator provider onboarding and review of the provider-specific agreement presented during onboarding.** Its provider/open-request path is the only reassessed path found to combine:

- API-key discovery, bidding, job updates, and delivery after operator onboarding;
- terms that expressly contemplate configured AI-agent operation;
- Base canonical-USDC escrow and payout to an operator-supplied external wallet;
- independently observable inbound payment without giving the marketplace or model signing authority;
- low-value jobs and a documented unverified-provider tier capped at USD 25; and
- no requirement for the AEA to sign EIP-3009, EIP-712, arbitrary messages, arbitrary calldata, approvals, or permits when acting only as a provider and using its API credential.

The selection is not adapter approval and is not PR16 approval. Before implementation, the operator must create the provider account, accept the applicable legal terms, review the additional Provider Agreement, set the externally controlled AEA Base address as payout wallet, obtain/restrict the provider API key and webhook secret, and confirm the account exposes the documented open-request provider endpoints. A live public probe returned zero open postings at the time of this review, so genuine available demand must be rechecked before PR16.

### Updated scoring matrix

Scoring uses the original 0–3 scale and dimensions. `Rail/signing` summarizes requirements that a numeric total cannot safely express.

| Candidate | Disc | Acc | Del | Pay | Dem | Low | Auto | Legal | ID | Rail | Sec | API | Econ | P16 | Total | Current status | Rail/signing conclusion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| the402 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 2 | 2 | 3 | 3 | 3 | 3 | 3 | 39 | OPERATOR ONBOARDING REQUIRED | Base is sufficient; provider path needs no AEA wallet signature or contract call |
| MoltJobs | 3 | 2 | 3 | 3 | 2 | 2 | 3 | 3 | 2 | 1 | 2 | 3 | 2 | 1 | 32 | SHORTLISTED | Base rail is supported, but documented Turnkey wallet remains a second debit/signing authority |
| Virtuals ACP v2 | 2 | 2 | 3 | 3 | 2 | 2 | 3 | 3 | 1 | 2 | 0 | 3 | 2 | 0 | 28 | TECHNICAL ADAPTER WORK REQUIRED | Base is supported; broad EVM adapter includes message/EIP-712 signing and contract calls |
| Olas Mech Marketplace | 2 | 1 | 3 | 3 | 2 | 3 | 3 | 2 | 1 | 2 | 1 | 3 | 2 | 0 | 28 | TECHNICAL ADAPTER WORK REQUIRED | Base is supported, but provider setup/delivery requires Marketplace/Safe contract calls; token use can require approval |
| AgentBazaar.dev | 1 | 1 | 3 | 3 | 1 | 3 | 3 | 0 | 1 | 3 | 1 | 0 | 3 | 0 | 23 | REJECTED | Solana, not EVM; general message signing and legal/API blockers remain |

### Blocker-change summary

| Candidate | Original material blocker | Removed by M2b? | Remaining or newly confirmed blocker |
|---|---|---|---|
| the402 | Base settlement could not be reconciled | **Yes** | operator onboarding and Provider Agreement review; public open-postings probe currently returned no demand |
| MoltJobs | EVM/Turnkey wallet outside Solana rail | **Partly** | Base can now be observed, but mandatory Turnkey custody/signing and external-payout support remain unresolved; official CLI still says Polygon |
| Virtuals ACP | EVM settlement and non-AEA signer | **Partly** | provider SDK requires broad transaction capability and exposes `signMessage`/`signTypedData`; smart-account/Privy boundary is not the accepted isolated signer |
| Olas Mech | unsupported EVM contracts and settlement | **Partly** | Base is supported, but registration/request/delivery, Safe, IPFS, and approval/payment calls exceed M2b's ERC-20-transfer-only signer |
| AgentBazaar.dev | general Solana message signing, unavailable API, absent legal terms | **No** | all original hard blockers remain; EVM support is irrelevant |

### the402 — conditionally selected; operator onboarding required

**Programmatic lifecycle.** Official provider documentation exposes provider registration, service publication, signed webhooks, open-request polling (`GET /v1/postings`), bidding (`POST /v1/postings/:id/bids`), status updates, deliverables, and earnings/payment history. Bids can use `X-API-Key`; a paid x402 bid is an alternative, not mandatory for an authenticated provider. Repeating an identical bid is documented as idempotent, while a changed bid replaces it. Provider webhooks are HMAC/timestamp authenticated, not wallet-message signatures.

**External demand and live probe.** The open-request system represents a buyer's funded request and competitive provider bids, so accepted work is genuine external demand rather than self-funded circular revenue. A read-only `GET https://api.the402.ai/v1/postings?limit=5` probe returned HTTP 200 with a valid bounded response and `total: 0`. The catalog endpoint also returned live service records with low-dollar prices. API availability is therefore observed, but current open demand is not established and must not be assumed.

**Rail and custody.** Base is directly supported. Provider documentation says dashboard onboarding creates an embedded Coinbase wallet by default but permits replacement with an external wallet, and that earnings go directly to the embedded or supplied external wallet. The future adapter must configure only the operator-controlled AEA Base address and must reject any marketplace/model payout-address override. Canonical inbound Base USDC can be verified by M2b receipt/log and balance reconciliation. No Polygon or additional signer architecture is required.

**Signing boundary.** the402's *buyer* x402 payment path uses an EIP-3009 USDC authorization and is outside current signer capability. That path must not be used. The selected *provider* path uses an API key for bidding/lifecycle and receives funds; it does not require arbitrary messages, EIP-712, EIP-3009, calldata, approvals, permits, or native-token transfer from the AEA. No contract-call allow-list is required for the initial provider adapter.

**Terms, identity, and economics.** Published terms expressly permit configured AI agents to discover, purchase, authorize payments, communicate, verify, and settle within operator-set limits; prohibit misrepresentation; and place responsibility on an adult account holder. Providers are subject to an additional Provider Agreement that must be reviewed by the operator before credentials are provisioned. The documented platform fee is 5%; provider tiers allow an unverified account to bid only up to USD 25, email-verified up to USD 250, and identity-verified without that tier cap. This fits a bounded approximately USD 20 experiment without requiring KYC to be bypassed. Geography, tax, sanctions, payout timing, and the exact Provider Agreement remain operator-verification items.

**Security envelope.** A future adapter must be provider-only, API-origin allow-listed, bounded and text/JSON-only. It must reject attachments and arbitrary URLs initially, keep API/webhook credentials outside Hermes, verify webhook HMAC/timestamp before durable state changes, deduplicate external request/bid/job/payment IDs, and verify revenue only from canonical inbound Base USDC. The marketplace API's `paid` state alone is not revenue.

### MoltJobs — shortlisted, custody boundary unresolved

M2b removes the unsupported-Base evidence problem but not the wallet-authority problem.

- **Discovery/acceptance/delivery:** official API, CLI, and MCP material document open-job discovery, bids, assignment/start, submission, approval, webhooks, payment state, and idempotency. A read-only jobs probe returned HTTP 200 and three open jobs with budgets from USD 9 to USD 100.
- **Terms/autonomy:** Terms dated 2026-08-02 expressly recognize authorized agents with accountable human/organizational owners, API/CLI/MCP use, truthful bidding, funded jobs, lawful/licensed deliverables, and on-chain USDC settlement. This removes the original legal-text uncertainty.
- **Turnkey boundary:** official wallet documentation says registration automatically provisions a Turnkey-managed Base EVM wallet; the API credential invokes Turnkey-backed withdrawals. In that arrangement Turnkey is custody/key infrastructure, embedded-wallet authentication, transaction signer, payout destination, and withdrawal mechanism—not merely an optional UI convenience. The MCP itself does not sign, but it can request the separate Turnkey signer to move funds.
- **External-wallet question:** no authoritative documentation was found permitting earnings to be paid directly to the AEA's externally controlled address. Therefore the Turnkey wallet cannot be treated as the AEA wallet without creating a second signing/debit authority, and its API balance cannot substitute for accepted wallet reconciliation.
- **Chain inconsistency:** current primary marketing/wallet/terms material says Base; the official CLI page still calls provisioned wallets Polygon addresses. Base would be supported by M2b, while Polygon would ordinarily be a configuration/policy extension to the EVM rail rather than a new signer architecture, but neither resolves custody.
- **Signatures/contracts:** the documented job path does not require the AEA to provide arbitrary message or EIP-712 signatures; it instead relies on API credentials and the managed wallet. That avoids a signature-oracle request but preserves the disqualifying second authority.

MoltJobs remains shortlisted for vendor clarification only: direct external payout, exact production chain, wallet ownership/export/rotation, and whether withdrawals can be disabled while earnings settle directly to the AEA must be answered before selection.

### Virtuals ACP v2 — technical adapter work required; not selected

Base and USDC support mean M2b removes the bare chain incompatibility, but the published EVM adapter contract is much broader than M2b:

- seller operation uses a Privy/Alchemy smart-account adapter with wallet ID and signer private key;
- the provider interface exposes `sendCalls`, plaintext `signMessage`, and EIP-712 `signTypedData` (the latter for v1 compatibility);
- job lifecycle invokes on-chain `createJob`/`createFundTransferJob`, budget/funding/submission/completion actions, and optional fund-transfer/subscription hooks;
- the official CLI additionally exposes generic send-transaction, sign-message, sign-typed-data, swaps, and wallet functions.

Those interfaces cannot receive the AEA key and cannot be passed through to the model. The exact production contract addresses, ABI versions, selectors, and permitted state transitions are not pinned in the reviewed integration overview sufficiently to create an auditable fixed allow-list. A future milestone could evaluate a narrow Base-only allow-list for exact ACP v2 job methods and decoded arguments, but only after eliminating plaintext/EIP-712 signing and managed-wallet dependencies. Configuration alone is insufficient; new signer policy and contract-call review would be required. It is not suitable for PR16 now.

### Olas Mech Marketplace — technical adapter work required; not selected

Current official client documentation now lists Base, Polygon, Gnosis, and Optimism and indicates USDC payment support on Base. This removes the chain-only blocker but exposes a larger protocol surface:

- provider operation entails agent/Safe setup, Marketplace registration, event monitoring, IPFS metadata/request handling, and on-chain delivery;
- Marketplace methods include `create`, `request`/`requestBatch`, `requestFromMarketplace`, `deliverToMarketplace`, and signature-based delivery variants;
- token-funded requester paths can perform ERC-20 `approve` plus transfer/deposit; native-token and subscription paths are also supported;
- published addresses and payment contracts vary by deployment/mech/payment type, and the client detects that type dynamically.

M2b deliberately prohibits approvals, native transfers, arbitrary calldata, and generic contract signing. A future safe integration would need pinned Base deployments, exact ABI signatures/selectors and decoded arguments for provider registration/delivery only, `value = 0`, no requester deposit/approval route, bounded IPFS content, and receipt/event verification. The reviewed official material does not establish one stable minimal provider-only selector/address set, so a safe allow-list cannot be approved from this research alone. This requires new narrowly reviewed signer capability, not configuration only.

### AgentBazaar.dev — rejected unchanged

EVM support does not affect this Solana marketplace. Its documented authentication still requires general timestamped wallet-message signing, which the accepted Solana signer correctly does not expose. A read-only health probe again followed the canonical redirect and returned HTTP 404. Applicable production Terms/Privacy, a stable documented API, and a scoped non-signing provider credential remain unavailable. General message signing remains a hard disqualifier.

### Required operator onboarding for the402

Before adapter implementation, the operator—not Hermes or the model—must:

1. review and accept the current the402 Terms and the provider-specific agreement;
2. create the accountable provider profile and complete only legitimately required email/identity checks;
3. replace or configure the default embedded payout wallet with the dedicated AEA Base public address and verify the address without exporting any private key;
4. create a narrowly scoped provider API key and webhook secret, store both under the external secrets hierarchy, and document revocation;
5. confirm API access to postings, bid, job, deliverable, webhook, and earnings endpoints and confirm that API-key bidding does not invoke x402 payment signing; and
6. confirm at least one eligible, funded, low-risk open request exists before PR16 proceeds.

If the provider agreement forbids the intended autonomous workflow, external payout cannot be configured, API-key bidding requires wallet signing, or no genuine eligible demand exists, selection fails closed and returns to `PR15 REASSESSMENT: STILL BLOCKED`.

### Reassessment sources and probes

Official/primary sources added or rechecked:

- the402 Terms: https://the402.ai/terms/
- the402 documentation: https://the402.ai/docs/
- the402 provider lifecycle, API, requests, webhooks, external wallets, and tier limits: https://the402.ai/docs/providers
- the402 public catalog: `GET https://api.the402.ai/v1/services/catalog?limit=5` (HTTP 200, read-only)
- the402 public postings: `GET https://api.the402.ai/v1/postings?limit=5` (HTTP 200, zero postings, read-only)
- MoltJobs Terms: https://moltjobs.io/terms
- MoltJobs API/product overview: https://github.com/Moltjobs
- MoltJobs wallet model: https://moltjobs.io/blog/agent-wallets-usdc-payments
- MoltJobs MCP boundary: https://github.com/Moltjobs/moltjobs-mcp
- MoltJobs CLI/wallet documentation: https://moltjobs.io/docs/cli
- MoltJobs public jobs: `GET https://api.moltjobs.io/v1/jobs?status=OPEN&limit=5` (HTTP 200, three jobs, read-only)
- Virtuals ACP Node v2: https://github.com/Virtual-Protocol/acp-node-v2
- Virtuals ACP CLI: https://github.com/Virtual-Protocol/acp-cli
- Olas Mech client and supported payment paths: https://github.com/valory-xyz/mech-client
- Olas Marketplace contracts: https://github.com/valory-xyz/autonolas-marketplace
- AgentBazaar health: `GET https://agentbazaar.dev/health` (redirect followed; HTTP 404, read-only)

No community assertion was used to establish selection. Where primary documentation conflicts or omits a material integration fact, the item remains explicitly unresolved.

---

## PR15 the402 revalidation and adapter implementation (2026-08-31)

Revalidation outcome: **architectural hard gates PASS**

Implementation outcome: **PR15: IMPLEMENTATION PASS / OPERATOR ONBOARDING BLOCKED**

Live demand outcome: **PR16 LIVE DEMAND: BLOCKED — NO ELIGIBLE FUNDED POSTINGS**

This section preserves the original 2026-08-22 **PR15 MARKETPLACE SELECTION: BLOCKED** result and the M2b **PR15 REASSESSMENT: OPERATOR ONBOARDING REQUIRED** selection. It re-reads current official documentation and terms before the provider adapter was implemented. No account was created, no terms were accepted, no API key was obtained, no bid/accept/submit was sent to the live API, and no funds were moved.

### Official sources re-read

- Terms of Service, version 2026-05-25: https://the402.ai/terms/
- Provider Agreement, version 2026-05-25: https://the402.ai/provider-terms
- Documentation index: https://the402.ai/docs/
- Provider guide: https://the402.ai/docs/providers
- Provider onboarding prompt: https://api.the402.ai/docs/prompt-provider-onboarding.md
- Provider integration guide: https://api.the402.ai/docs/provider-guide.md
- Well-known manifest: `GET https://api.the402.ai/.well-known/the402.json`
- OpenAPI 3.1: `GET https://api.the402.ai/openapi.json`
- Health: `GET https://api.the402.ai/health`
- Public postings: `GET https://api.the402.ai/v1/postings?limit=5`
- Public catalog: `GET https://api.the402.ai/v1/services/catalog?limit=5`

### Hard-gate results

| Gate | Result | Evidence |
|---|---|---|
| Provider workflow permits autonomous/API operation | **PASS** | Terms §3 authorize configured AI agents; Provider Agreement §2 requires transacting with automated Agents; provider APIs use `X-API-Key` |
| API-key authentication is sufficient for provider actions | **PASS** | Bidding is `POST /v1/postings/:id/bids` via x402 **or** `X-API-Key`; job update/earnings/list-jobs use `X-API-Key` |
| No arbitrary wallet signing | **PASS** | Provider path does not require `signMessage` / wallet message signatures |
| No EIP-712 signing | **PASS** | Buyer x402/EIP-3009 remains out of scope and is not used |
| No arbitrary calldata | **PASS** | Provider adapter performs HTTPS JSON only |
| No ERC-20 approvals/permits | **PASS** | Provider receives USDC; it does not approve or permit |
| Provider payout can use the AEA Base address | **PASS** | Dashboard/settings replacement of the embedded wallet with an external Base address is still documented; payouts are USDC on Base |
| Payment independently observable/reconcilable | **PASS** | Settlement is Base canonical USDC to the operator-supplied wallet; adapter treats marketplace `paid` as a claim until wallet observation |
| Terms do not require identity misrepresentation or human-only operation | **PASS** | Adult accountable account holder; AI-agent operation is explicit; misrepresentation is prohibited |
| Marketplace credentials remain outside Hermes/model scope | **PASS** | API key and webhook secret load from operator files; live adapter default-disabled |

Buyer-side x402 / EIP-3009 remains prohibited. API-key rotation (`POST /v1/participants/rotate-key`) is an x402-signed call and is **not** implemented.

### Material current-state facts that differ from 2026-08-22

These do **not** fail the architectural gates, but they block operator onboarding and PR16:

- **Fact:** Site and docs display “the402 has temporarily paused new activity.”
- **Fact:** `GET https://api.the402.ai/health` returned `status=paused`, `paused=true`, `pause_reason=compliance review`, `paused_at=2026-08-02T21:03:17.928Z`.
- **Fact:** Settlement-related crons (`escrow-monitor`, `provider-settlement`, `auto-refund`, posting notify retries) last succeeded on 2026-08-02 and are stale.
- **Fact:** Read-only `GET /v1/postings?limit=5` still returns HTTP 200, `total: 0`, empty `postings`.
- **Fact:** Catalog remains live (`GET /v1/services/catalog?limit=5` HTTP 200, `total: 485`). Catalog supply is not provider-side demand.
- **Fact:** No operator the402 API key, webhook secret, or provider profile exists under the AEA secrets hierarchy.
- **Inference:** A paused compliance-review marketplace must not be onboarded by automating terms acceptance or identity creation. Adapter tests therefore use fake/sanitized transport.

### Adapter implementation (gated)

`src/aea/marketplace/live/the402.py` implements `MarketplaceAdapter` for the provider workflow only. `AEA_ENABLED_ADAPTERS` remains `mock` by default. `the402` loads only when both `AEA_ENABLED_ADAPTERS` lists it **and** `AEA_THE402_ENABLED` is truthy. Live HTTPS additionally requires `AEA_THE402_LIVE_HTTP=1` and an operator API-key file.

See `docs/the402-live-adapter.md` for credentials, payout wallet, job envelope, state mapping, webhook verification, idempotency, and PR16 preconditions.
