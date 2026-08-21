-- Autonomous economic agent ledger. Dedicated schema; not ControlOps assurance.
-- Idempotent. Safe to re-run on an existing controlops volume via
-- autonomous_economic_agent/scripts/apply_schema.sh.
-- Fresh volumes pick this up from /docker-entrypoint-initdb.d.

BEGIN;

CREATE SCHEMA IF NOT EXISTS economic;

COMMENT ON SCHEMA economic IS
'Autonomous economic agent ledger, jobs, policy, audit. Not ControlOps assurance state.';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'economic' AND t.typname = 'usdc_amount'
    ) THEN
        CREATE DOMAIN economic.usdc_amount AS NUMERIC(20, 8)
            CHECK (VALUE = trunc(VALUE, 8));
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS economic.agent_accounts (
    account_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id          TEXT NOT NULL,
    asset             TEXT NOT NULL CHECK (asset IN ('USDC', 'SOL')),
    opening_balance   NUMERIC(20, 8) NOT NULL CHECK (opening_balance >= 0),
    current_balance   NUMERIC(20, 8) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, asset)
);

CREATE TABLE IF NOT EXISTS economic.policy_versions (
    policy_version    TEXT PRIMARY KEY,
    policy_document   JSONB NOT NULL,
    policy_hash       TEXT NOT NULL,
    effective_from    TIMESTAMPTZ NOT NULL,
    created_by        TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_current        BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT chk_policy_created_by_not_agent
        CHECK (created_by <> 'economic-agent')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_economic_policy_current
    ON economic.policy_versions (is_current) WHERE is_current;

CREATE TABLE IF NOT EXISTS economic.constitution_versions (
    constitution_version TEXT PRIMARY KEY,
    constitution_hash    TEXT NOT NULL,
    effective_from       TIMESTAMPTZ NOT NULL,
    created_by           TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_constitution_created_by_not_agent
        CHECK (created_by <> 'economic-agent')
);

CREATE TABLE IF NOT EXISTS economic.opportunities (
    opportunity_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id               TEXT NOT NULL,
    source                 TEXT NOT NULL,
    external_reference     TEXT NOT NULL,
    discovered_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    description_hash       TEXT NOT NULL,
    artefact_uri           TEXT,
    expected_revenue       NUMERIC(20, 8),
    expected_cost          NUMERIC(20, 8),
    expected_margin        NUMERIC(20, 8),
    expected_revenue_asset TEXT CHECK (
        expected_revenue_asset IN ('USDC', 'SOL')
        OR expected_revenue_asset IS NULL
    ),
    risk_score             NUMERIC(6, 5),
    decision               TEXT NOT NULL DEFAULT 'discovered'
        CHECK (decision IN (
            'discovered', 'evaluated', 'accepted', 'declined', 'expired'
        )),
    decision_reason        TEXT,
    policy_version         TEXT REFERENCES economic.policy_versions(policy_version),
    model_id               TEXT,
    runtime_version        TEXT,
    UNIQUE (source, external_reference)
);

CREATE TABLE IF NOT EXISTS economic.jobs (
    job_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id      UUID NOT NULL REFERENCES economic.opportunities(opportunity_id),
    agent_id            TEXT NOT NULL,
    status              TEXT NOT NULL
        CHECK (status IN (
            'accepted', 'performing', 'performed', 'submitted',
            'completed', 'failed', 'cancelled'
        )),
    accepted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at        TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    expected_revenue    NUMERIC(20, 8) NOT NULL,
    realised_revenue    NUMERIC(20, 8) NOT NULL DEFAULT 0,
    deliverable_hash    TEXT,
    policy_version      TEXT REFERENCES economic.policy_versions(policy_version),
    model_id            TEXT,
    runtime_version     TEXT,
    UNIQUE (opportunity_id)
);

CREATE TABLE IF NOT EXISTS economic.payment_requests (
    request_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                  UUID REFERENCES economic.jobs(job_id),
    amount                  NUMERIC(20, 8) NOT NULL CHECK (amount > 0),
    asset                   TEXT NOT NULL CHECK (asset IN ('USDC', 'SOL')),
    destination             TEXT NOT NULL,
    purpose                 TEXT NOT NULL,
    requested_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    policy_decision         TEXT NOT NULL CHECK (policy_decision IN (
                                'pending', 'approved', 'rejected'
                            )),
    rejection_reason        TEXT,
    reason_code             TEXT,
    approved_at             TIMESTAMPTZ,
    approved_amount         NUMERIC(20, 8),
    policy_version          TEXT REFERENCES economic.policy_versions(policy_version),
    canonical_hash          TEXT,
    transaction_reference   TEXT,
    idempotency_key         TEXT NOT NULL,
    correlation_id          UUID NOT NULL,
    UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS economic.economic_costs (
    cost_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID REFERENCES economic.jobs(job_id),
    category            TEXT NOT NULL CHECK (category IN (
                            'compute', 'api', 'data', 'network_fee',
                            'purchased_service', 'other_approved'
                        )),
    amount              NUMERIC(20, 8) NOT NULL CHECK (amount >= 0),
    asset               TEXT NOT NULL CHECK (asset IN ('USDC', 'SOL')),
    usdc_equivalent     NUMERIC(20, 8) NOT NULL CHECK (usdc_equivalent >= 0),
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence_reference  TEXT,
    correlation_id      UUID,
    payment_request_id  UUID
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_costs_payment_request'
    ) THEN
        ALTER TABLE economic.economic_costs
            ADD CONSTRAINT fk_costs_payment_request
            FOREIGN KEY (payment_request_id)
            REFERENCES economic.payment_requests(request_id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS economic.revenues (
    revenue_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                  UUID NOT NULL REFERENCES economic.jobs(job_id),
    amount                  NUMERIC(20, 8) NOT NULL CHECK (amount > 0),
    asset                   TEXT NOT NULL CHECK (asset IN ('USDC')),
    payer_reference         TEXT,
    transaction_reference   TEXT NOT NULL,
    received_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified                BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (transaction_reference)
);

CREATE TABLE IF NOT EXISTS economic.transfers (
    transfer_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id              UUID NOT NULL REFERENCES economic.agent_accounts(account_id),
    direction               TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    amount                  NUMERIC(20, 8) NOT NULL CHECK (amount > 0),
    asset                   TEXT NOT NULL CHECK (asset IN ('USDC', 'SOL')),
    classification          TEXT NOT NULL CHECK (classification IN (
                                'opening_capital', 'operator_top_up',
                                'operator_withdrawal', 'refund',
                                'not_revenue', 'fee_reserve'
                            )),
    transaction_reference   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS economic.decisions (
    decision_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id               UUID REFERENCES economic.jobs(job_id),
    opportunity_id       UUID REFERENCES economic.opportunities(opportunity_id),
    decision_type        TEXT NOT NULL,
    input_summary        TEXT,
    input_hash           TEXT,
    reasoning_summary    TEXT NOT NULL,
    decision             TEXT NOT NULL,
    expected_value       NUMERIC(20, 8),
    confidence           NUMERIC(5, 4),
    policy_version       TEXT,
    model_id             TEXT,
    runtime_version      TEXT,
    constitution_version TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    idempotency_key      TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS economic.audit_events (
    event_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id            TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    correlation_id      UUID,
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash        TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS economic.supervisor_state (
    singleton           BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    frozen              BOOLEAN NOT NULL DEFAULT false,
    signer_enabled      BOOLEAN NOT NULL DEFAULT true,
    loop_enabled        BOOLEAN NOT NULL DEFAULT true,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS economic.incidents (
    incident_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity            TEXT NOT NULL CHECK (severity IN ('info', 'warn', 'critical')),
    kind                TEXT NOT NULL,
    message             TEXT NOT NULL,
    correlation_id      UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_econ_opp_source
    ON economic.opportunities (source, discovered_at DESC);
CREATE INDEX IF NOT EXISTS ix_econ_jobs_status
    ON economic.jobs (status);
CREATE INDEX IF NOT EXISTS ix_econ_costs_job
    ON economic.economic_costs (job_id);
CREATE INDEX IF NOT EXISTS ix_econ_rev_job
    ON economic.revenues (job_id);
CREATE INDEX IF NOT EXISTS ix_econ_pay_decision
    ON economic.payment_requests (policy_decision, requested_at DESC);
CREATE INDEX IF NOT EXISTS ix_econ_audit_corr
    ON economic.audit_events (correlation_id);
CREATE INDEX IF NOT EXISTS ix_econ_audit_type
    ON economic.audit_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_econ_pay_hash
    ON economic.payment_requests (canonical_hash);

CREATE OR REPLACE VIEW economic.v_realised_pnl_by_job AS
SELECT
    j.job_id,
    j.opportunity_id,
    j.status,
    j.expected_revenue,
    COALESCE((SELECT SUM(r.amount) FROM economic.revenues r
              WHERE r.job_id = j.job_id AND r.asset = 'USDC' AND r.verified), 0)
        AS realised_revenue_usdc,
    COALESCE((SELECT SUM(c.usdc_equivalent) FROM economic.economic_costs c
              WHERE c.job_id = j.job_id), 0)
        AS realised_cost_usdc,
    COALESCE((SELECT SUM(r.amount) FROM economic.revenues r
              WHERE r.job_id = j.job_id AND r.asset = 'USDC' AND r.verified), 0)
    - COALESCE((SELECT SUM(c.usdc_equivalent) FROM economic.economic_costs c
                WHERE c.job_id = j.job_id), 0)
        AS realised_pnl_usdc
FROM economic.jobs j;

CREATE OR REPLACE VIEW economic.v_cumulative_realised_pnl AS
SELECT
    a.agent_id,
    a.opening_balance AS opening_usdc,
    a.current_balance AS current_usdc,
    COALESCE((SELECT SUM(r.amount) FROM economic.revenues r
              JOIN economic.jobs j ON j.job_id = r.job_id
              WHERE j.agent_id = a.agent_id AND r.verified), 0) AS revenue_usdc,
    COALESCE((SELECT SUM(c.usdc_equivalent) FROM economic.economic_costs c
              LEFT JOIN economic.jobs j ON j.job_id = c.job_id
              WHERE j.agent_id = a.agent_id OR c.job_id IS NULL), 0) AS cost_usdc,
    COALESCE((SELECT SUM(r.amount) FROM economic.revenues r
              JOIN economic.jobs j ON j.job_id = r.job_id
              WHERE j.agent_id = a.agent_id AND r.verified), 0)
    - COALESCE((SELECT SUM(c.usdc_equivalent) FROM economic.economic_costs c
                LEFT JOIN economic.jobs j ON j.job_id = c.job_id
                WHERE j.agent_id = a.agent_id OR c.job_id IS NULL), 0)
        AS realised_pnl_usdc
FROM economic.agent_accounts a
WHERE a.asset = 'USDC';

CREATE OR REPLACE VIEW economic.v_revenue_cost_by_category AS
SELECT 'revenue'::text AS kind, 'job_payment'::text AS category,
       SUM(amount) AS amount_usdc
FROM economic.revenues WHERE verified
UNION ALL
SELECT 'cost', category, SUM(usdc_equivalent)
FROM economic.economic_costs
GROUP BY category;

CREATE OR REPLACE VIEW economic.v_capital_at_risk AS
SELECT
    (SELECT COALESCE(SUM(j.expected_revenue), 0)
       FROM economic.jobs j
      WHERE j.status IN ('accepted', 'performing', 'performed', 'submitted')
    ) AS expected_inflow_open_jobs,
    (SELECT COALESCE(SUM(c.usdc_equivalent), 0)
       FROM economic.economic_costs c
       JOIN economic.jobs j ON j.job_id = c.job_id
      WHERE j.status IN ('accepted', 'performing', 'performed', 'submitted')
    ) AS sunk_cost_open_jobs,
    (SELECT COALESCE(SUM(pr.amount), 0)
       FROM economic.payment_requests pr
      WHERE pr.asset = 'USDC'
        AND pr.policy_decision = 'approved'
        AND pr.transaction_reference IS NULL
    ) AS approved_unsettled_outflow;

CREATE OR REPLACE VIEW economic.v_rejected_payment_requests AS
SELECT request_id, job_id, amount, asset, destination, purpose,
       requested_at, rejection_reason, reason_code, policy_version, correlation_id
FROM economic.payment_requests
WHERE policy_decision = 'rejected';

CREATE OR REPLACE VIEW economic.v_balance_reconciliation AS
SELECT
    a.agent_id,
    a.asset,
    a.opening_balance,
    a.current_balance AS ledger_balance,
    a.opening_balance
      + COALESCE((SELECT SUM(t.amount) FROM economic.transfers t
                  WHERE t.account_id = a.account_id AND t.direction = 'in'
                    AND t.classification NOT IN ('opening_capital', 'fee_reserve')), 0)
      - COALESCE((SELECT SUM(t.amount) FROM economic.transfers t
                  WHERE t.account_id = a.account_id AND t.direction = 'out'), 0)
      + CASE WHEN a.asset = 'USDC' THEN COALESCE((SELECT SUM(r.amount)
            FROM economic.revenues r
            JOIN economic.jobs j ON j.job_id = r.job_id
            WHERE j.agent_id = a.agent_id AND r.verified), 0) ELSE 0 END
      - COALESCE((SELECT SUM(c.amount) FROM economic.economic_costs c
                  LEFT JOIN economic.jobs j ON j.job_id = c.job_id
                  WHERE c.asset = a.asset
                    AND c.payment_request_id IS NOT NULL
                    AND (j.agent_id = a.agent_id OR j.job_id IS NULL)), 0)
        AS reconstructed_balance,
    a.current_balance - (
      a.opening_balance
      + COALESCE((SELECT SUM(t.amount) FROM economic.transfers t
                  WHERE t.account_id = a.account_id AND t.direction = 'in'
                    AND t.classification NOT IN ('opening_capital', 'fee_reserve')), 0)
      - COALESCE((SELECT SUM(t.amount) FROM economic.transfers t
                  WHERE t.account_id = a.account_id AND t.direction = 'out'), 0)
      + CASE WHEN a.asset = 'USDC' THEN COALESCE((SELECT SUM(r.amount)
            FROM economic.revenues r
            JOIN economic.jobs j ON j.job_id = r.job_id
            WHERE j.agent_id = a.agent_id AND r.verified), 0) ELSE 0 END
      - COALESCE((SELECT SUM(c.amount) FROM economic.economic_costs c
                  LEFT JOIN economic.jobs j ON j.job_id = c.job_id
                  WHERE c.asset = a.asset
                    AND c.payment_request_id IS NOT NULL
                    AND (j.agent_id = a.agent_id OR j.job_id IS NULL)), 0)
    ) AS delta
FROM economic.agent_accounts a;

COMMENT ON VIEW economic.v_balance_reconciliation IS
'Cash identity is the wallet mirror. opening_capital/fee_reserve transfers and compute marks are excluded.';

COMMIT;
