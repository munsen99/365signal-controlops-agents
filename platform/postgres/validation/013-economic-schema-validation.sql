\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'economic') THEN
        RAISE EXCEPTION 'Schema economic is missing.';
    END IF;
END
$$;

DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(t, ', ')
      INTO missing
      FROM unnest(ARRAY[
        'agent_accounts', 'policy_versions', 'constitution_versions',
        'opportunities', 'jobs', 'economic_costs', 'revenues', 'transfers',
        'payment_requests', 'decisions', 'audit_events',
        'supervisor_state', 'incidents'
      ]) AS t
     WHERE NOT EXISTS (
         SELECT 1 FROM information_schema.tables
          WHERE table_schema = 'economic' AND table_name = t
     );
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'Missing economic tables: %', missing;
    END IF;
END
$$;

DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(v, ', ')
      INTO missing
      FROM unnest(ARRAY[
        'v_realised_pnl_by_job',
        'v_cumulative_realised_pnl',
        'v_revenue_cost_by_category',
        'v_capital_at_risk',
        'v_rejected_payment_requests',
        'v_balance_reconciliation'
      ]) AS v
     WHERE NOT EXISTS (
         SELECT 1 FROM information_schema.views
          WHERE table_schema = 'economic' AND table_name = v
     );
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'Missing economic views: %', missing;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_costs_payment_request'
    ) THEN
        RAISE EXCEPTION 'economic_costs.payment_request_id FK is missing.';
    END IF;
END
$$;

DO $$
BEGIN
    IF (SELECT pg_catalog.pg_get_userbyid(n.nspowner)
          FROM pg_namespace n WHERE n.nspname = 'economic') <> 'controlops_admin' THEN
        RAISE EXCEPTION 'Schema economic must be owned by controlops_admin.';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'economic'
           AND c.relkind IN ('r', 'v')
           AND pg_catalog.pg_get_userbyid(c.relowner) <> 'controlops_admin'
    ) THEN
        RAISE EXCEPTION 'economic relations must be owned by controlops_admin.';
    END IF;

    IF has_schema_privilege('economic_app', 'economic', 'CREATE')
       OR has_schema_privilege('economic_supervisor', 'economic', 'CREATE') THEN
        RAISE EXCEPTION 'App/supervisor must not CREATE in schema economic.';
    END IF;

    IF has_table_privilege(
        'economic_app', 'catalogue.permission_definition', 'SELECT'
    ) THEN
        RAISE EXCEPTION 'economic_app must not SELECT catalogue.permission_definition.';
    END IF;

    IF has_table_privilege('economic_app', 'economic.supervisor_state', 'INSERT')
       OR has_table_privilege('economic_app', 'economic.supervisor_state', 'UPDATE')
       OR has_table_privilege('economic_app', 'economic.supervisor_state', 'DELETE') THEN
        RAISE EXCEPTION 'economic_app must not alter freeze/supervisor_state.';
    END IF;

    IF has_table_privilege('economic_app', 'economic.policy_versions', 'INSERT')
       OR has_table_privilege('economic_app', 'economic.policy_versions', 'UPDATE')
       OR has_table_privilege('economic_app', 'economic.policy_versions', 'DELETE') THEN
        RAISE EXCEPTION 'economic_app must not alter active policy_versions.';
    END IF;

    IF has_table_privilege('economic_app', 'economic.constitution_versions', 'INSERT')
       OR has_table_privilege('economic_app', 'economic.constitution_versions', 'UPDATE') THEN
        RAISE EXCEPTION 'economic_app must not alter constitution_versions.';
    END IF;

    IF has_table_privilege('economic_app', 'economic.agent_accounts', 'INSERT')
       OR has_table_privilege('economic_app', 'economic.agent_accounts', 'DELETE') THEN
        RAISE EXCEPTION 'economic_app must not insert/delete agent_accounts.';
    END IF;

    IF has_column_privilege(
        'economic_app', 'economic.agent_accounts', 'opening_balance', 'UPDATE'
    ) THEN
        RAISE EXCEPTION 'economic_app must not UPDATE opening_balance.';
    END IF;

    IF NOT has_column_privilege(
        'economic_app', 'economic.agent_accounts', 'current_balance', 'UPDATE'
    ) THEN
        RAISE EXCEPTION 'economic_app must UPDATE current_balance (wallet mirror).';
    END IF;

    IF NOT has_table_privilege(
        'economic_supervisor', 'economic.supervisor_state', 'UPDATE'
    ) THEN
        RAISE EXCEPTION 'economic_supervisor must UPDATE supervisor_state.';
    END IF;

    IF has_table_privilege('economic_supervisor', 'economic.policy_versions', 'UPDATE')
       OR has_table_privilege('economic_supervisor', 'economic.agent_accounts', 'UPDATE')
       OR has_table_privilege('economic_supervisor', 'economic.transfers', 'INSERT') THEN
        RAISE EXCEPTION 'economic_supervisor must not alter policy or opening-capital history.';
    END IF;

    IF has_table_privilege('economic_app', 'economic.agent_accounts', 'DELETE')
       OR has_table_privilege('economic_supervisor', 'economic.jobs', 'DELETE') THEN
        RAISE EXCEPTION 'economic roles must not DELETE ledger rows.';
    END IF;
END
$$;

DO $$
DECLARE
    n_policy integer;
    n_usdc integer;
    n_sol integer;
    n_supervisor integer;
    d_usdc numeric;
    d_sol numeric;
BEGIN
    SELECT count(*) INTO n_policy
      FROM economic.policy_versions WHERE is_current AND policy_version = 'policy/v0.1.0';
    IF n_policy <> 1 THEN
        RAISE EXCEPTION 'Expected one current policy/v0.1.0 row, found %.', n_policy;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM economic.constitution_versions
         WHERE constitution_version = 'constitution/v0.1.0'
    ) THEN
        RAISE EXCEPTION 'constitution/v0.1.0 seed row is missing.';
    END IF;

    SELECT count(*) INTO n_supervisor FROM economic.supervisor_state WHERE singleton;
    IF n_supervisor <> 1 THEN
        RAISE EXCEPTION 'Expected one supervisor_state row.';
    END IF;

    SELECT count(*) INTO n_usdc
      FROM economic.agent_accounts
     WHERE agent_id = 'economic-agent' AND asset = 'USDC'
       AND opening_balance = 20 AND current_balance = 20;
    SELECT count(*) INTO n_sol
      FROM economic.agent_accounts
     WHERE agent_id = 'economic-agent' AND asset = 'SOL'
       AND opening_balance = 0.05 AND current_balance = 0.05;
    IF n_usdc <> 1 OR n_sol <> 1 THEN
        RAISE EXCEPTION 'Seed agent_accounts USDC/SOL opening balances are wrong.';
    END IF;

    SELECT delta INTO d_usdc
      FROM economic.v_balance_reconciliation
     WHERE agent_id = 'economic-agent' AND asset = 'USDC';
    SELECT delta INTO d_sol
      FROM economic.v_balance_reconciliation
     WHERE agent_id = 'economic-agent' AND asset = 'SOL';
    IF d_usdc IS NULL OR abs(d_usdc) > 0.000001 THEN
        RAISE EXCEPTION 'USDC recon delta is %, expected 0.', d_usdc;
    END IF;
    IF d_sol IS NULL OR abs(d_sol) > 0.000001 THEN
        RAISE EXCEPTION 'SOL recon delta is %, expected 0.', d_sol;
    END IF;
END
$$;

-- App cannot rewrite freeze, policy, opening capital, or seed transfers.
DO $$
DECLARE
    account uuid;
    froze boolean;
BEGIN
    SELECT account_id INTO STRICT account
      FROM economic.agent_accounts
     WHERE agent_id = 'economic-agent' AND asset = 'USDC';

    SET LOCAL ROLE economic_app;

    BEGIN
        UPDATE economic.supervisor_state SET frozen = true;
        RAISE EXCEPTION 'economic_app UPDATE supervisor_state succeeded';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    BEGIN
        UPDATE economic.policy_versions SET is_current = false WHERE is_current;
        RAISE EXCEPTION 'economic_app UPDATE policy_versions succeeded';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    BEGIN
        UPDATE economic.agent_accounts SET opening_balance = 0 WHERE account_id = account;
        RAISE EXCEPTION 'economic_app UPDATE opening_balance succeeded';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
    END;

    BEGIN
        INSERT INTO economic.transfers (
            account_id, direction, amount, asset, classification
        ) VALUES (
            account, 'in', 1, 'USDC', 'opening_capital'
        );
        RAISE EXCEPTION 'economic_app INSERT opening_capital succeeded';
    EXCEPTION
        WHEN insufficient_privilege THEN NULL;
        WHEN raise_exception THEN
            IF SQLERRM LIKE '%cannot insert seed transfer%' THEN
                NULL;
            ELSE
                RAISE;
            END IF;
    END;

    RESET ROLE;

    SELECT frozen INTO froze FROM economic.supervisor_state WHERE singleton;
    IF froze THEN
        RAISE EXCEPTION 'freeze state mutated during app-role tests';
    END IF;
END
$$;

-- Compute mark without a payment_request_id must not move recon delta.
DO $$
DECLARE
    d_before numeric;
    d_after numeric;
BEGIN
    SELECT delta INTO d_before
      FROM economic.v_balance_reconciliation
     WHERE agent_id = 'economic-agent' AND asset = 'USDC';

    INSERT INTO economic.economic_costs (
        category, amount, asset, usdc_equivalent
    ) VALUES (
        'compute', 0.00100000, 'USDC', 0.00100000
    );

    SELECT delta INTO d_after
      FROM economic.v_balance_reconciliation
     WHERE agent_id = 'economic-agent' AND asset = 'USDC';

    IF abs(d_after - d_before) > 0.000001 THEN
        RAISE EXCEPTION 'Compute mark changed recon delta from % to %.', d_before, d_after;
    END IF;

    DELETE FROM economic.economic_costs
     WHERE job_id IS NULL AND category = 'compute' AND amount = 0.00100000;
END
$$;

ROLLBACK;
