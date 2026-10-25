# 06 — Tests and acceptance

Tests are pytest modules under `controlops_research/tests/test_pr6_*.py`.
The tree has no `controlops_research.tests` package, so
`python3 -m unittest controlops_research.tests.test_pr6_acceptance` is not
the command. The existing PR5-R files are
`tests/test_pr5_acceptance.py` and `tests/test_pr5_infer.py`.

HTTP and infer are fakes. The tests cover:

1. A valid draft with real stored bytes becomes `supported`.
2. A usable candidate whose text cannot support the claim stays `insufficient` when the draft says so.
3. An unknown citation id fails validation and forces `insufficient`.
4. One failed retrieval is recorded and skipped while another usable candidate completes the run.
4b. Zero usable candidates produce `failed` and no finding answer.
5. Malformed model JSON produces `MODEL_OUTPUT_INVALID` and `failed`.
6. A readiness failure performs zero infer POSTs and fails the run.
7. `MODEL_CONTENTION` fails the run.
8. The run directory contains the required artefacts and the hash matches the stored bytes.
9. A final URL outside the allowlist is dropped.
9b. An off-allowlist redirect `Location` is not requested.
10. Snippet text supplied beside a URL is not copied into the infer packet or the evidence file.
11. Writes stay under `$WORKSPACE/runtime/runs/<run_id>/`.
12. The research package source does not reference port `1234` or import `http_client` or `LMStudioProbe`.
13. A body longer than 200_000 bytes stores only the prefix, and `content_hash` matches that prefix.

## Live acceptance

Blocked until discovery exists or the operator supplies seed URLs for:

```text
Does Microsoft recommend phishing-resistant MFA for privileged Entra roles?
```

The later capture list is the question, seeded or discovered URLs, hop
chains, final URL, HTTP status, content hash, selected ids, finding,
`citation-validation.json`, run status, infer model, finish reason, and
elapsed time, plus `GET /v1/models` and
`python -m controlops_research.runtime doctor` before and after.
`scripts/controlops doctor` is not created. The unit suite and the PR5-R
tests run before that live question.

The model-id list must be unchanged. The jail argv must still contain
`--unshare-all` and not `--share-net`.
