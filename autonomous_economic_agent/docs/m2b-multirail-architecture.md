# M2b multi-rail wallet architecture amendment

Date: 2026-08-22. Governing contract: M0 v0.1.2. This is an additive wallet-layer amendment; it does not change the nine tools or any accepted Solana behavior.

## Boundary and supported envelope

The authority path remains `Model → Control → Policy → HMAC approval → isolated rail signer → chain → verified evidence → Ledger/Reconciliation`. Phase `E` selects the EVM rail. Its first networks are Base local, Base Sepolia, and Base mainnet (chain IDs 131277322940537 for the Py-EVM fixture, 84532, and 8453 respectively). Production configuration enables only one network at a time.

The only EVM debit operation implemented is `erc20_transfer` to canonical USDC. The signer creates calldata itself from a protected destination owner and integer base-unit amount. There is no raw transaction, raw calldata, native transfer, approval, permit, message-signing, typed-data, deployment, swap, bridge, NFT, DeFi, or arbitrary-contract API. A structured future contract-call allow-list is represented by policy's `contract_calls_enabled`, which is schema-locked to `false` in M2b.

Base mainnet native USDC is pinned to `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`; Base Sepolia Circle test USDC is pinned to `0x036CbD53842c5426634e7929541eC2318f3dCF7e`. Both require six decimals. Sources: [Base network information](https://docs.base.org/base-chain/network-information), [Circle USDC contract addresses](https://developers.circle.com/stablecoins/usdc-contract-addresses), and [Base transaction finality](https://docs.base.org/base-chain/network-information/block-building).

## Approval and signing

`EvmApprovalContext` is included in the canonical approved-request hash and Policy HMAC. It binds rail, network, chain ID, operation, payer, token contract, destination, six-decimal base units, and all gas ceilings. The isolated signer re-resolves the destination classification to an operator-configured address and compares every context field before signing. RPC chain ID, deployed token bytecode, and token decimals are independently checked.

The dedicated EVM key is a 32-byte hexadecimal secp256k1 private key (optional `0x` prefix) in an external regular file, owned by the signer UID, mode `0600`. It is never derived from or shared with Solana or an operator wallet. `scripts/evm-keygen` refuses replacement and prints only the public address. The EVM overlay mounts that key only into `economic-signer`; wallet is keyless and Control, Policy, Marketplace, Ledger, Supervisor, and Hermes receive no key mount.

The signer recovery directory is owner-only `0700`; each state file is `0600`, non-symlinked, and contains the canonical/intent hashes plus exact signed transaction bytes. It is persisted before broadcast. After response loss or restart, the signer looks up that exact hash first and reuses the same signed bytes. It never allocates a fresh nonce or payment intent while the outcome is uncertain.

## Gas, nonce, settlement, and accounting

Nonce comes from RPC `pending` state and becomes part of the persisted signed transaction. Gas is estimated by RPC, padded deterministically by 20%, then bounded by policy. EIP-1559 priority fee is capped; maximum fee is `2 × latest base fee + capped priority fee`. Gas limit, max fee per gas, priority fee, and total maximum fee must each fit both Policy and signer configuration. The model supplies none of them.

States are `prepared`, `signed`, `broadcast`, `pending`, `confirmed`, `accepted`, `reverted`, and `unknown`. A hash is not settlement. Base defaults to 12 confirmations for this bounded rail; this is explicit operational confirmation, not Ethereum L1 finality. Applications needing withdrawal-grade L1 finality must wait for Base batch finalization (documented by Base as roughly 20 minutes under normal conditions). Receipt status, chain, sender, token target, zero native value, exact transfer calldata, and exactly one matching `Transfer` log are verified before `accepted`.

Ledger assets remain distinct: USDC principal, SOL fee reserve, and ETH/Base native gas reserve. Exact wei, gas used, effective gas price, chain, token, block and transaction hash are stored in chain evidence; the accepted monetary mirror retains its established eight-decimal database precision. Wei fees are normalized as ETH network costs and never revenue. A Policy-pinned native/USDC snapshot, source, and observation timestamp are stored with the evidence; no exchange rate is fetched or invented by the model. Schema migration 016 adds ETH without changing prior rows. Reconciliation compares USDC and native balances independently while exact fee discrepancies are checked against chain evidence; missing/duplicate entries, wrong chain/token, unexplained external movements, and fee differences fail closed.

## Operations and emergency controls

Use `config/policy.evm.example.yaml`, `config/destinations.evm.example.yaml`, `config/evm.env.example`, and the `ops/compose.evm.yaml` overlay. Install protected files outside Git:

- `policy.evm.yaml` and `destinations.evm.yaml`: operator-controlled, read-only mounts to Control/Policy as shown in Compose.
- `evm_rpc_url`: external RPC credential/URL, read-only only to signer and wallet; URL queries are removed from diagnostics.
- `evm-signer.key`: signer UID, `0600`, signer only.
- `evm-signer-state/`: signer UID, `0700`, signer only.
- `live/CONFIRM_LIVE_USDC_TRANSFER`: absent by default; signer-only read mount.

For Base mainnet, both `AEA_LIVE_WALLET=1` and the accepted protected live confirmation file must be present, while supervisor freeze is false and signing is enabled. Missing, malformed, unreadable, or inconsistent state fails closed. Freeze and signer disable are rechecked immediately before broadcast. Remove the live confirmation and restore `AEA_LIVE_WALLET=0` to disable; there is no automatic re-enable.

Key rotation: freeze, disable signer, remove live confirmation, stop Phase E, reconcile all pending hashes, create a new dedicated key through the operator path, update public-wallet/policy bindings, fund only the bounded reserves, and restart read-only. Revoke RPC credentials separately at the provider.

## Security review

- Replay/chain confusion: EIP-155 chain ID plus MAC-bound network/chain; RPC mismatch rejects.
- Malicious RPC/nonce manipulation: deterministic caps and post-receipt raw transaction/log verification; residual risk remains until evidence is corroborated by an independent RPC.
- Gas griefing: four independent ceilings; no model-controlled gas.
- Approval drain/signature oracle: no `approve`, permit, message, typed-data, or generic signing method.
- Token/address poisoning: canonical contract and protected destination mapping; checksum normalization is not treated as authorization.
- Replacement/response loss: exact signed bytes and nonce persist before broadcast; no automatic replacement transaction.
- Reorganization/finality: configurable confirmations reduce short-reorg risk; L2 confirmation is not represented as L1 finality.

Residual operational risks are RPC equivocation/outage, Base sequencer availability, fee-token price volatility, and operator misconfiguration of protected destination addresses. They remain fail-closed or require independent operational review; none is delegated to the model.
