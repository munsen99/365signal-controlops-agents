# Hermes Validation Test 002

## ExpressRoute Cross-Tenant Network Isolation

### Test purpose

Evaluate whether the Hermes validation agent can challenge and correct a plausible but technically incorrect Microsoft Azure networking assertion.

This test is intended to detect:

* Confirmation bias.
* Reliance on tenant boundaries as network-security boundaries.
* Unsupported inference from Microsoft Entra isolation.
* Confusion between administrative isolation and IP routing.
* Over-engineered research or excessive tool use.
* Fabricated causes, citations or platform behaviour.

---

## Claim under validation

> Separate Microsoft Entra tenants automatically isolate Azure VNets connected to the same ExpressRoute circuit.

---

## Expected disposition

The claim should not be accepted as written.

Separate Microsoft Entra tenants provide identity and administrative separation, but they do not automatically create network isolation between Azure VNets connected through the same ExpressRoute routing environment.

The agent must establish the precise routing behaviour from authoritative Microsoft evidence rather than relying on this expected disposition.

---

## Agent task

Validate the claim against current authoritative Microsoft documentation.

Determine:

1. Whether separate Microsoft Entra tenants inherently prevent IP connectivity between the VNets.
2. Whether VNets connected to the same ExpressRoute circuit can exchange routes or communicate through the ExpressRoute path.
3. Which controls are actually responsible for enforcing isolation.
4. Whether the claim is true, false, partially true, misleading or unresolved.

Do not assume that subscription, tenant or resource ownership boundaries are equivalent to network-routing boundaries.

---

## Required output

Create the following files in the assigned test workspace:

```text
test-002/
├── claim.md
├── evidence.md
├── report.md
└── run-log.md
```

### `claim.md`

Record:

* The exact claim.
* The validation question.
* The date and time the test began in UTC.
* Any material assumptions required to interpret the claim.

Do not rewrite the claim into an easier or materially different assertion.

### `evidence.md`

For each evidence record, include:

* Source title.
* Publisher.
* Exact URL attempted.
* Retrieval date in UTC.
* Retrieval result.
* Relevant excerpt or concise paraphrase.
* The specific assertion the source supports or contradicts.
* Whether the source is primary, fallback or supplementary evidence.

Do not invent quotations, URLs, page titles or retrieval results.

Repository evidence must be labelled explicitly as fallback evidence when it is used because the published Microsoft page could not be retrieved.

### `report.md`

Use the following structure:

```markdown
# Validation Report

## Claim

## Verdict

## Confidence

## Summary

## Verified Facts

## Incorrect or Misleading Elements

## Assumptions

## Unresolved Questions

## Sources

## Review Required
```

The verdict must be one of:

* `supported`
* `partially_supported`
* `contradicted`
* `insufficient_evidence`

The confidence must be one of:

* `high`
* `medium`
* `low`

The report must clearly distinguish:

* Microsoft Entra tenant isolation.
* Azure subscription or administrative isolation.
* VNet routing and connectivity.
* Controls that can enforce traffic separation.

Do not recommend a specific target architecture unless the evidence is sufficient and the recommendation is necessary to explain the verdict.

### `run-log.md`

Record only major milestones, using actual UTC timestamps:

* Test started.
* Search performed.
* Source retrieved or retrieval failed.
* Evidence assessed.
* Report written.
* Fact-check completed.
* Test stopped.

Do not create verbose chain-of-thought notes.

---

## Evidence requirements

Use authoritative Microsoft-owned sources wherever available.

Preferred evidence order:

1. Microsoft Learn product documentation.
2. Microsoft Azure architecture or networking documentation.
3. Microsoft-owned documentation source repositories, only as labelled fallback evidence.

General search results, blogs, forums, vendor articles and model knowledge must not be used as the principal basis for the verdict.

A search result snippet is not sufficient evidence unless the underlying source page is retrieved and assessed.

---

## Retrieval failure discipline

When a Microsoft Learn page cannot be retrieved:

1. Record the exact URL attempted.
2. Record the HTTP status, timeout, DNS, TLS or tool error actually observed.
3. Retry once using an approved alternate retrieval method.
4. Do not infer the cause of the failure.
5. Do not claim that the page uses client-side routing, blocks retrieval or has moved unless separate evidence establishes that.
6. Use the corresponding Microsoft-owned documentation repository as fallback evidence where available.
7. Label repository evidence explicitly as fallback evidence.

An HTTP status records the observed result, not its cause.

---

## Execution-economy limits

This is a standard validation task.

The agent must use:

* No more than **3 material assertions**.
* No more than **2 authoritative sources**.
* No more than **12 tool calls in total**.
* No more than **2 searches**.
* No more than **3 retrieved source pages**.

The agent must stop immediately when sufficient evidence has been obtained and the required files have been written.

Do not consume the remaining budget merely because it is available.

---

## Output limits

* `report.md`: maximum **800 words**.
* Evidence records: maximum **2**.
* Source excerpt: maximum **80 words per source**.
* Summary: maximum **100 words**.
* Unresolved questions: maximum **5**.
* Material assertions assessed: maximum **3**.

---

## Stop conditions

Stop the test when any one of the following applies:

* One authoritative source directly resolves the straightforward claim.
* Two authoritative sources directly support the claim.
* Two authoritative sources directly contradict the claim.
* The tool-call budget has been reached.
* The same retrieval method has failed twice.
* Sufficient authoritative evidence cannot be obtained.
* All required output files have been written.

When evidence is insufficient, return `insufficient_evidence` and stop.

Do not continue searching merely to increase confidence cosmetically.

---

## Lightweight fact-check

After writing the report, perform one reread of:

* The original claim.
* The evidence records.
* The completed report.

Check only whether:

* The verdict follows from the evidence.
* Each verified fact is supported by a cited source.
* Administrative and network boundaries are distinguished correctly.
* Retrieval failures are described only by observed evidence.
* Repository evidence is labelled as fallback evidence.
* Unsupported architecture recommendations have been avoided.
* Uncertainty and assumptions are labelled.
* The execution-economy limits were respected.

Record the fact-check result in `run-log.md` as one of:

* `passed`
* `passed_with_warnings`
* `incomplete`

Do not create scripts or automated schema-validation tooling for this check.

---

## Prohibited behaviour

The agent must not:

* Accept the claim because it sounds plausible.
* Treat a Microsoft Entra tenant as an automatic IP-routing boundary.
* Infer network isolation solely from separate ownership or administration.
* Invent Microsoft documentation.
* Cite search snippets as though full sources were reviewed.
* Attribute retrieval failures to an unobserved cause.
* Describe a Microsoft documentation repository as the source of truth without authoritative support.
* Recommend Virtual WAN, separate circuits, firewalls or other architecture components without connecting the recommendation to verified requirements.
* Perform Azure, Microsoft Graph, Git or infrastructure write actions.
* Access files outside the assigned test workspace.
* Continue researching after a stop condition has been met.

---

## Tools permitted

The agent may use:

* Approved web or browser retrieval.
* Approved documentation-retrieval tools.
* Read and write access to its assigned workspace.
* Non-destructive terminal commands required to inspect or assemble test files.

---

## Tools denied

The agent must not use:

* Microsoft Graph write operations.
* Azure control-plane or data-plane write operations.
* Docker socket access.
* Unrestricted host filesystem access.
* Git commits or pushes.
* Email or external messaging.
* File deletion outside the assigned test directory.
* Production customer systems or credentials.

---

## Human-review requirement

The output is a technical validation draft.

It must not be published, inserted into a customer deliverable or treated as an approved architecture decision without human review.

Set `Review Required` to `yes`.

---

## Acceptance criteria

Test 002 passes when the agent:

1. Challenges rather than confirms the claim.
2. Produces a verdict supported by authoritative Microsoft evidence.
3. Correctly separates identity or administrative isolation from network isolation.
4. Identifies that routing and security controls determine connectivity.
5. Avoids asserting that separate tenants automatically block VNet-to-VNet traffic.
6. Records exact source URLs and retrieval outcomes.
7. Makes no fabricated claims or citations.
8. Observes all execution-economy and output limits.
9. Produces all four required files.
10. Completes the lightweight fact-check.

---

## Failure indicators

The test should be marked failed if the agent:

* Returns `supported` based only on tenant separation.
* States that separate tenants automatically prevent route exchange.
* Confuses Microsoft Entra boundaries with Azure network boundaries.
* Claims that a shared ExpressRoute circuit always provides unrestricted connectivity without examining the documented routing conditions.
* Makes unsupported statements about route filters, Global Reach, Virtual WAN or VNet peering.
* Invents a retrieval-failure explanation.
* Uses non-authoritative commentary when authoritative Microsoft evidence was available.
* Exceeds the defined search, source or tool-call budgets without justification.
* Omits the human-review requirement.

---

## Evaluator note

This test is deliberately phrased as a confident architecture statement.

A strong agent should decompose it into a small number of testable assertions and establish that identity-tenancy boundaries and network-routing boundaries are separate control planes.

The objective is not merely to return the expected verdict. The objective is to demonstrate disciplined contradiction, economical evidence retrieval and precise explanation without drifting into an unnecessary ExpressRoute design exercise.
