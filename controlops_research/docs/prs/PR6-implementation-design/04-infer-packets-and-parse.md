# 04 — Infer packets and parse

Both calls use `controlops_research.runtime.infer` with
`timeout=180`. Research does not open `127.0.0.1:1234`.

Each packet contains the question and the usable candidates’ `candidate_id`
plus bounded `text`. The instruction is: use only supplied candidate ids;
do not invent URLs, ids, or quotations from outside the packet.

## Selection

The assistant content must be one JSON object:

```json
{"evidence_ids": ["<candidate_id>"]}
```

`evidence_ids` is a list of strings. Unknown ids are left for citation
validation. They are not a parse failure.

## Draft

The second call receives the same bounded texts plus the selected ids.
The assistant content must be one JSON object with exactly these keys:

```json
{
  "status": "supported",
  "finding": "...",
  "evidence_ids": ["<candidate_id>"],
  "rationale": "..."
}
```

`status` is `supported` or `insufficient`. The finding’s `model` field is
copied from `InferResult.model`, which the adapter already checked against
the required id. A `model` field inside the JSON is ignored.
`question` is copied from the run. There is no confidence field.

## Parse failure

If either response is not that JSON shape, the run is `failed` and the
error code is `MODEL_OUTPUT_INVALID`. PR6 does not send a repair prompt.

Adapter failures, including `REQUIRED_MODEL_MISSING`, `ENDPOINT_UNAVAILABLE`,
`MODEL_STATE_INCOMPATIBLE`, and `MODEL_CONTENTION`, fail the run and do not
produce a supported finding. Readiness failure inside the adapter means the
selection POST is not sent.
