# Human-approved PR1 runtime acceptance amendment

Date: 2026-09-26.
Authority: human reviewer decision supplied through [Approved.txt](../Approved.txt).
Approval source SHA-256:
`2bff741519a0b009be748aa92d12015fee1c0de7960b3e44033896e888ff0d88`.

## Approved decision

- ControlOps Research targets **Python >=3.13**.
- Python **3.13** is the compatibility baseline.
- Python **3.14** is the current preferred runtime.
- Python 3.12 validation is no longer required for PR1.
- Existing successful validation on Python 3.13.14 and 3.14.4 is sufficient for
  PR1's runtime acceptance criterion.

This explicitly supersedes the Python 3.12 validation requirement in the earlier
D4 design/acceptance record. The historical design package and its pinned manifest
remain unchanged. Its previous three-version requirement is historical, not an
outstanding implementation acceptance item.

## Scope

Update package runtime metadata, the canonical PR1 specification, implementation
report and current overview documents. Rerun the existing suite on Python 3.14
and `git diff --check` after the update; record actual results in the PR1 record.

No policy behaviour, policy data, fixture or test changes are authorised or made
by this amendment. Policy identity remains `controlops-public-url/v1.0.0`; package
runtime compatibility metadata is separate from that policy identity.

## Reviewer state

Runtime acceptance criterion: **SATISFIED** by the accepted 3.13.14/3.14.4 evidence.
Final PR1 implementation acceptance: **PENDING REVIEW**.
No PR2 work, staging or commit is authorised.

## Amendment verification

After the human-approved runtime amendment, the unchanged suite was rerun on
Python 3.14.4 using `/tmp/controlops-pr1-py314/bin/python -m pytest` from
`controlops_research/`: **716 passed in 0.46s, exit 0**. `git diff --check` passed.
Offline editable installation succeeded and installed `Requires-Python` metadata
was verified as `>=3.13`. The accepted Python 3.13.14 result remains sufficient;
no additional Python 3.13 run was required by this documentation/metadata change.

Policy source, policy data, fixtures, tests and the pinned historical design
package were SHA-256 compared to their pre-amendment baseline: unchanged.
The staged index was also compared byte-for-byte: unchanged.
