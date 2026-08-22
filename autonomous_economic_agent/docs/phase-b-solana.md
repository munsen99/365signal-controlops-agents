# Phase-B Solana dev/test operator workflow

Phase B uses test value only. Mainnet and `mainnet-beta` are rejected in
configuration. The SPL mint must be an explicitly configured, dedicated
development token; it is represented as `USDC` in the economic ledger because
it exercises the six-decimal test rail, but it is not real USDC.

Install the optional backend with `pip install -e '.[solana]'`. Generate the
dedicated signer key directly in the external secret hierarchy:

```console
python -m aea.wallet.provision generate \
  --key-file /home/proteu5/.config/controlops/economic/signer.key
```

The command prints only the public address and refuses overwrite, symlinks,
malformed files, and non-owner-only key permissions. Obtain devnet SOL using an
operator-selected faucet. Create a six-decimal development SPL mint and source
and destination associated token accounts with trusted Solana operator tooling;
mint test units to the source ATA. Do not reuse a mainnet USDC mint. Record only
the mint, public owners, and ATAs in protected Phase-B configuration.

Copy the example policy, destinations, and environment file into the external
economic secret directory, replace placeholders, calculate the canonical policy
hash with the existing policy loader, and start with the Phase-B Compose overlay.
The destination in model requests is the policy ID, never a caller-supplied ATA;
the signer maps it to the configured owner and derives the ATA itself.

Settlement is `confirmed` by default and may be tightened to `finalized`.
Submission alone is not settlement. The original signature and signed bytes are
retained across uncertain retries in the signer process; retry first queries
chain evidence and never creates a fresh payment. Observed lamport fees are
recorded as SOL `network_fee` cost using the policy's snapshotted SOL/USDC rate.

## PR13 local-validator acceptance

M0 PR13 explicitly permits tests with a local validator. The operator-only
`scripts/phase-b-localnet` wrapper binds Agave to loopback and keeps its ledger,
PID, generated destination key, and public provisioning environment outside
Git. Its lifecycle is:

```console
scripts/phase-b-localnet start
AEA_SIGNER_KEY_FILE=/home/proteu5/.config/controlops/economic/signer.key \
  scripts/phase-b-localnet provision
scripts/phase-b-localnet status
# Start the Phase-B signer on its Unix socket with the protected configuration.
# Export the policy/token/password *file paths* and evidence/run identifiers.
scripts/phase-b-localnet acceptance
scripts/phase-b-localnet stop
scripts/phase-b-localnet clean CONFIRM_CLEAN_LOCALNET
```

`provision` uses only the local faucet and operator SPL CLI: it funds the test
wallet, creates a fresh six-decimal development mint, derives sender and
destination ATAs, and mints test units. It writes public addresses only to
`public.env`. `acceptance` does not load the signer key: Policy HMACs the public
transaction context and calls the separately running signer over its Unix
socket. The database setup is transaction-scoped and rolled back after the
sanitized evidence pack is written.
