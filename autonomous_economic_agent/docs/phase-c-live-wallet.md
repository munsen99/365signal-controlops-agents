# Phase C constrained Solana mainnet wallet

Phase C is a read-only mainnet wallet unless two independent operator conditions
are both present: `AEA_LIVE_WALLET=1` in the protected runtime environment and
an owner-only regular live-spend file containing exactly
`CONFIRM_LIVE_USDC_TRANSFER`. Control checks the first condition at startup;
the isolated signer checks both conditions immediately before signing and again
before broadcast. There is no model-facing mutation route and no automatic
re-enable.

Only `mainnet-beta`, genesis
`5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d`, canonical Solana USDC mint
`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`, six decimals, a wallet-derived
source ATA, an allow-listed destination owner and its derived ATA, and
`finalized` settlement are accepted. The signer creates exactly one
`transfer_checked` instruction from the HMAC-bound intent. Final parsed chain
evidence must match its payer, mint, source, destination, decimals and integer
base-unit amount before settlement succeeds.

The example smoke policy caps a transaction, daily discretionary spend, and
capital at risk at `0.010000 USDC`. SOL is fee reserve only and its configured
per-transaction ceiling remains `0.001000 SOL`. Operators should install copies
of the Phase-C example policy and destinations under the protected secrets
directory and replace only the explicit wallet and destination values.

Run the read-only probe without a key, signer credential, HMAC key, or live gate:

```sh
python tests/e2e/solana_mainnet_readonly.py
```

Before a smoke transfer, use `scripts/phase-c-live-smoke preview AMOUNT OWNER`.
It prints the source, destination, amount, current operator-supplied fee estimate,
network and pinned policy. Enabling requires the literal operator argument:

```sh
scripts/phase-c-live-smoke enable CONFIRM_LIVE_USDC_TRANSFER
```

There is deliberately no `--force`, non-interactive `yes`, or model-generated
confirmation path. Enabling the file does not itself construct or submit a
transaction. After a single approved smoke transaction, disable the gate and
freeze the system. Remaining live funds are swept out of band, never through
the agent.

RPC URLs may be stored in an external file. Query credentials are scrubbed from
errors and evidence. The signer key remains the PR13 owner-only, non-symlink,
external key file mounted only into the signer.
