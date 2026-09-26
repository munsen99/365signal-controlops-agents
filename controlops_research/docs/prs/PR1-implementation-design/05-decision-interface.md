# 05 — Decision/data interface and implementation boundary

Decision D5: **PENDING**. Proposed signatures/data only; no source implementation.

## Public interface

`evaluate_url(value: object) -> UrlDecision` is the sole public policy entry point. It uses the built-in approved version only; no caller policy object, version selector, allowlist override, resolver, clock, callback or logger. Accept only exact built-in `str`, rejecting subclasses and other types without invoking user-defined conversion or repr.

`UrlDecision` is an immutable record; `Decision` and `ReasonCode` are closed string enums. `bool(result)` must raise TypeError to prevent truthy rejection/review objects being mistaken for acceptance. Consumers compare the explicit decision value; even ACCEPT is not connection authority. No dedicated exception/override entry point or public network-address validator in PR1. Internal pure address classification may be reused later only through a reviewed interface.

## Exact data shape

All ten keys below are mandatory in the documented JSON representation. No additional keys; no runtime serializer or persistence service is required. Tuple/object representations may be used internally with equivalent immutable semantics.

| Key | Type and invariant |
| --- | --- |
| original_url | string or null; exact built-in string input, even if rejected; null for every other input type |
| decision | ACCEPT, REJECT or REVIEW |
| reason_code | Exactly one of the 17 codes below |
| policy_version | `controlops-public-url/v1.0.0`; null only for POLICY_UNAVAILABLE |
| canonical_url | string for ACCEPT/REVIEW, null for REJECT |
| host | lowercase DNS or canonical bare IP (IPv6 without brackets), null for REJECT |
| host_kind | dns, ipv4 or ipv6 for ACCEPT/REVIEW; null for REJECT |
| effective_port | integer 443 for ACCEPT; 80 or 443 for REVIEW; null for REJECT |
| explanation | Exact constant text below; no URL interpolation |
| requested_human_action | Exact text below for REVIEW; null otherwise |


REVIEW action: `Supply a compliant replacement URL, abandon this source, or propose a future governed policy change.`

No timestamp, run ID, approval flag, signature or evidence status inside this deterministic record. A future workflow may wrap it with orchestration time and identifiers, without changing its decision. Do not infer permission from canonical_url being present. Original URL may contain credentials; suppress it from default object repr, do not log it, and leave future redacted persistence to its own design.

## Exact reason mapping

| Code | Decision | Explanation |
| --- | --- | --- |
| POLICY_UNAVAILABLE | REJECT | The required policy data is unavailable or invalid. |
| INVALID_INPUT | REJECT | A nonempty built-in string is required. |
| FORBIDDEN_RAW_CHARACTER | REJECT | The URL contains a forbidden raw character. |
| MALFORMED_PERCENT_ESCAPE | REJECT | The URL contains a malformed percent escape. |
| FORBIDDEN_ENCODED_CHARACTER | REJECT | The URL encodes a forbidden control or backslash character. |
| MALFORMED_URL | REJECT | The URL does not have an unambiguous absolute authority structure. |
| UNSUPPORTED_SCHEME | REJECT | The URL scheme is not supported by this policy. |
| USERINFO_FORBIDDEN | REJECT | URL userinfo is forbidden. |
| ENCODED_AUTHORITY_FORBIDDEN | REJECT | Percent encoding in the URL authority is forbidden. |
| INVALID_PORT | REJECT | The explicit port is invalid or noncanonical. |
| PORT_NOT_PERMITTED | REJECT | The explicit port is not permitted. |
| HOST_NOT_PERMITTED | REJECT | The host representation does not satisfy the policy. |
| DESTINATION_PROHIBITED | REJECT | The destination is excluded by the address or namespace policy. |
| INVALID_COMPONENT | REJECT | A URL component contains an invalid character. |
| DOT_SEGMENT_FORBIDDEN | REJECT | The URL path contains a prohibited dot segment. |
| HTTP_NOT_PERMITTED | REVIEW | HTTP requires human assessment and cannot proceed automatically. |
| PUBLIC_URL_CANDIDATE | ACCEPT | Candidate source accepted by deterministic URL policy. |

## Evaluation precedence refinements

Policy-unavailable precedes input errors. Then input/type, forbidden raw characters, any malformed percent escape, any forbidden encoded byte, URL structure, scheme, userinfo, encoded authority, invalid explicit port, disallowed port, host representation, destination exclusions, component grammar, dot segments, and finally HTTP REVIEW or HTTPS ACCEPT. Scan for all malformed escapes before encoded-byte rejection so result is not scan-order dependent. These rules propose exact tie-breaking for the parent contract.

Do not let accessing a parser port attribute prematurely change reason precedence. Separate structural splitting from port validation. A bracket/authority structure that cannot be represented unambiguously remains MALFORMED_URL. `file:///etc/passwd` and `data:text/plain,x` fail structure first; `file://host.com/path` reaches UNSUPPORTED_SCHEME. Both reject and neither escalates.

**D5a — confirm HTTP ports:** otherwise eligible omitted-port HTTP is REVIEW with descriptive port 80; explicit :80 rejects; explicit :443 is REVIEW with port 443 and retains :443 in diagnostic canonical_url. This preserves the parent specification exactly, despite the deliberate difference between implicit and explicit HTTP port 80. It is not a recommendation to connect to either.

**D5b — exact built-in str only:** this narrows the generic string wording to avoid invoking user-defined methods during a supposedly pure evaluation. No implicit conversion. No arbitrary  URL length threshold is added by this proposal; resource limits for future externally exposed ingress need their own design.

## Worked complete results

The fixture-only `policy_available` flag describes private test fault injection; it is not a public evaluator argument or caller override.

Full fixed outputs for all states and every reason are in [decision-examples.json](fixtures/decision-examples.json). Four selected objects follow. These are proposed expectations, not observed execution results.

```json
{
  "id": "https-case-default-port",
  "input": "HTTPS://LEARN.MICROSOFT.COM:443",
  "policy_available": true,
  "expected": {
    "original_url": "HTTPS://LEARN.MICROSOFT.COM:443",
    "decision": "ACCEPT",
    "reason_code": "PUBLIC_URL_CANDIDATE",
    "policy_version": "controlops-public-url/v1.0.0",
    "canonical_url": "https://learn.microsoft.com/",
    "host": "learn.microsoft.com",
    "host_kind": "dns",
    "effective_port": 443,
    "explanation": "Candidate source accepted by deterministic URL policy.",
    "requested_human_action": null
  }
}
```

```json
{
  "id": "http-review",
  "input": "http://learn.microsoft.com/",
  "policy_available": true,
  "expected": {
    "original_url": "http://learn.microsoft.com/",
    "decision": "REVIEW",
    "reason_code": "HTTP_NOT_PERMITTED",
    "policy_version": "controlops-public-url/v1.0.0",
    "canonical_url": "http://learn.microsoft.com/",
    "host": "learn.microsoft.com",
    "host_kind": "dns",
    "effective_port": 80,
    "explanation": "HTTP requires human assessment and cannot proceed automatically.",
    "requested_human_action": "Supply a compliant replacement URL, abandon this source, or propose a future governed policy change."
  }
}
```

```json
{
  "id": "http-loopback",
  "input": "http://127.0.0.1/",
  "policy_available": true,
  "expected": {
    "original_url": "http://127.0.0.1/",
    "decision": "REJECT",
    "reason_code": "DESTINATION_PROHIBITED",
    "policy_version": "controlops-public-url/v1.0.0",
    "canonical_url": null,
    "host": null,
    "host_kind": null,
    "effective_port": null,
    "explanation": "The destination is excluded by the address or namespace policy.",
    "requested_human_action": null
  }
}
```

```json
{
  "id": "policy-unavailable",
  "input": "https://learn.microsoft.com/",
  "policy_available": false,
  "expected": {
    "original_url": "https://learn.microsoft.com/",
    "decision": "REJECT",
    "reason_code": "POLICY_UNAVAILABLE",
    "policy_version": null,
    "canonical_url": null,
    "host": null,
    "host_kind": null,
    "effective_port": null,
    "explanation": "The required policy data is unavailable or invalid.",
    "requested_human_action": null
  }
}
```

## Proposed later file layout and checks

Only after separate authorisation: `src/controlops_research/policy.py` for evaluator/types; `src/controlops_research/policy_data.py` for immutable reviewed data; `tests/test_url_policy.py` and test-only fixture copies. Leave __init__.py side-effect-free. Standard library only, pytest remains development-only. No HTTP, DNS, database, model or agent dependencies. Documentation XML is provenance, not a runtime package dependency.

On the future implementation, run install/import and PR0 architecture checks, the new semantic suite and smallest existing profile/hash regressions. This package does not create those files or execute hypothetical tests. No PR2 work, PR1 activation, source changes or commit follows from design-package creation.
