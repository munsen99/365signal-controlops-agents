# 03 — Discovery dependency

Discovery is missing. The implement pass stops here.

Inspection of `controlops_research/src` found no module that turns a question
into Microsoft URLs. `policy.py` and `fetch.py` judge or retrieve a URL the
caller already has. Tests use `learn.microsoft.com` as a policy fixture.
That is not a discovery product.

No Bing, Google, DuckDuckGo, Common Crawl, or browser client exists in the
research package. This pack does not add one.

`max_discover = 8` applies to the input URL list once a later approved
mechanism, or an operator seed list, exists. Search snippets, titles, and
SERP text are not evidence and are not passed to infer.

The live acceptance question is fixed:

```text
Does Microsoft recommend phishing-resistant MFA for privileged Entra roles?
```

No seed URL was supplied in this turn. Until the operator writes an explicit
allowlisted seed list for that question, there is no authorised input to
retrieve and no live PR6 run.

A later seed-URL run is an acceptance stand-in. It does not implement
discovery.
