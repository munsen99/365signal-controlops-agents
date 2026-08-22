-- M2b: preserve chain-native fee reserves as distinct ledger assets.
BEGIN;

ALTER TABLE economic.agent_accounts
    DROP CONSTRAINT IF EXISTS agent_accounts_asset_check;
ALTER TABLE economic.agent_accounts
    ADD CONSTRAINT agent_accounts_asset_check CHECK (asset IN ('USDC', 'SOL', 'ETH'));

ALTER TABLE economic.opportunities
    DROP CONSTRAINT IF EXISTS opportunities_expected_revenue_asset_check;
ALTER TABLE economic.opportunities
    ADD CONSTRAINT opportunities_expected_revenue_asset_check
    CHECK (expected_revenue_asset IN ('USDC', 'SOL', 'ETH') OR expected_revenue_asset IS NULL);

ALTER TABLE economic.payment_requests
    DROP CONSTRAINT IF EXISTS payment_requests_asset_check;
ALTER TABLE economic.payment_requests
    ADD CONSTRAINT payment_requests_asset_check CHECK (asset IN ('USDC', 'SOL', 'ETH'));

ALTER TABLE economic.economic_costs
    DROP CONSTRAINT IF EXISTS economic_costs_asset_check;
ALTER TABLE economic.economic_costs
    ADD CONSTRAINT economic_costs_asset_check CHECK (asset IN ('USDC', 'SOL', 'ETH'));

ALTER TABLE economic.transfers
    DROP CONSTRAINT IF EXISTS transfers_asset_check;
ALTER TABLE economic.transfers
    ADD CONSTRAINT transfers_asset_check CHECK (asset IN ('USDC', 'SOL', 'ETH'));

CREATE TABLE IF NOT EXISTS economic.chain_transaction_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_request_id UUID NOT NULL REFERENCES economic.payment_requests(request_id),
    rail TEXT NOT NULL CHECK (rail IN ('evm')),
    network TEXT NOT NULL,
    chain_id BIGINT NOT NULL CHECK (chain_id > 0),
    transaction_hash TEXT NOT NULL,
    block_number BIGINT NOT NULL CHECK (block_number >= 0),
    token_contract TEXT NOT NULL,
    gas_used NUMERIC(78, 0) NOT NULL CHECK (gas_used >= 0),
    effective_gas_price_wei NUMERIC(78, 0) NOT NULL CHECK (effective_gas_price_wei >= 0),
    fee_wei NUMERIC(78, 0) NOT NULL CHECK (fee_wei >= 0),
    fee_usdc_snapshot NUMERIC(20, 8) NOT NULL CHECK (fee_usdc_snapshot > 0),
    fee_rate_source TEXT NOT NULL,
    fee_rate_observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rail, network, transaction_hash),
    UNIQUE (payment_request_id)
);
ALTER TABLE economic.chain_transaction_evidence
    ADD COLUMN IF NOT EXISTS fee_usdc_snapshot NUMERIC(20, 8),
    ADD COLUMN IF NOT EXISTS fee_rate_source TEXT,
    ADD COLUMN IF NOT EXISTS fee_rate_observed_at TIMESTAMPTZ;
ALTER TABLE economic.chain_transaction_evidence
    ALTER COLUMN fee_usdc_snapshot SET NOT NULL,
    ALTER COLUMN fee_rate_source SET NOT NULL,
    ALTER COLUMN fee_rate_observed_at SET NOT NULL;
GRANT SELECT, INSERT, UPDATE ON economic.chain_transaction_evidence TO economic_app;
GRANT SELECT ON economic.chain_transaction_evidence TO economic_supervisor;

COMMIT;
