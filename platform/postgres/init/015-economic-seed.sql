-- Dev/M1 seed. Single cash identity: opening_balance is the wallet mirror.
-- opening_capital / fee_reserve transfers are audit-only and excluded from recon.
-- Idempotent. Does not credit a live wallet. Mock wallet credit is PR 4.
-- Policy/constitution hashes are refreshed by apply_schema.sh from git files.

BEGIN;

INSERT INTO economic.policy_versions (
    policy_version,
    policy_document,
    policy_hash,
    effective_from,
    created_by,
    is_current
) VALUES (
    'policy/v0.1.0',
    '{"policy_version":"policy/v0.1.0","wallet_phase":"A","unit_of_account":"USDC"}'::jsonb,
    'pending-apply-schema-hash',
    now(),
    'operator',
    true
)
ON CONFLICT (policy_version) DO UPDATE
SET is_current = true
WHERE economic.policy_versions.is_current IS DISTINCT FROM true;

INSERT INTO economic.constitution_versions (
    constitution_version,
    constitution_hash,
    effective_from,
    created_by
) VALUES (
    'constitution/v0.1.0',
    'pending-apply-schema-hash',
    now(),
    'operator'
)
ON CONFLICT (constitution_version) DO NOTHING;

INSERT INTO economic.supervisor_state (
    singleton,
    frozen,
    signer_enabled,
    loop_enabled,
    updated_by
) VALUES (
    true,
    false,
    true,
    true,
    'operator'
)
ON CONFLICT (singleton) DO NOTHING;

INSERT INTO economic.agent_accounts (
    agent_id,
    asset,
    opening_balance,
    current_balance
) VALUES
    ('economic-agent', 'USDC', 20.00000000, 20.00000000),
    ('economic-agent', 'SOL', 0.05000000, 0.05000000)
ON CONFLICT (agent_id, asset) DO NOTHING;

INSERT INTO economic.transfers (
    account_id,
    direction,
    amount,
    asset,
    classification
)
SELECT a.account_id, 'in', a.opening_balance, a.asset,
       CASE WHEN a.asset = 'USDC' THEN 'opening_capital' ELSE 'fee_reserve' END
FROM economic.agent_accounts a
WHERE a.agent_id = 'economic-agent'
  AND a.opening_balance > 0
  AND NOT EXISTS (
      SELECT 1
      FROM economic.transfers t
      WHERE t.account_id = a.account_id
        AND t.classification IN ('opening_capital', 'fee_reserve')
  );

COMMIT;
