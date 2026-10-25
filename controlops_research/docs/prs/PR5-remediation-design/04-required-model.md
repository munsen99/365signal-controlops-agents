# 04 — Required model id

Source of truth: the `id` strings returned by
`GET http://127.0.0.1:1234/v1/models` on this Hermes host during the
inspection in [01](01-inspection.md). The response has no field that selects
one of those ids as loaded, pinned, or required.

`CONTROLOPS_REQUIRED_MODEL` has no default in code. If the variable is unset
or empty, configuration fails with `CONFIG_INVALID` and no HTTP call is made.
The string `controlops-research-local` is not introduced. The prototype's
hardcoded `qwen3.8-27b` is not kept as a default. That id is one of the twelve
inspected ids. This pack does not promote it.

## Operator line

Implementation is blocked until this line contains one exact id from the
inspection list, with the same spelling and no added whitespace:

```text
CONTROLOPS_REQUIRED_MODEL=qwen3.8-27b
```

The live pack uses that value. Readiness succeeds only when `GET /v1/models`
returns HTTP 200 and a data row whose `id` is equal to that string.
A near-match, including a longer id that merely contains the required string,
is `REQUIRED_MODEL_MISSING`.

The base URL is the fixed production value `http://127.0.0.1:1234`. Tests
inject a fake transport. There is no environment variable that retargets
LM Studio.
