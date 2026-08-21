-- Roles economic_app (ledger DML) and economic_supervisor (freeze rows).
-- Passwords are NOT stored here. apply_schema.sh may ALTER ROLE from
-- ~/.config/controlops/economic/ password files when present.
-- Hermes receives no database credentials.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'economic_app') THEN
        CREATE ROLE economic_app LOGIN PASSWORD NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'economic_supervisor') THEN
        CREATE ROLE economic_supervisor LOGIN PASSWORD NULL;
    END IF;
END
$$;

DO $$
DECLARE
    sch text;
BEGIN
    FOREACH sch IN ARRAY ARRAY[
        'catalogue', 'raw', 'evidence', 'assurance',
        'reporting', 'operations', 'permission_pilot'
    ]
    LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = sch) THEN
            EXECUTE format(
                'REVOKE ALL ON SCHEMA %I FROM economic_app, economic_supervisor',
                sch
            );
            EXECUTE format(
                'REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM economic_app, economic_supervisor',
                sch
            );
        END IF;
    END LOOP;
END
$$;

GRANT USAGE ON SCHEMA economic TO economic_app, economic_supervisor;

GRANT SELECT ON ALL TABLES IN SCHEMA economic TO economic_app;
GRANT SELECT ON ALL TABLES IN SCHEMA economic TO economic_supervisor;

GRANT SELECT, INSERT, UPDATE ON
    economic.opportunities,
    economic.jobs,
    economic.economic_costs,
    economic.revenues,
    economic.transfers,
    economic.payment_requests,
    economic.decisions,
    economic.audit_events,
    economic.incidents
    TO economic_app;

-- Wallet-mirror DML only. Seed opening_balance / account identity is operator-owned.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON economic.agent_accounts FROM economic_app;
GRANT UPDATE (current_balance, updated_at)
    ON economic.agent_accounts TO economic_app;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON
    economic.policy_versions,
    economic.supervisor_state,
    economic.constitution_versions
    FROM economic_app;

GRANT SELECT ON
    economic.policy_versions,
    economic.supervisor_state,
    economic.constitution_versions
    TO economic_app;

GRANT INSERT, UPDATE ON
    economic.supervisor_state,
    economic.incidents,
    economic.audit_events
    TO economic_supervisor;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON
    economic.policy_versions,
    economic.agent_accounts,
    economic.transfers,
    economic.constitution_versions
    FROM economic_supervisor;

REVOKE DELETE, TRUNCATE ON ALL TABLES IN SCHEMA economic
    FROM economic_app, economic_supervisor;

-- Opening-capital / fee-reserve history is seed/operator only.
-- current_user so SET ROLE economic_app is also blocked.
CREATE OR REPLACE FUNCTION economic.reject_seed_transfer_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_user IN ('economic_app', 'economic_supervisor') THEN
        IF TG_OP = 'INSERT'
           AND NEW.classification IN ('opening_capital', 'fee_reserve') THEN
            RAISE EXCEPTION
                '% cannot insert seed transfer classification %',
                current_user, NEW.classification;
        END IF;
        IF TG_OP = 'UPDATE'
           AND (
               OLD.classification IN ('opening_capital', 'fee_reserve')
               OR NEW.classification IN ('opening_capital', 'fee_reserve')
           ) THEN
            RAISE EXCEPTION
                '% cannot alter opening-capital seed/history',
                current_user;
        END IF;
        IF TG_OP = 'DELETE'
           AND OLD.classification IN ('opening_capital', 'fee_reserve') THEN
            RAISE EXCEPTION
                '% cannot delete opening-capital seed/history',
                current_user;
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_reject_seed_transfer_mutation ON economic.transfers;
CREATE TRIGGER trg_reject_seed_transfer_mutation
    BEFORE INSERT OR UPDATE OR DELETE ON economic.transfers
    FOR EACH ROW
    EXECUTE FUNCTION economic.reject_seed_transfer_mutation();

REVOKE ALL ON FUNCTION economic.reject_seed_transfer_mutation() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION economic.reject_seed_transfer_mutation() TO economic_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA economic
    GRANT SELECT, INSERT, UPDATE ON TABLES TO economic_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA economic
    GRANT SELECT ON TABLES TO economic_supervisor;

ALTER ROLE economic_app SET search_path = economic;
ALTER ROLE economic_supervisor SET search_path = economic;

COMMIT;
