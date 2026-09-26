# PR1 implementation review report — 2026-09-26

Subsequent reviewer decision: **ACCEPTED**; see the
[final acceptance record](../approvals/pr1-final-acceptance-2026-09-26.md).
The report below preserves the submitted implementation-review evidence, including
its then-pending status and then-current Git snapshots. The later acceptance
supersedes that status and authorises a commit only after the specified checks.

Result: **IMPLEMENTED — PENDING FINAL ACCEPTANCE REVIEW**. Runtime acceptance is
**SATISFIED** under the [human-approved amendment](../approvals/pr1-runtime-acceptance-2026-09-26.md):
Python >=3.13, with 3.13 as compatibility baseline and 3.14 preferred.
Python 3.12 validation is no longer required. No staging, commit or PR2 work.

## Files created

- `controlops_research/src/controlops_research/policy.py`
- `controlops_research/src/controlops_research/policy_data.py`
- `controlops_research/tests/test_url_policy.py`
- `controlops_research/tests/fixtures/url_policy/address-boundaries.csv`
- `controlops_research/tests/fixtures/url_policy/namespace-boundaries.json`
- `controlops_research/tests/fixtures/url_policy/decision-examples.json`
- `controlops_research/docs/prs/approvals/pr1-fixture-amendment-2026-09-25/README.md`
- `controlops_research/docs/prs/approvals/pr1-fixture-amendment-2026-09-25/previous-manifest.json`
- `controlops_research/docs/prs/approvals/pr1-fixture-amendment-2026-09-25/previous-address-boundaries.csv`
- `controlops_research/docs/prs/approvals/pr1-fixture-amendment-2026-09-25/PR1-public-url-policy-before-implementation.md`
- `controlops_research/docs/prs/reports/pr1-implementation-2026-09-26.md`
- `controlops_research/docs/prs/approvals/pr1-runtime-acceptance-2026-09-26.md` (subsequent runtime amendment).

## Existing files modified by this implementation and runtime amendment

- `controlops_research/pyproject.toml` (runtime amendment: requires-python >=3.13).
- `controlops_research/README.md`
- `controlops_research/docs/prs/PR1-public-url-policy.md`
- `controlops_research/docs/prs/README.md`
- `controlops_research/docs/prs/PR1-implementation-design/fixtures/address-boundaries.csv`
- `controlops_research/docs/prs/PR1-implementation-design/package-manifest.json`

The original approval files, input text files and other design documents were
already present and were not created or changed by this implementation. The
fixture amendment preserves the original manifest/CSV/spec bytes separately.
Existing unrelated Econo/platform work remains present, as in the initial status.

## Exact implementation summary

`evaluate_url(value: object)` implements `controlops-public-url/v1.0.0` with closed
Decision/ReasonCode string enums, all 17 approved reasons/explanations, and an
immutable ten-field UrlDecision. Only exact built-in str input is evaluated.
No implicit conversion or public policy override; bool(result) raises TypeError.
Original input is excluded from default repr.

The evaluator checks the compiled immutable policy version/data fingerprint before
processing input, returning POLICY_UNAVAILABLE if the approved data cannot be
established. It performs the approved ordered raw/structural/scheme/userinfo/port/
host/destination/component checks, then emits HTTPS ACCEPT or eligible HTTP REVIEW.
HTTP omitted port gives REVIEW/80; explicit :80 rejects; explicit :443 gives
REVIEW/443. There is no upgrade, redirect, connection or exception mechanism.

IPv4 uses the 27 approved deny entries. IPv6 requires one of the 36 pinned
ALLOCATED prefixes and none of the 25 deny entries; deny wins. The 16 effective
namespace restrictions match the approved table. Data is compiled in Python tuples,
not loaded from IANA/XML/JSON at runtime. Hex-only canonical IPv6 spelling is
checked explicitly rather than relying on interpreter-dependent mapped-address
rendering. Canonicalisation preserves approved path/query semantics and removes
validated fragments. All decisions remain candidate/workflow data, not authority.

## Exact commands and observed results

Working directory for both final research runs: `controlops_research/`.

| Command | Runtime / tools | Final result |
| --- | --- | --- |
| `/tmp/controlops-pr1-py314/bin/python -m pytest` | Python 3.14.4 / pytest 9.1.1 | 716 passed in 0.46s, exit 0 |
| `/tmp/controlops-pr1-py313/bin/python -m pytest` | Python 3.13.14 / pytest 9.1.1 | 716 passed in 0.46s, exit 0 |

After the human-approved runtime amendment, the unchanged suite was rerun on
Python 3.14.4 using `/tmp/controlops-pr1-py314/bin/python -m pytest` from
`controlops_research/`: **716 passed in 0.46s, exit 0**. `git diff --check` passed.
Offline editable installation succeeded and installed `Requires-Python` metadata
was verified as `>=3.13`. The accepted Python 3.13.14 result remains sufficient;
no additional Python 3.13 run was required by this documentation/metadata change.

Each run includes 687 PR1 tests and 29 unchanged PR0 import/architecture tests.
Earlier pre-restart research runs also passed: 716 in 0.48s (3.14) and 716 in
0.47s (3.13). The final runs above verified the recovered working tree.

Working directory for existing regressions: `autonomous_economic_agent/`.

- `.venv/bin/python -m pytest tests/unit/test_profile.py tests/unit/test_hashing.py`
  — **8 passed in 0.03s, exit 0**, including the post-recovery rerun. These cover
  economic/Hermes profile, validator identity, Compose linkage and hashing.
  Existing tests were not modified.

Working directory for offline installation: repository root.

- `/tmp/controlops-pr1-py314/bin/python -m pip install --no-build-isolation --no-deps --no-index -e ./controlops_research`
  — successfully installed `controlops-research-0.1.0`, exit 0.
- `/tmp/controlops-pr1-py313/bin/python -m pip install --no-build-isolation --no-deps --no-index -e ./controlops_research`
  — successfully installed `controlops-research-0.1.0`, exit 0.
- `uv python find --offline --no-python-downloads 3.12`
  — no interpreter found in virtual environments, managed installations or search
  path, exit 2. Historical probe: Python 3.12 was unavailable/untested; no
  interpreter was downloaded. It is no longer a target or acceptance requirement.

The environments were populated with existing cached pytest/setuptools using
`uv pip install --python <temporary-environment>/bin/python --offline 'setuptools>=68' 'pytest>=8'`.
No dependency was added to the project's runtime requirements.

## Boundary, side-effect and PR0 results

- All 496 approved vectors passed on both runtimes: 351 address boundaries,
  64 namespace boundaries, 81 full decision examples.
- The parent matrix, 17 reason/state mappings, precedence, canonicalisation and
  idempotence, hostname lengths, IPv6 spellings and overlap rules passed.
- Exact built-in-str, immutable result, bool protection, unavailable/corrupted
  policy and forbidden interpreter-classification fallback checks passed.
- A fresh interpreter verified policy import and all available-policy examples plus
  every address/namespace vector under evaluation guards. No DNS/socket/network,
  process, file/config access, writes, logging, clock or random operation occurred
  during evaluation. Importlib directory caches were primed without executing
  policy modules before applying the policy-import guard.
- The 29 original PR0 architecture/import tests passed unchanged in each run.
  No external or live-service integration test was performed or needed for this
  pure component. These checks do not claim runtime DNS isolation or rebinding
  prevention; those remain future fetch-layer responsibilities.

## Approved amendment and manifest

See [fixture amendment](../approvals/pr1-fixture-amendment-2026-09-25/README.md).
Only two boundary URL fields changed to hex forms; expected
DESTINATION_PROHIBITED results were retained. Separate dotted mapped URLs still
return HOST_NOT_PERMITTED. No policy decision rule or version changed.

- Original manifest: `a6b93936931a85819e5ac2777be9e2b8480cb8ee0df19a943c97245085214c97`.
- Amended manifest: `90e3b506ae26fc936b6822161d693b7f0c7507abff4b3c91b286a4e47d605278`.

All amended artifact/input hashes verified after restart. The original parent
specification is archived and referenced by the amended manifest, while the
canonical PR-level document now records the approved allocation rule and results.
Historical design evidence remains separate and preserved.

## Deviations, environment issues and audit limits

The two fixture corrections and the subsequent Python >=3.13 runtime acceptance
amendment are explicitly human-approved. The latter changes only documentation
and compatibility metadata; policy behaviour/data/fixtures/tests remain unchanged. No additional
unresolved design contradiction or unapproved policy exception was introduced.

An initial unscoped `/tmp/controlops-pr0-venv/bin/python -m pytest` from the repository
root failed collection with 40 errors because unrelated AEA suites/dependencies
were unavailable in that research environment; no tests ran in that invocation.
The first correctly scoped run had 715 passes and one new import-guard harness
failure, corrected by priming module-discovery caches without executing policy
code. Subsequent runs passed; no existing test was weakened.

Research test startup emitted `Failed to create stream fd: Operation not permitted`;
tests still exited 0 with the results above. Pip disabled its unwritable cache;
uv cache access required sandbox escalation and used copy fallback across filesystems.
The server restart removed temporary environments and the full pre-edit hash
baseline. The environments and required tests were restored/repeated. Current
unrelated diff statistics match the observed original 29 files / 1452 insertions /
515 deletions; staged statistics still match the previously staged PR0 19 files /
1143 insertions. The staged index was also byte-compared across recovery completion.
The lost baseline prevents repeating the full byte comparison of every unrelated
file; no unrelated edits were performed.

Five existing IANA XML snapshots contain upstream trailing whitespace and remain
byte-identical. `git diff --check` passes; explicit new-file whitespace checks pass
for authored source/tests/fixtures and amendment evidence. Python parsing, canonical
PR section structure and local documentation links were also checked.

## Capability/change confirmations (this PR)

| Capability or protected system | Introduced/changed? |
| --- | --- |
| Network | NO |
| DNS resolution | NO |
| Database access/migration | NO |
| Model inference | NO |
| Econo | NO |
| Hermes | NO |
| Microsoft validator | NO |
| Compose/profiles | NO |
| PR2 capability | NO |
| Persistence/review notification | NO |
| Paid API | NO |
| Writer/publication/RAG | NO |

## Tested implementation file hashes

- `controlops_research/src/controlops_research/policy.py`: `b2db26465e81f163caa09bd4012ca4d85ef1f5a3af2ac8ff74925e1f80ea8c02`.
- `controlops_research/src/controlops_research/policy_data.py`: `55ea903f754556df442e359922892e16ef9a82816c92722043e52fd1f59a8317`.
- `controlops_research/tests/test_url_policy.py`: `f7f96efe073e603586520f113a1b046c41aab5173f35ba38721beaf528094d0d`.
- `controlops_research/tests/fixtures/url_policy/address-boundaries.csv`: `1edadfe6de492d9b4263b3e84e33e4d073da1cf69432c8640d228018bc90557d`.
- `controlops_research/tests/fixtures/url_policy/namespace-boundaries.json`: `2a9b2a40c85282efce784cb821f146f5269c8de668561aef1a4a9da55f485da2`.
- `controlops_research/tests/fixtures/url_policy/decision-examples.json`: `78b59f53c460c3f6cd10430ad705e291dd947fa28dc2cc2094580b3e72cc86e4`.

## git status --short

```text
 M autonomous_economic_agent/dashboard_plugin/dashboard/dist/index.js
 M autonomous_economic_agent/dashboard_plugin/dashboard/dist/style.css
 M autonomous_economic_agent/docs/aea-dashboard-observability.md
 M autonomous_economic_agent/ops/compose.evm.yaml
 M autonomous_economic_agent/src/aea/control/app.py
 M autonomous_economic_agent/src/aea/ledger/db.py
 M autonomous_economic_agent/src/aea/ledger/models.py
 M autonomous_economic_agent/src/aea/ledger/service.py
 M autonomous_economic_agent/src/aea/observability/__init__.py
 M autonomous_economic_agent/src/aea/observability/schemas.py
 M autonomous_economic_agent/src/aea/observability/service.py
 M autonomous_economic_agent/src/aea/payment/service.py
 M autonomous_economic_agent/src/aea/policy/service.py
 M autonomous_economic_agent/src/aea/policy/signer_client.py
 M autonomous_economic_agent/src/aea/signer/backend.py
 M autonomous_economic_agent/src/aea/signer/evm.py
 M autonomous_economic_agent/src/aea/signer/service.py
 M autonomous_economic_agent/src/aea/supervisor/service.py
 M autonomous_economic_agent/src/aea/types.py
 M autonomous_economic_agent/src/aea/wallet/evm.py
 M autonomous_economic_agent/src/aea/wallet/service.py
 M autonomous_economic_agent/src/aea/wallet/solana.py
 M autonomous_economic_agent/tests/integration/test_observability.py
 M autonomous_economic_agent/tests/integration/test_signer_isolation.py
 M autonomous_economic_agent/tests/unit/test_dashboard_plugin.py
 M autonomous_economic_agent/tests/unit/test_evm_rail.py
 M autonomous_economic_agent/tests/unit/test_m2b_contract.py
 M autonomous_economic_agent/tests/unit/test_observability.py
AM controlops_research/README.md
A  controlops_research/docs/architecture-invariants.md
A  controlops_research/docs/prs/PR0-research-scaffold.md
AM controlops_research/docs/prs/PR1-public-url-policy.md
A  controlops_research/docs/prs/PR10-integration-acceptance.md
A  controlops_research/docs/prs/PR2-fetch-snapshot.md
A  controlops_research/docs/prs/PR3-evidence-plane.md
A  controlops_research/docs/prs/PR4-budget-gate.md
A  controlops_research/docs/prs/PR5-local-runtime-sandbox.md
A  controlops_research/docs/prs/PR6-local-research-loop.md
A  controlops_research/docs/prs/PR7-learn-discovery.md
A  controlops_research/docs/prs/PR8-roadmap-monitor.md
A  controlops_research/docs/prs/PR9-frontier-escalation.md
AM controlops_research/docs/prs/README.md
AM controlops_research/pyproject.toml
A  controlops_research/src/controlops_research/__init__.py
A  controlops_research/src/controlops_research/constants.py
A  controlops_research/tests/test_architecture_boundaries.py
A  controlops_research/tests/test_package_import.py
 M scripts/economic
?? autonomous_economic_agent/scripts/phase-e-baseline
?? autonomous_economic_agent/src/aea/observability/contexts.py
?? autonomous_economic_agent/src/aea/observability/identity.py
?? autonomous_economic_agent/src/aea/observability/readonly.py
?? autonomous_economic_agent/tests/e2e/evidence/dashboard-observability/correctness-degraded-20260831.json
?? autonomous_economic_agent/tests/e2e/evidence/gate-b/gate-b-20260924T203850Z/
?? autonomous_economic_agent/tests/e2e/evidence/m2b/m2b-base-sepolia-e3-20260822T151455Z/
?? autonomous_economic_agent/tests/unit/test_phase_e_baseline.py
?? controlops_research/docs/prs/Approved.txt
?? "controlops_research/docs/prs/Codex scratch pad.txt"
?? "controlops_research/docs/prs/PR1 Public URL Policy.txt"
?? controlops_research/docs/prs/PR1-implementation-design/
?? controlops_research/docs/prs/approvals/
?? controlops_research/docs/prs/reports/
?? controlops_research/src/controlops_research/policy.py
?? controlops_research/src/controlops_research/policy_data.py
?? controlops_research/tests/fixtures/
?? controlops_research/tests/test_url_policy.py
?? platform/postgres/init/017-economic-evm-precision.sql
```

## git diff --stat

```text
 .../dashboard_plugin/dashboard/dist/index.js       |  152 +--
 .../dashboard_plugin/dashboard/dist/style.css      |   17 +-
 .../docs/aea-dashboard-observability.md            |   49 +-
 autonomous_economic_agent/ops/compose.evm.yaml     |    7 +-
 autonomous_economic_agent/src/aea/control/app.py   |   24 +-
 autonomous_economic_agent/src/aea/ledger/db.py     |   21 +-
 autonomous_economic_agent/src/aea/ledger/models.py |    3 +-
 .../src/aea/ledger/service.py                      |   49 +-
 .../src/aea/observability/__init__.py              |    2 +
 .../src/aea/observability/schemas.py               |   71 +-
 .../src/aea/observability/service.py               | 1057 +++++++++++++-------
 .../src/aea/payment/service.py                     |   15 +-
 .../src/aea/policy/service.py                      |    1 +
 .../src/aea/policy/signer_client.py                |    9 +-
 .../src/aea/signer/backend.py                      |    1 +
 autonomous_economic_agent/src/aea/signer/evm.py    |    3 +-
 .../src/aea/signer/service.py                      |   10 +-
 .../src/aea/supervisor/service.py                  |   14 +-
 autonomous_economic_agent/src/aea/types.py         |    6 +-
 autonomous_economic_agent/src/aea/wallet/evm.py    |    7 +-
 .../src/aea/wallet/service.py                      |    4 +-
 autonomous_economic_agent/src/aea/wallet/solana.py |    1 +
 .../tests/integration/test_observability.py        |   36 +-
 .../tests/integration/test_signer_isolation.py     |    9 +
 .../tests/unit/test_dashboard_plugin.py            |    3 +
 .../tests/unit/test_evm_rail.py                    |   45 +
 .../tests/unit/test_m2b_contract.py                |   19 +
 .../tests/unit/test_observability.py               |  273 ++++-
 controlops_research/README.md                      |   12 +-
 .../docs/prs/PR1-public-url-policy.md              |  506 +++++++++-
 controlops_research/docs/prs/README.md             |    7 +-
 controlops_research/pyproject.toml                 |    2 +-
 scripts/economic                                   |   59 +-
 33 files changed, 1951 insertions(+), 543 deletions(-)
```

Git diff statistics include pre-existing unrelated tracked changes and compare
research docs to the earlier staged PR0 placeholder; Git excludes the untracked
new implementation and design evidence from this statistic. The file lists above
describe this implementation's actual scope. Nothing was staged by this task.

## Recommended reviewer action

Review PR1's implementation and fixture amendment against the approved v1.0.0
contract. The reviewer has accepted the Python 3.13.14/3.14.4 validation as
sufficient; Python 3.12 is not an outstanding acceptance item. Final implementation
acceptance remains PENDING. No commit, staging, policy expansion or PR2 work proceeds from
this report.
