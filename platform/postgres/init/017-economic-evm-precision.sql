-- M2b: retain exact wei precision for EVM native fee reserves and costs.
-- Widening remains compatible with the accepted six/eight-decimal rails.
BEGIN;

CREATE TEMP TABLE aea_saved_economic_views AS
SELECT viewname, definition
  FROM pg_views
 WHERE schemaname = 'economic'
   AND viewname IN ('v_realised_pnl_by_job', 'v_cumulative_realised_pnl',
                    'v_revenue_cost_by_category', 'v_capital_at_risk',
                    'v_rejected_payment_requests', 'v_balance_reconciliation');

DO $$
DECLARE name TEXT;
BEGIN
    FOREACH name IN ARRAY ARRAY[
        'v_realised_pnl_by_job', 'v_cumulative_realised_pnl',
        'v_revenue_cost_by_category', 'v_capital_at_risk',
        'v_rejected_payment_requests', 'v_balance_reconciliation'
    ] LOOP
        EXECUTE format('DROP VIEW IF EXISTS economic.%I CASCADE', name);
    END LOOP;
END $$;

ALTER TABLE economic.agent_accounts
    ALTER COLUMN opening_balance TYPE NUMERIC(38, 18),
    ALTER COLUMN current_balance TYPE NUMERIC(38, 18);

ALTER TABLE economic.economic_costs
    ALTER COLUMN amount TYPE NUMERIC(38, 18);

ALTER TABLE economic.transfers
    ALTER COLUMN amount TYPE NUMERIC(38, 18);

ALTER TABLE economic.chain_transaction_evidence
    ADD COLUMN IF NOT EXISTS l1_fee_wei NUMERIC(78, 0) NOT NULL DEFAULT 0
        CHECK (l1_fee_wei >= 0);

DO $$
DECLARE item RECORD;
BEGIN
    FOR item IN SELECT viewname, definition FROM aea_saved_economic_views LOOP
        EXECUTE format('CREATE VIEW economic.%I AS %s', item.viewname, item.definition);
    END LOOP;
END $$;

GRANT SELECT ON economic.v_realised_pnl_by_job,
                economic.v_cumulative_realised_pnl,
                economic.v_revenue_cost_by_category,
                economic.v_capital_at_risk,
                economic.v_rejected_payment_requests,
                economic.v_balance_reconciliation
TO economic_app, economic_supervisor;

COMMIT;
