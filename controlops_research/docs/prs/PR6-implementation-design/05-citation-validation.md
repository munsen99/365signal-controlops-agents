# 05 — Citation validation

Validation is Python in `research/citations.py`. It is not a third infer call
and it does not judge whether the page answers the question.

For every id in `evidence_ids`:

1. The id exists on a usable candidate from this run.
2. That candidate’s `http_status` is 200.
3. `evidence/<candidate_id>.bin` exists and its SHA-256 equals `content_hash`.
4. Extracted `text` is non-empty.
5. No id is unknown.

`status` may remain `supported` only when `evidence_ids` is non-empty and
every id passes 1–5. Otherwise `citation-validation.json` records:

```json
{"result": "CITATION_VALIDATION_FAILED", "errors": ["..."]}
```

`finding.status` is then forced to `insufficient`. `run.json` stays
`completed`. A passed validation records `result: CITATION_VALIDATION_PASSED`
and does not change a draft that already says `insufficient`.

A page that does not answer the question can still yield `supported` when
these referential checks pass. PR6 accepts that limit and does not add an
entailment judge. The live evidence report must repeat this sentence.

Empty `evidence_ids` with draft status `supported` fails validation and
becomes `insufficient`.
