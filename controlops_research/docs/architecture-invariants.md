# Architecture invariants

1. Research must not import `aea`.

2. Research must not call Econo control-plane services on ports `18700`, `18701`, `18702`, `18703`, `18704`, or `18705`.

3. Research must not use or mount `aea_run`.

4. Research runtime must never authenticate to Postgres as `economic_app` or `controlops_admin`.

5. Research must not read secrets under `~/.config/controlops/economic`.

6. Research must not use the economic-agent model token.

7. Research must not modify the Econo control plane, signer, wallet, policy, supervisor or marketplace.

8. Research must not become another Hermes profile.

9. Research must not depend on the Microsoft validator profile.

10. Research must not be added to the existing Hermes Compose project.

11. Future local-model access will be explicitly restricted to the approved local LM Studio interface.

12. Future frontier inference must be an explicit governed escalation, never the default research execution path.

13. Model output is not evidence.

14. Evidence must ultimately be traceable to stored source material.

15. Research evidence and approved knowledge are separate concepts.

16. Raw research must not automatically enter the trusted ControlOps RAG.

17. Capability must be introduced progressively through reviewed PRs.

18. Fail closed where an authority, evidence, isolation, budget or runtime precondition cannot be established.

## Authority and future architecture

Models reason. Deterministic controls establish authority.
Evidence, not model output, is the system of record.

The future independent ControlOps Research Driver will coordinate deterministic
fetch/snapshot/hash/evidence logic, local reasoning through LM Studio / qwen3.8-27b,
the Postgres `research` Evidence Plane, and tightly governed Grok escalation only
when explicitly authorised by a future gate. None is implemented in PR0.

## PR0 enforcement and limits

Static AST tests inspect only Python implementation files under
`src/controlops_research/`, excluding documentation and tests. They reject `aea`
imports and obvious forbidden connection/configuration strings, economic secrets
paths and model-token references. Bare integer ports remain valid for future
blocked-destination policy. Module/function/class docstrings are not runtime
configuration. Tests exercise the checker with both rejected and accepted fixtures.

This is a static contract, not a runtime sandbox or proof against dynamically
constructed targets, indirect imports, or external configuration. Later PRs must
extend enforcement for their capabilities; they must not weaken these invariants.
Runtime network admission, authentication, mounts, budget authority, evidence
validation, model access and publication approval cannot yet be runtime-enforced
because PR0 has no such execution paths. Import tests also prohibit external
activity during package import.

## Future writer and RAG boundary

```text
External Sources
  -> Research
  -> Evidence Plane
  -> Verified Finding
  -> Writer
  -> Optional Critic / Polish
  -> Human Approval
  -> Published Knowledge
  -> ControlOps Trusted RAG
```

Research creates evidence. Review creates knowledge.
Only approved knowledge enters the trusted RAG.

Research must not directly publish raw findings into trusted RAG. Writer Agent,
publication workflow and trusted RAG ingestion are outside PR0–PR10 unless a
later approved architecture decision explicitly introduces them.
