# ControlOps Assurance Intelligence — Contextual Architecture

## Document Control

| Field | Value |
| --- | --- |
| Status | Draft — repository-grounded baseline |
| Version | 0.1.0 |
| Last updated | 16 August 2026 |
| Intended audience | Prospective partners, technical stakeholders, security architects, ControlOps analysts and internal maintainers |
| Diagram filename | `ControlOps-Assurance-Intelligence-Contextual-Architecture.png` |
| Repository commit | `c33603808fb70e071ce97c92cd55770036afc80e` |
| Working-tree state | Dirty — tracked modifications and untracked files were present during review |
| Runtime verification date | 16 August 2026 |
| Diagram revision | Not specified 
| Document owner | 365signal / Jon Bruce
| Document purpose | Explain the ControlOps system context and preserve an evidence-based architectural record, including the boundary between current capability and intended evolution |

# Part I — Partner Architecture Overview

## 1. Purpose and Audience

This document explains the ControlOps Assurance Intelligence context to
prospective partners and other technically sophisticated stakeholders. It is
also the internal continuity record for the principal system boundaries,
responsibilities and dependencies.

The architecture diagram expresses both current and target context. This
explanation qualifies it against repository evidence and read-only inspection
of the local proof-of-concept deployment. A box in the diagram is not, by
itself, evidence that a capability is implemented.

## 2. Executive Summary

ControlOps operationalises Microsoft cloud assurance by combining governed
assurance data, semantic knowledge, evidence collection, specialised agents,
model services and human review. Its present implementation is a local-first,
evidence-led proof of concept centred on a Hermes agent runtime, a Microsoft
technical validator, filesystem-backed LanceDB knowledge, and a PostgreSQL
Microsoft Graph permission-classification pilot.

The design separates retrieved knowledge from governed assurance state.
Authoritative material and semantic matches can help investigate a question;
they do not become an assurance decision merely because a model finds them
relevant. Model confidence is not evidence. Human judgement remains
responsible for material classifications, findings and publication decisions.

The diagram also shows intended roles—additional agents, richer workflow APIs,
general drift detection and complete evidence, assurance and reporting
stores—that are not all implemented today. Part II records those distinctions.

## Why ControlOps Matters

Traditional Microsoft cloud assessments are labour-intensive, point-in-time
exercises. Evidence is gathered manually, conclusions are distributed across
documents and spreadsheets, and the relationship between an observation,
control, decision and remediation can be difficult to preserve.

ControlOps is intended to make that assurance process repeatable and
operational:

- evidence can be collected consistently;
- deterministic facts can be evaluated by governed rules;
- specialist agents can accelerate research and analysis;
- material decisions remain subject to accountable human review;
- results can be retained as governed assurance state; and
- subsequent observations can be compared with the approved baseline to
  identify drift.

The intended outcome is not autonomous compliance. It is faster, more
consistent and more defensible human-led assurance.

## 3. Architecture Diagram

![ControlOps Assurance Intelligence — Contextual Architecture](diagrams/ControlOps-Assurance-Intelligence-Contextual-Architecture.png)

## 4. Platform Boundary, Users and Consumers

Inside the conceptual ControlOps boundary are Hermes orchestration and local
state; ControlOps-owned agent definitions, contracts, tests and artefacts;
approved tool integration points; model integration; LanceDB semantic
knowledge; PostgreSQL governed data; and controlled production of assurance
outputs.

Hermes source, LM Studio, Microsoft cloud services, Microsoft Learn and any
optional external model provider are dependencies outside that boundary. Users
and downstream consumers also sit outside it. Microsoft tenant data remains in
the source platform unless an approved, least-privilege interface retrieves it.
The current deployment uses host networking, so the drawn boundary is a system
context rather than a network security zone.

Primary users and consumers are:

- **Security architects**, who submit technical assertions and consume
  evidence-backed findings and architecture guidance;
- **ControlOps analysts**, who curate taxonomy, inspect machine proposals,
  correct classifications and prepare governed outputs;
- **human reviewers**, who approve, reject or adjudicate material conclusions;
  and
- **future API and reporting consumers**, for which no operational ControlOps
  assurance API or populated reporting implementation exists today.

## 5. Hermes Runtime, Agents and Approved Tools

Hermes provides the gateway, local dashboard, model and tool invocation, and
persistent runtime state. The repository owns the ControlOps deployment
overlay, lifecycle checks and agent contracts, but does not vendor Hermes. The
gateway and dashboard were observed running on 16 August 2026.

The Microsoft technical validator is the only defined ControlOps agent. It
tests Microsoft 365, Entra and Azure assertions against approved authoritative
sources and produces structured evidence and verdicts for human review. Its
workflow contract limits assertions, searches, sources and tool calls, requires
a fact-check pass, and defines explicit stop conditions. It is marked
`development`, so it is an experimental evidence assistant rather than a
production assurance authority.

Research, document assembly and fact checking are distinct architectural roles.
The current validator performs bounded research, uses output templates and
requires a fact-check pass, but no separately deployed agents exist for those
roles. Broader multi-agent coordination, approval workflows and API-triggered
execution remain planned.

Approved tool principles are least privilege and task-specific:

- Microsoft Graph MCP is documented as an on-demand, read-only `stdio`
  process. Its executable was observed, but effective permissions and an
  end-to-end Graph request were not verified.
- Azure access is intended to be read-only. Azure CLI exists on the host, but
  no Azure MCP configuration, executable or running process was established in
  the deployed Hermes environment; Azure MCP status is therefore not verified.
- Authoritative web research is restricted to approved Microsoft-owned sources
  for the validator. Search snippets are not evidence.
- Git and filesystem access support inspection and controlled artefact writing.
  The validator denies platform writes, Git commits, external messaging and
  privileged writes.

## 6. Model Services and Processing Boundary

LM Studio is the configured local chat-model service, exposed through a
loopback OpenAI-compatible endpoint. Local embedding models support LanceDB
ingestion and retrieval through a separately maintained local RAG
implementation. Local execution does not confer evidential authority: source
provenance, deterministic results and human decisions remain distinct from
model output.

The architecture permits optional external frontier-model review or
arbitration for selected high-value cases. It is not enabled in the committed
validator configuration and was not observed. Any use would cross an
information-processing boundary and require explicit decisions on data
classification, minimisation, approval and provider governance.

## 7. Knowledge, Evidence and Assurance Data

### LanceDB

LanceDB supports semantic retrieval and knowledge grounding across technical
documents, architecture patterns, framework controls, Microsoft Learn
catalogue material and multimodal content. Retrieval provides context; it does
not prove a claim or approve a control. **LanceDB is not the governed assurance
record.**

### PostgreSQL

PostgreSQL is the intended governed system of record for taxonomy,
classifications, reviews, evidence, assurance state and reporting. The current
implementation is narrower: Microsoft Graph catalogue imports, raw snapshots,
import metadata, a six-pillar/34-domain taxonomy, and a controlled 36-permission
classification pilot with analyst and independent AI reviewer records.

The `evidence`, `assurance` and `reporting` schemas exist but currently contain
no tables. The diagram's broader governed record is therefore target
architecture rather than completed implementation.

### ControlOps Workspace

The workspace holds agents, templates, tests, SQL, validation scripts,
documentation, datasets and generated artefacts. Hermes profile state and some
operational artefacts live outside Git. An artefact is not governed merely
because it appears in the workspace.

## 8. Drift Engine Proposition

The Drift Engine proposition is to establish an approved, governed baseline;
repeat evidence collection on an authorised cadence; compare new observations
with approved state; and identify configuration, permission, control and
evidence drift. This would make change visible in assurance terms rather than
merely as raw platform difference.

The repository demonstrates useful foundations: versioned catalogue imports,
source hashes, current/retired permission state, stable pilot selections and
governed review records. These are not a general Drift Engine. Generalised
automated drift detection, cross-domain comparison and scheduling remain
planned; the validator explicitly denies autonomous scheduling.

## 9. Hybrid Decision Model

ControlOps separates repeatable fact from assurance judgement:

- deterministic facts—such as observed configuration values, catalogue
  changes, freshness, counts and rule predicates—should be derived by rules and
  retained with provenance;
- judgement-led classifications should retain independent analyst and agent
  reviews rather than overwriting one with the other;
- disagreements require explicit human adjudication and an auditable decision;
  and
- model confidence is metadata, not evidence and not a substitute for source
  sufficiency.

The Graph permission pilot demonstrates separate analyst and independent AI
reviewer records and provides comparison and adjudication-oriented structures.
It does not yet implement a general adjudication or publication workflow.

## 10. Assurance Flow, Outputs and Governance

At contextual level, ControlOps is intended to work as follows:

1. A user or workflow defines an assurance question and its scope.
2. Hermes coordinates an appropriate bounded agent and approved tools.
3. Platform evidence is collected without making production changes.
4. Relevant authoritative knowledge is retrieved with provenance.
5. Rules derive deterministic facts and agents assess judgement-led questions.
6. Human review or adjudication is applied where material judgement is needed.
7. Governed evidence relationships, decisions and assurance state are persisted.
8. A traceable evidence pack, finding, verdict, guidance item or report is
   produced for an authorised consumer.

The current validator demonstrates structured evidence, findings, verdicts,
reports and run logs. The permission pilot demonstrates governed review data.
Reusable evidence packs, general architecture guidance, curated reporting and
operational APIs remain incomplete or planned.

The governing principles are human approval, evidence provenance, least
privilege, local-first processing, read-only platform access, no autonomous
production changes, no Docker socket exposure, approved filesystem mounts, and
separation of trusted control instructions from untrusted claims and retrieved
content.

# Part II — Implementation and Verification Record

## 11. Evidence Basis

This record was reconciled against the repository at commit
`c33603808fb70e071ce97c92cd55770036afc80e`, its material uncommitted files, the
architecture diagram, relevant Git history, and read-only runtime checks on
16 August 2026.

Principal repository evidence includes:

- [`README.md`](../../README.md), the ControlOps Compose overlay, lifecycle
  scripts, smoke test, runbook and service inventory;
- the Microsoft validator definition, runtime policy, templates and recorded
  test artefacts;
- the Microsoft Learn catalogue ingestion script and observed LanceDB store;
- PostgreSQL Compose, importer, schema migrations, pilot SQL and validation
  scripts; and
- commits from the validator scaffold (`26632a6`) through the latest committed
  permission-pilot classifications (`c336038`).

## 12. Current Implementation Status

| Capability | Status | Repository evidence | Runtime evidence | Notes |
| --- | --- | --- | --- | --- |
| Hermes gateway and dashboard deployment | Implemented | [`ops/compose.controlops.yaml`](../../ops/compose.controlops.yaml), [`scripts/controlops`](../../scripts/controlops) | Both containers running; dashboard responded; expected mounts present | Hermes source is a separately maintained local dependency |
| Operational deployment checks | Validated | [`tests/operations/controlops-smoke.sh`](../../tests/operations/controlops-smoke.sh), [`docs/operations/hermes-runbook.md`](../operations/hermes-runbook.md) | Read-only smoke test passed | Services have no Docker health check; readiness uses state, HTTP and mount checks |
| Microsoft technical validator | Experimental | [`agents/controlops-msft-validator/agent.yaml`](../../agents/controlops-msft-validator/agent.yaml), [`runtime/SOUL.md`](../../agents/controlops-msft-validator/runtime/SOUL.md) | Deployed profile and persistent state observed | Agent metadata says `development` |
| Validator reports, evidence and fact-check pass | Experimental | [`test-001-entra-connect`](../../agents/controlops-msft-validator/tests/test-001-entra-connect), [`test-002-expressroute-tenant-isolation`](../../agents/controlops-msft-validator/tests/test-002-expressroute-tenant-isolation) | Generated artefacts exist | Proof-of-concept records, not production-service evidence |
| Separate research agent | Planned | Research role appears in the diagram; validator embeds bounded research behaviour | None | No separate agent definition or profile verified |
| Separate document-assembly agent | Planned | Templates demonstrate output contracts | None | No separate agent definition verified |
| Separate fact-checking agent | Planned | Validator contract requires a fact-check pass | None | Behaviour exists within the validator, not as a separate agent |
| Read-only Microsoft Graph MCP | Not verified | [`docs/operations/service-inventory.md`](../operations/service-inventory.md) documents on-demand `stdio` use | Executable detected; no Graph request tested | Effective permissions and collection path remain unverified |
| Azure MCP and read-only Azure collection | Not verified | Validator policy denies `azure_write`; service inventory contains no Azure MCP entry | Host Azure CLI found; no Azure MCP configuration, container executable or process found | Absence of evidence does not establish that the capability is planned, installed or usable |
| Authoritative Microsoft web research | Experimental | Validator source policy and recorded test evidence | Not exercised during this architecture review | Tests record Microsoft Learn use |
| Local chat model through LM Studio | Not verified | [`runtime/config.yaml`](../../agents/controlops-msft-validator/runtime/config.yaml) configures LM Studio | `/v1/models` unavailable at inspection | Current model availability was not observed |
| Local embedding and LanceDB ingestion | Experimental | [`ingest_learn_catalog.py`](../../agents/controlops-msft-validator/scripts/ingest_learn_catalog.py) | Multiple LanceDB tables and local batch RAG directory observed | Depends on a separately maintained local RAG implementation; freshness and quality not revalidated |
| PostgreSQL catalogue and taxonomy | Validated | [`platform/postgres/init`](../../platform/postgres/init), [`platform/postgres/validation`](../../platform/postgres/validation) | PostgreSQL healthy; 1,562 current permissions, six pillars and 34 domains | Validation SQL covers invariants and idempotency |
| Graph permission classification pilot | Validated | [`docs/graph-permission-classification-pilot.md`](../graph-permission-classification-pilot.md), committed migrations and validations | 36 selections and 72 reviews observed | Pilot data is not a complete assurance system |
| Governed evidence, assurance and reporting stores | Planned | Schemas created by [`001-create-database.sql`](../../platform/postgres/init/001-create-database.sql) | Schemas present, but no tables in them | The diagram shows the intended broader record |
| Hermes runtime state, logs and persistence | Implemented | Compose mounts and operational runbook | Hermes profile state, sessions and logs observed | Not a complete assurance workflow-state schema |
| Pilot human review capability | Validated | Pilot review tables, exports and validation SQL | Analyst drafts/submissions and independent AI reviewer submissions observed | Technical rows use `reviewer_kind = 'codex'` for the AI reviewer |
| General adjudication and publication workflow | Planned | Validator requires human review; pilot provides comparison/adjudication-oriented structures | No end-to-end approval or publication flow observed | Identity, segregation-of-duties and publication states remain to be defined |
| Drift Engine foundations | Experimental | Versioned imports, hashes, current-state flags and stable pilot records | Catalogue state and import metadata present | General drift rules, scheduling and cross-domain comparison remain planned |
| Evidence packs, architecture guidance and reports | Experimental | Validator templates and test reports | Workspace artefacts observed | Reusable evidence-pack and guidance products remain incomplete |
| Assurance APIs and reporting consumers | Planned | Named in diagram; reporting schema reserved | No API or populated reporting tables observed | Requires contracts, access controls and governed publication state |
| Optional external frontier-model arbitration | Planned | Optional boundary shown in diagram; fallback examples are commented out | Not enabled or observed | Requires explicit information-governance approval |
| No Docker socket exposure to Hermes | Validated | Agent policy denies `docker_socket`; Compose declares approved mounts | Container inspection found no Docker socket | Applies to the inspected deployment |

## 13. Detailed Runtime and Validation Observations

Read-only checks on 16 August 2026 established that:

- `hermes`, `hermes-dashboard` and PostgreSQL 17 were running; PostgreSQL was
  healthy and published only on `127.0.0.1:5432`;
- gateway mounts matched the declared Hermes data, ControlOps workspace and
  LanceDB paths, while the dashboard had the declared data and workspace
  mounts; no Docker socket was mounted;
- the dashboard responded, although Hermes services have no Docker health
  checks;
- the operational doctor reported 12 passes and three warnings: dirty
  ControlOps and Hermes worktrees and an unavailable LM Studio endpoint;
- PostgreSQL contained 1,562 current permissions, six pillars, 34 domains, 36
  pilot selections and 72 reviews. Review state comprised 28 analyst drafts,
  eight analyst submissions and 36 independent AI submissions;
- the `catalogue`, `raw`, `operations` and `permission_pilot` schemas contained
  tables, while `evidence`, `assurance` and `reporting` did not; and
- multiple LanceDB tables and a deployed validator profile with local state,
  sessions and logs were present.

These are point-in-time observations, not availability, performance or
end-to-end transaction guarantees. The temporary combination of running Hermes
services and an unavailable LM Studio endpoint illustrates that container state
alone does not prove inference readiness. Repository start, restart and rebuild
operations intentionally refuse to proceed while that endpoint is unavailable.

The repository's read-only operational smoke test passed. PostgreSQL validation
scripts and repository notes record extensive invariant and idempotency checks.
This architecture review did not rerun validation SQL that invokes persistent
migrations; it used read-only database queries instead.

## 14. Engineering Discrepancies and Qualification Notes

- The working tree was materially dirty before this revision. Modified agent
  contracts and pilot documentation, generated test artefacts, architecture
  images, prompts, and migrations/validations `010`–`012` were uncommitted. The
  runtime and this record may therefore describe material beyond `HEAD`.
- The committed pilot sequence through migration `009` establishes the
  catalogue sample and independent reviews. Uncommitted migrations `010`–`012`
  add analyst drafts and human corrections observed in the running database;
  those changes do not yet have commit provenance.
- One recorded ExpressRoute run log uses partial `xx` timestamps despite the
  agent's exact runtime-timestamp rule. The test supports workflow shape, but
  not full audit-timestamp compliance.
- In `agent.yaml`, `execution_policy` appears as an empty mapping while execution
  limits follow at the parent level. The behavioural instructions state the
  same limits, but structural enforcement by Hermes was not verified.
- Test 001 records a pending human review. Generated test evidence and outputs
  are uncommitted and should not be presented as governed publication records.
- Graph MCP executable availability was observed, but effective Graph
  permissions and a live request were not tested.
- Azure MCP was not found in repository configuration, the deployed Hermes
  profile, the service inventory, container executables or running processes.
  Azure CLI was present on the host but absent from the Hermes container. A
  sandboxed `az version` probe attempted to update an Azure session file and was
  blocked by the read-only environment; no conclusion about authentication or
  tenant access is drawn from that result.
- The diagram groups PostgreSQL evidence, assurance state and reporting as a
  platform capability. Only catalogue, import and pilot-review structures are
  implemented at present.

## 15. Planned Evolution

Repository documentation and the diagram support the following evolution:

- separate research, document-assembly and fact-checking responsibilities where
  independent control is beneficial;
- extend PostgreSQL from catalogue and pilot reviews to governed evidence,
  assurance and reporting tables;
- generalise deterministic comparison into configuration, permission, control
  and evidence drift detection, with approved scheduling;
- develop a general human adjudication and publication workflow;
- develop reusable evidence packs, architecture guidance and curated reports;
- introduce authenticated APIs only after governed data and publication states
  are defined; and
- permit selected external model review only behind an explicit processing
  boundary and approval policy.

The repository does not establish delivery dates, production scale or a
commitment to a particular external model provider.

## 16. Assumptions, Limitations and Unverified Claims

- This is a local proof of concept, not evidence of a multi-tenant, highly
  available or disaster-recovered service.
- Runtime observations do not prove historical uptime or future configuration.
- A responding dashboard and running container are operational signals, not an
  end-to-end assurance transaction test.
- LM Studio inference was not observed during this review.
- Graph and Azure tenant access, permissions and read-only enforcement were not
  verified end to end.
- LanceDB ingestion lineage, source freshness and retrieval quality were not
  independently validated.
- Generalised drift detection and scheduling were not observed.
- General approval, adjudication and publication workflows were not observed.
- No customer data processing, production Microsoft tenant access, performance
  testing, threat model, backup restore test or external-model data-flow
  assessment was verified.

## 17. Related Architecture Documents

The following documents are planned; their relative links are reserved but the
files do not yet exist:

- [ControlOps Knowledge and RAG Component Architecture (planned)](02-controlops-knowledge-rag-component-architecture.md)
- [ControlOps Assurance Data Platform Logical Architecture (planned)](03-controlops-assurance-data-platform-logical-architecture.md)
- [ControlOps Assurance Workflow End to End (planned)](04-controlops-assurance-workflow-end-to-end.md)
- [ControlOps Deployment Architecture (planned)](05-controlops-deployment-architecture.md)

Corresponding diagram images already exist for the knowledge/RAG, assurance
data and deployment views. Their existence does not imply that the explanatory
documents or every depicted capability have been implemented.

## 18. Document History

| Version | Date | Description |
| --- | --- | --- |
| 0.1.0 | 16 August 2026 | Draft repository-grounded baseline, reorganised into a partner overview and implementation record and reconciled with the diagram, Git history and read-only runtime observations |
