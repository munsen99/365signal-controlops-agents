# ControlOps Assurance Data Platform — Logical Data Architecture

## Document Control

| Field | Value |
| --- | --- |
| Status | Draft — repository-grounded internal baseline |
| Version | 0.1.0 |
| Last updated | 16 August 2026 |
| Intended audience | ControlOps architects, engineers, data architects, security architects and technical reviewers |
| Diagram filename | `03-ControlOps-Assurance-Data-Platform-Logical-Data-Architecture.png` |
| Repository commit | `c33603808fb70e071ce97c92cd55770036afc80e` |
| Repository working-tree baseline | Dirty — tracked modifications and untracked files were present during review |
| Runtime verification basis | Repository inspection and the read-only observations recorded in documents 01 and 02 on 16 August 2026; direct Docker access was unavailable during this review |
| Diagram revision | Not specified |
| Document owner | 365signal / Jon Bruce |
| Document purpose | Define the logical data architecture, classify current maturity and preserve the boundary between implemented assurance data capability and target-state intent |

## 1. Purpose and Scope

This document describes the logical data architecture of the ControlOps
Assurance Data Platform. It follows the system context in document 01 and the
Knowledge and RAG component in document 02. The current logical data
architecture diagram is the principal structural reference; repository SQL,
import code, agent contracts, templates, test artefacts and the implementation
records in documents 01 and 02 qualify what the diagram depicts.

The design proposition is broader than the implementation. A box or flow in
the diagram is not evidence that a corresponding database object, service or
operational workflow exists. In particular, creating an empty PostgreSQL
schema reserves a namespace; it does not implement that logical capability.

The platform's defining objective is not merely to collect configuration data.
It is to build an evidence-backed assurance model in which observations,
normalised facts, classifications, control evaluations, findings and
conclusions remain distinguishable and traceable. AI may assist research,
interpretation and classification, but source evidence, deterministic rules,
model inference and explicit human judgement must remain separately
identifiable.

## 2. Classification Method and Evidence Basis

This document uses the required maturity terms consistently:

- **Implemented** — direct repository or recorded runtime evidence shows that
  the capability exists and is usable. This does not imply production quality.
- **Partially Implemented** — a meaningful subset exists, but scope,
  integration, automation or operating controls are incomplete.
- **Planned** — repository documentation, reserved structures or the diagram
  establish intended capability, but no substantive implementation was found.
- **Conceptual** — the item is a design direction or principle for which the
  inspected repository establishes no concrete implementation commitment.

The review used:

- the current logical data architecture diagram;
- [document 01](01-controlops-contextual-architecture.md) and
  [document 02](02-controlops-knowledge-rag-component-architecture.md);
- PostgreSQL Compose, migrations `001`–`012`, validation SQL, pilot queries and
  the Graph permission importer under `platform/postgres`;
- the Microsoft technical validator definition, policy, evidence and reporting
  templates, and recorded development runs; and
- the Graph permission pilot implementation record.

The repository was materially dirty. Migrations and validations `010`–`012`,
agent changes, generated test evidence and the architecture documents were
uncommitted at the baseline. Claims involving those assets describe the
inspected working tree, not only the named Git commit. Direct access to the
Docker API was denied in this review. Point-in-time database and LanceDB counts
therefore rely on the read-only runtime observations already reconciled in
documents 01 and 02 rather than a second independent runtime query.

## 3. Architecture Summary

![ControlOps Assurance Data Platform — Logical Data Architecture](diagrams/03-ControlOps-Assurance-Data-Platform-Logical-Data-Architecture.png)

The diagram separates three concerns:

1. **Governed structured state in PostgreSQL.** Raw source payloads,
   catalogue entities, taxonomy, permission classifications, independent
   reviews, assurance state and reporting read models belong here.
2. **Semantic knowledge in LanceDB.** Technical documents, control knowledge
   and architecture patterns can ground research and review, but are not the
   assurance record.
3. **Sources and consumers outside the record.** Microsoft Graph, Azure and
   Microsoft 365 observations, control material, agents and analysts supply
   inputs; reporting tools and APIs consume approved views.

The implemented portion is narrower. PostgreSQL contains working `raw`,
`catalogue`, `operations` and `permission_pilot` structures. The `evidence`,
`assurance` and `reporting` schemas are empty. The implemented vertical slice
catalogues Microsoft Graph permission definitions and supports controlled,
independent classification review of a selected sample. It does not yet
persist a general chain from a customer observation to a control verdict and
assurance conclusion.

The logical target can be expressed as:

```text
Collect -> Preserve -> Normalise -> Enrich -> Classify
        -> Validate -> Evaluate -> Report
```

Today, the permission catalogue implements parts of Preserve, Normalise and
Enrich; the permission pilot implements a bounded Classify and Review path;
validator files demonstrate a separate evidence-assistance workflow. Validate,
Evaluate and Report are not integrated as a governed end-to-end data flow.

## 4. Information Classes and Assurance Semantics

ControlOps needs an explicit information-class boundary because similarly
shaped statements can have very different authority.

| Information class | Meaning | Example | Required treatment |
| --- | --- | --- | --- |
| Authoritative external knowledge | A vendor, standards body or framework states how a product or control is defined | Microsoft Learn documentation; NCSC CAF text | Preserve source, version, authority and retrieval context; do not treat it as a tenant observation |
| Tenant or environment observation | A collector or analyst observed a value in a scoped environment at a time | A grant, policy setting or Azure resource property | Retain tenant, source system, collection method, timestamp and raw representation |
| Analyst judgement | A named reviewer interprets facts or makes a risk or assurance decision | A permission is judged `critical`; evidence is sufficient | Retain reviewer, rationale, review state and time; do not silently replace it with model output |
| Derived assurance data | A repeatable transform, rule, comparison or controlled decision produces a new record | Current/retired catalogue state; a rule-derived capability; an approved finding | Retain derivation method, inputs, rule/model version, confidence where relevant and approval status |

The diagram's “Control sources” straddles two distinct concepts. Framework
content is external knowledge. A mapping between a framework control and a
ControlOps technical control is governed structured data. An evaluation of a
tenant observation against that control is assurance data. These must not be
collapsed into one generic control record.

## 5. Source and Evidence Layer

### 5.1 Intended source classes

The architecture should accommodate:

- Microsoft Graph catalogue material and tenant observations;
- Azure and Microsoft 365 configuration and operational state;
- security telemetry and test results;
- manually supplied evidence and supporting artefacts;
- architecture documents and approved technical standards;
- authoritative Microsoft documentation;
- NCSC CAF, CIS Controls, NIST SP 800-53, Cloud Controls Matrix and other
  framework material;
- assessment results and previous approved assurance state; and
- controlled external evidence sources.

These are not equally implemented. The Graph importer processes an exported
Microsoft Graph service-principal definition into a permission catalogue. It
does not collect customer grants, tenant configuration or security telemetry.
The validator has evidence templates and development run artefacts based on
authoritative Microsoft sources. Document 02 records populated semantic
collections, including NCSC CAF 4.0 and Microsoft technical material. No
general Azure/Microsoft 365 evidence collector or authenticated customer
observation pipeline was found.

### 5.2 Evidence as a first-class object

Evidence is not a prose footnote to a finding. A production evidence object
needs, where applicable:

- a stable evidence identifier and scoped tenant/customer identifier;
- source system, source object and source URI or immutable artefact reference;
- observation and retrieval times, distinct from processing time;
- collection method, collector identity/version and execution identifier;
- the observed payload or a content-addressed reference and hash;
- validation state, validation method and any collection error;
- relationships to normalised facts, controls and findings; and
- retention, sensitivity, access and human-review metadata.

The validator's YAML template implements part of this concept for documentary
evidence: stable source IDs, claim relationships, exact URLs, retrieval time,
publisher, section, excerpts, summaries, authority, currency, ambiguity,
retrieval status and citation/human-review flags. Recorded runs demonstrate
use, but these remain filesystem artefacts and are not persisted in the empty
PostgreSQL `evidence` schema. They are therefore **Partially Implemented** as an
evidence model, not a governed evidence store.

The target trace is:

```text
Source
  -> Observation
  -> Normalised Fact
  -> Classification
  -> Control Evaluation
  -> Finding
  -> Assurance Conclusion
```

Each arrow should be an explicit, queryable relationship with the producing
process and version. The repository demonstrates portions of Source → raw
snapshot → normalised permission definition and separate classification
reviews. It does not demonstrate this complete chain or automated propagation
through control evaluation, finding and conclusion.

## 6. Raw and Landing Data

Raw retention allows ControlOps to reconstruct what was received before
normalisation or interpretation. It supports dispute resolution, importer
debugging, reprocessing after taxonomy or rules change, and proof that a later
classification was based on a particular source representation.

The implemented `raw.catalogue_snapshot` table stores the import-run foreign
key, source URI, retrieval time, optional HTTP status and headers, JSON payload,
payload hash and creation time. The Graph importer computes a canonical SHA-256
hash, writes the complete imported payload once per run, and associates it with
`operations.catalogue_import_run`. This is a useful raw-preservation pattern.

Its limits are material:

- it handles one catalogue import shape, not general tenant evidence;
- the importer reads a supplied JSON file, so collection from Graph and
  authentication are outside the implemented transaction;
- append-or-immutable enforcement is not present in database permissions or
  triggers;
- tenant/customer identity, data classification, retention and legal hold are
  absent; and
- payload-to-individual-normalised-record lineage is inferable through the run
  and stored raw payload, but no direct snapshot-record junction is defined.

The raw layer is therefore **Implemented** for Graph permission catalogue
snapshots and **Planned** as a general assurance landing layer.

## 7. Catalogue and Normalised Data

### 7.1 Implemented catalogue model

The current relational catalogue is deliberately small:

- `catalogue.source_system` identifies a source, vendor and platform;
- `catalogue.interface` identifies a versioned interface, base URI,
  authentication type and prospective collector adapter;
- `catalogue.permission_definition` stores stable internal IDs, external IDs,
  permission name/type, Microsoft description, inferred `access_class`, admin
  consent metadata, current/valid-time state, source hash and the source item;
- `catalogue.controlops_pillar` and `catalogue.controlops_domain` implement six
  pillars and 34 domains; and
- permission classification and domain mapping tables define constrained
  assurance attributes and taxonomy relationships.

The importer uses source hashes and `valid_from`, `valid_to`, `is_current` to
preserve changed versions and retire definitions absent from a later import.
Unchanged records are retained without a new version. Migrations and validation
SQL are transactional and designed to be repeatable. Document 01 records 1,562
current permission definitions at the verification date.

### 7.2 Limits of the normalised model

The diagram describes permissions, resources and workloads, controls and
assertions, and stable identifiers. Only permission definitions and the
ControlOps pillar/domain taxonomy have concrete tables. Workload is sometimes
derived from naming for pilot sampling but has no authoritative catalogue
entity. No general tenant, identity, service, resource, configuration,
relationship, technical control or assertion entity was found.

The present model is therefore a credible permission-catalogue slice, not a
canonical Microsoft cloud entity model. Extending `permission_definition` or
JSONB fields to stand in for all future resource types would erase important
identity, temporal and relationship semantics. New entities should be added
only through demonstrated use cases and stable source identifiers.

## 8. Taxonomy, Classification and Governed Review

### 8.1 Taxonomy

The implemented taxonomy contains six assurance pillars and 34 domains with
codes, descriptions, display ordering, active state and relational constraints.
Domain-to-pillar integrity and uniqueness are database-enforced and covered by
validation SQL. This is **Implemented** for the permission pilot. It is not yet
proven as a complete taxonomy for all assurance subjects or frameworks.

### 8.2 Permission classification

`catalogue.permission_classification` defines these dimensions:

- access level and capability;
- administrative capability;
- privilege level;
- data sensitivity;
- destructive potential;
- tenant-wide impact;
- consent sensitivity;
- classification confidence and source;
- review status and analyst notes; and
- primary or secondary domain mapping with rationale.

Controlled values and the single-primary-domain rule are enforced in SQL.
However, the pilot intentionally does not publish into this table. Its
validation confirms that the production classification tables remain
unchanged. The table is an implemented schema contract but not evidence of a
populated governed permission-classification product.

### 8.3 Independent reviews and adjudication

The `permission_pilot` schema provides a stronger experimental review model:
stable pilot definition and sample, analyst and `codex` reviews, review rounds,
separate domain assignments, field-level comparison, disagreement records,
domain review, schema-gap capture and proposed—not executable—classification
rules. Migrations record 36 independent AI reviews, eight submitted analyst
reviews and 28 machine-seeded analyst drafts. Human corrections update eight
submitted analyst records across migrations `011` and `012`. The draft rows
must not be described as human decisions merely because their
`reviewer_kind` is `analyst`; they were copied from model reviews for later
analyst action.

The schema can represent disagreements and resolutions, but no disagreement or
domain-review rows were created in the inspected baseline. There is no general
workflow identity, approval, publication or segregation-of-duties service.
Independent review is **Partially Implemented**; general adjudication and
governed publication are **Planned**.

## 9. Fact, Classification, Judgement and Conclusion

The logical model must not use one generic “result” type. ControlOps should
preserve the following distinctions:

| Type | Definition | Typical producer | Example in current assets |
| --- | --- | --- | --- |
| Observed fact | A value read from a source without interpretive transformation | Collector or analyst | A permission definition contains a name and Microsoft description |
| Derived fact | A reproducible transform over observations | Importer or deterministic function | Source hash; current/retired state; name-derived `access_class` |
| Rule-based classification | A controlled rule assigns a category and can be replayed | Versioned rules engine | Candidate sampling labels suggest patterns, but are explicitly not persisted classifications |
| Analyst judgement | An accountable human interprets evidence under stated criteria | Named analyst | Submitted permission review and its rationale/corrections |
| Assurance conclusion | An approved statement about control effectiveness, risk or assurance status | Authorised assurance workflow | No general governed implementation found |

An LLM proposal is none of these merely by virtue of being plausible. It is a
model-generated proposal with model, prompt, context and execution provenance.
If accepted by a human, the human decision must be a distinct record linked to
the proposal, not a relabelling or silent overwrite of it.

Not all assurance conclusions are deterministic. Permission name and
description can support repeatable facts; effective scope may depend on grants,
assignments, signed-in-user privilege or resource installation. Risk,
materiality, evidence sufficiency and compensating controls commonly require
context and accountable judgement. Confidence should describe uncertainty and
review sufficiency, not manufacture evidential weight.

## 10. Control and Framework Mapping

Four separate capabilities are required:

1. **Store framework content.** Preserve the wording, hierarchy, version and
   source of a framework.
2. **Map controls.** Relate a ControlOps technical control or test to one or
   more framework controls with scope, rationale, mapping type and version.
3. **Evaluate evidence.** Apply explicit criteria to evidence and normalised
   facts for a scoped tenant, time and control implementation.
4. **Produce an assurance verdict.** Combine evaluation results, exceptions,
   confidence and human approval into a publishable conclusion.

Document 02 records 82 NCSC CAF 4.0 semantic records in LanceDB. That is
**Implemented** framework-content retrieval at proof-of-concept scope; it is
not a relational control register, mapping or evaluation engine. The
`REGULATORY_FRAMEWORK_MANAGEMENT` domain and diagram references establish
architectural intent. No relational assets for CIS Controls, NIST SP 800-53,
Cloud Controls Matrix, Microsoft-specific controls or customer-defined control
overlays were found. No control-evaluation engine or governed assurance verdict
store was found.

Framework storage is therefore **Partially Implemented** across the knowledge
platform; framework mapping and evidence evaluation are **Planned**; a general
cross-framework assurance model remains **Conceptual** until its semantics and
ownership are approved.

## 11. Knowledge and RAG Relationship

A precise separation is:

```text
Knowledge platform
= sources and retrievable material that help ControlOps understand products,
  standards, controls and architecture.

Assurance data platform
= governed records of what was observed, how it was normalised and classified,
  what was evaluated, who reviewed it and what was concluded for a defined scope.
```

Source documents remain the inspectable authority. LanceDB stores retrieval-
oriented chunks, embeddings and metadata so agents and analysts can find
relevant material. PostgreSQL stores structured identities, facts,
relationships, reviews and assurance lifecycle state. A retrieved passage can
support interpretation or be linked as documentary evidence, but vector
similarity does not establish that the passage is authoritative, current or
sufficient for a conclusion.

Document 02 confirms populated LanceDB tables and experimental retrieval. It
also identifies heterogeneous schemas, incomplete embedding lineage and no
governed path from a RAG response to PostgreSQL. The dashed diagram flow from
semantic knowledge to governed assurance state is therefore support for
reasoning, not a direct data-authority transfer. LanceDB is correctly labelled
“Not the assurance record.”

Vector search must not replace exact relational lookup for tenant IDs,
permission IDs, control IDs, approval state, timestamps or evidence lineage.
Conversely, PostgreSQL need not reproduce large document bodies solely to
perform semantic retrieval; it should retain stable references and any
governed source/citation metadata necessary to reopen the evidence.

## 12. PostgreSQL Role and Schema Inventory

PostgreSQL currently acts as the structured assurance-data system of record by
architectural convention and by the working permission pilot. It provides
foreign keys, uniqueness, controlled values, transactional migrations,
idempotent loaders, durable review rows, temporal catalogue fields and
SQL-based validation and comparison. These properties are appropriate for
auditable assurance state.

| Schema | Implemented contents | Architectural purpose | Classification |
| --- | --- | --- | --- |
| `raw` | `catalogue_snapshot` | Preserve imported source payload, hash and retrieval context | Implemented for Graph catalogue only |
| `catalogue` | source systems, interfaces, permission definitions, pillars, domains, permission classification and domain mapping | Stable normalised entities and controlled taxonomy | Partially Implemented |
| `operations` | `catalogue_import_run` | Import execution, status, counts, versions, hash and errors | Implemented for Graph catalogue import |
| `permission_pilot` | pilot sample, independent reviews, domain assignments, comparisons, disagreement/adjudication structures, schema gaps and candidate rules | Isolate experimental permission-classification and review work from governed classifications | Partially Implemented |
| `evidence` | No tables | Governed observations, provenance, artefacts and evidence relationships | Planned |
| `assurance` | No tables | Controls, evaluations, findings, decisions, exceptions and approved state | Planned |
| `reporting` | No tables or views | Stable consumer read models and publication-safe views | Planned |

There is no separate `taxonomy` schema; pillars, domains and classification
structures are currently in `catalogue`. There is no general production review
schema; review structures are pilot-specific. The diagram's “Taxonomy”,
“Independent Reviews” and “Governed Assurance State” are logical groupings,
not one-to-one reflections of implemented schemas.

PostgreSQL also has limitations as presently deployed: no tenant key or row-
level security design, no migration ledger beyond ordered init scripts, no
role/grant model in the inspected SQL, no backup/restore evidence, and no
service or API boundary. PostgreSQL is a sensible current technology choice,
but the repository does not establish it as an irrevocable production product
decision.

## 13. Processing and Derivation Controls

The target stages should have explicit authority and provenance:

| Stage | Primary mode | Required record |
| --- | --- | --- |
| Collect | Deterministic connector or controlled manual intake | Scope, source, collector, time, raw result and errors |
| Preserve | Deterministic, append-oriented write | Hash, immutable/versioned payload and import/run identity |
| Normalise | Versioned deterministic transformation | Input references, transform version, entity identifiers and validation outcome |
| Enrich | Rules, exact lookups and bounded knowledge retrieval | Enrichment source and method; no silent change to the observation |
| Classify | Deterministic rules where justified; model/analyst proposals otherwise | Rule/model/analyst identity, rationale, confidence and status |
| Validate | Automated constraints plus independent review | Checks performed, exceptions, reviewer and result |
| Evaluate | Versioned control criteria plus contextual judgement | Control version, facts/evidence used, result and limitations |
| Report | Deterministic approved read model and controlled document assembly | Publication state, source record versions and approval |

The Graph import is deterministic except for the deliberately simple
name-based `access_class` inference. The pilot selection query uses stable,
name-derived sampling labels and expressly states that they are not
classifications. SQL constraints and validation scripts check invariants and
idempotency. Independent AI reviews are model-assisted judgements; analyst
submissions and corrections are separately identifiable. No production rules
engine, model registry, evaluation engine or report read model exists.

LLM assistance should always retain model identifier, version if available,
prompt/instruction version, retrieved context identifiers, run time, proposed
values and uncertainty. A later analyst decision should refer to that proposal
and preserve the prior record. The current pilot separates reviewer rows but
does not record model, prompt or retrieval provenance; this is a material gap.

## 14. Agent Interaction with the Data Platform

The intended interaction contract is role-based:

- collection agents create observations and import-run records; they do not
  edit classifications or conclusions;
- validation agents check facts and source support and create reviewable
  validation outputs;
- classification agents propose classifications with model/rule provenance;
- analysts confirm, reject, amend or adjudicate judgement-led proposals;
- control-evaluation agents apply approved versioned criteria and flag cases
  requiring judgement; and
- reporting agents consume approved, publication-eligible read models and do
  not query draft or raw records indiscriminately.

Agents must not silently overwrite raw evidence, authoritative source content,
submitted human reviews or approved conclusions. Corrections should create a
new version, decision or explicit supersession relationship, with actor and
rationale.

Only the Microsoft technical validator is defined in the repository. It is a
development agent that produces structured YAML evidence and Markdown reports,
requires a fact-check pass and human review, denies customer data and
production access, and does not persist to PostgreSQL. The Graph importer is a
script, not an autonomous collection agent. Separate collection,
classification, adjudication and reporting agents are **Planned** where shown
by the wider architecture; their detailed write contracts are **Conceptual**.

## 15. Reporting and Consumption

Potential consumers include ControlOps validation and assessment reports,
evidence packs, architecture assessments, dashboards, Power BI or an
equivalent visualisation layer, customer/partner collateral, APIs and bounded
agent reasoning context.

Operational records and presentation views must be separated. Raw payloads,
draft reviews, internal rationales, collector errors and unresolved
disagreements are operational state. Reporting models should expose only the
approved dimensions and history appropriate to a consumer, while retaining a
stable route to underlying evidence for authorised reviewers. A report should
record the assurance-state version or effective time from which it was built.

The validator demonstrates development Markdown reports and filesystem
evidence records. The pilot provides review export and comparison views, not
customer reporting views. The `reporting` schema is empty. No Power BI model,
general assurance API, evidence-pack generator or publication-state service
was found. These capabilities are **Planned**; broad customer/partner
collateral generation is **Conceptual** until disclosure and approval controls
are defined.

## 16. Data Governance Principles

Assurance data can affect risk acceptance, audit findings and customer trust.
Its governance requirements are therefore part of the correctness model, not
post-production administration.

- **Provenance and lineage.** Every material conclusion must identify its
  source observations, transformations, rules, reviewers and control version.
- **Evidence preservation.** Raw evidence should be append-oriented or
  immutable by policy. Corrections should supersede rather than erase.
- **Repeatability.** Deterministic transforms and control tests must be
  rerunnable against preserved inputs and versioned taxonomies.
- **Versioning.** Source definitions, entities, taxonomies, rules, models,
  mappings, evidence and conclusions need appropriate valid/effective time.
- **Confidence.** Confidence belongs to a specific proposal or judgement. It
  is not evidence and must not hide missing or contradictory sources.
- **Review ownership.** Human decisions require attributable identity, role,
  time, rationale and a controlled status transition.
- **Separation of observation and interpretation.** Derived values must not
  overwrite observations. Model output must not masquerade as a collected fact.
- **Retention and disposal.** Policy must reflect contractual, regulatory,
  evidential and minimisation requirements, including source artefacts and
  derived copies.
- **Auditability.** Changes to approved state, mappings, exceptions and
  publication status require tamper-evident history and reviewable access logs.
- **Least privilege and sensitivity.** Customer configuration, identity,
  security telemetry and evidence may reveal attack paths; collection and
  consumption must be scoped to purpose.
- **Tenant isolation.** Shared knowledge may be reusable; private observations,
  evidence, mappings, exceptions and conclusions must remain inside the
  authorised customer boundary.

Current hashes, valid-time fields, import runs, constraints and separate pilot
review records implement useful fragments. They do not constitute complete
governance. Database access policy, retention, audit logging, legal hold,
backup restoration and approved-state history were not found.

## 17. Tenant and Customer Isolation

No tenant/customer entity, tenant foreign key, row-level security policy,
customer-specific database/schema allocation or application authorisation
boundary appears in the inspected PostgreSQL SQL. The validator explicitly
disallows customer data. The current implementation must therefore not be
described as multi-tenant or suitable for storing customer evidence.

A production design must decide and test:

- stable customer, tenant and source-system identifiers, including one
  customer with several tenants or subscriptions;
- whether isolation is database-, schema-, partition- or row-based, and the
  operational consequences of that choice;
- enforced query and write boundaries for humans, agents, APIs and reporting;
- customer-specific encryption, retention, export and deletion requirements;
- customer-specific evidence and control overlays without contaminating the
  shared taxonomy; and
- explicit separation of shared public/approved knowledge from private tenant
  observations and conclusions.

Adding a nullable `tenant_id` to future tables would not by itself provide
isolation. The key must participate in uniqueness and relationships where
necessary, and access must be enforced below prompt or agent-instruction level.
Tenant isolation is **Planned** as a production requirement; its mechanism is
currently **Conceptual**.

## 18. Current-State Maturity Matrix

| Capability | Current State | Classification | Evidence / Notes | Target Direction |
| --- | --- | --- | --- | --- |
| Microsoft Graph source catalogue import | File-based Graph service-principal export is validated, flattened and transactionally loaded | Implemented | Importer, raw snapshot, import run and versioned permission definitions | Authenticated, least-privilege collection with explicit source-run contract |
| Azure/Microsoft 365 tenant configuration collection | No general collector or verified end-to-end tenant read | Planned | Diagram and broader context only; Azure MCP was not verified | Scoped connectors producing tenant-bound observations |
| Security telemetry and external evidence intake | No governed intake found | Conceptual | Source class is architecturally relevant but not concretely committed in inspected assets | Approve source classes and collection/retention contracts per use case |
| Manual evidence and documentary validation | YAML evidence templates and development run artefacts exist | Partially Implemented | Rich source metadata, but filesystem-only and human review often pending | Persist governed evidence objects and artefact references |
| Raw source preservation | Full Graph catalogue payload and hash retained per import | Partially Implemented | Strong narrow pattern; no general assurance landing model or immutability control | General append-oriented observation/evidence landing contract |
| Import operations and lineage | Import run captures source/interface, versions, counts, status, hash and errors | Implemented | Limited to catalogue importer | General collection-run and transformation lineage |
| Resource/entity catalogue | Permission definitions, source systems and interfaces only | Partially Implemented | No tenants, identities, services, resources, workloads or relationships | Use-case-led canonical entity and relationship model |
| Temporal catalogue state | Changed permission versions and retirements supported | Implemented | `valid_from`, `valid_to`, `is_current`, source hash | Bitemporal/effective-time policy where assurance history requires it |
| Assurance pillars and domains | Six pillars and 34 constrained domains | Implemented | Seed and validation SQL | Governed taxonomy lifecycle and impact analysis |
| General control and assertion catalogue | No relational entities found | Planned | Diagram names controls/assertions | Versioned technical controls, criteria and assertions |
| Permission classification schema | Controlled dimensions and mappings exist; production tables intentionally unpopulated | Partially Implemented | Schema contract proven, publication path absent | Approved classification state with version/history |
| Independent permission reviews | 36 AI reviews, eight human submissions and 28 model-seeded analyst drafts | Partially Implemented | Pilot-specific; drafts are not human decisions | General review identity, assignment, status and provenance |
| Disagreement and adjudication | Tables and comparison/export views exist; no recorded disagreements/resolutions | Partially Implemented | Representational capability without demonstrated workflow | Controlled adjudication and segregation of duties |
| Candidate rules/rules engine | Candidate-rule table exists; no executable engine or accepted rules | Planned | Sampling heuristics are not governed classifications | Versioned deterministic rules, testing, exceptions and replay |
| Governed evidence store | Empty `evidence` schema | Planned | Filesystem templates do not make a database evidence store | First-class evidence, artefacts, provenance and links |
| Control/framework content | NCSC CAF records exist in semantic store | Partially Implemented | Retrieval content only; no relational control register | Versioned framework registry plus source-document links |
| Framework/control mapping | No mapping tables or workflow | Planned | Taxonomy domain indicates intent only | Many-to-many versioned mappings with rationale and scope |
| Control evaluation | No evaluation engine or records | Planned | Must not be inferred from classification pilot | Deterministic criteria plus reviewable contextual evaluation |
| Findings and assurance conclusions | Empty `assurance` schema | Planned | Validator verdict files are development outputs | Governed findings, exceptions, decisions and approved conclusions |
| Semantic knowledge retrieval | Populated LanceDB and experimental query paths | Partially Implemented | Separate component; retrieval quality and citations incomplete | Governed hand-off of resolvable sources to evidence/review |
| Reporting views/read models | Empty `reporting` schema; pilot operational views only | Planned | No assurance-facing read model | Versioned, publication-safe relational views |
| Power BI/API consumers | No implementation found | Planned | Explicitly marked Future in diagram | Authenticated consumers over approved read models |
| Multi-tenant isolation | No implemented tenant model or access enforcement | Planned | Current validator disallows customer data | Tested isolation, authorisation and customer lifecycle |
| General end-to-end lineage | Only source-to-catalogue and review fragments exist | Partially Implemented | No complete observation-to-conclusion chain | Queryable lineage across every assurance transition |
| Agent write/governance contract | Validator boundaries exist; no data-platform API or role-specific writes | Partially Implemented | Validator does not persist to PostgreSQL | Authenticated commands, optimistic controls and append/supersede semantics |

## 19. Architectural Strengths

The strongest aspects of the direction are:

1. **Correct separation of semantic knowledge and governed state.** The
   diagram and document 02 consistently keep LanceDB outside the assurance
   record.
2. **A tangible preservation and versioning pattern.** Raw Graph payloads,
   hashes, import runs, versioned definitions and retirement state give the
   platform a real reprocessing foundation, albeit for one source type.
3. **Relationally enforced taxonomy and review vocabularies.** Foreign keys,
   check constraints, uniqueness and repeatable validation reduce accidental
   taxonomy drift.
4. **Independent-review intent is represented in data.** Analyst and model
   reviews are separate rows, draft model-seeded analyst records are not
   silently promoted, and disagreements have explicit structures.
5. **Experimental work is isolated from governed classification tables.** The
   permission pilot does not publish automatically into the production-named
   classification tables.
6. **The design is compatible with repeatable assurance.** Stable identifiers,
   source hashes, valid time, rationales and review status are a more credible
   foundation than one-off assessment documents alone.

These strengths are architectural foundations, not proof of a complete
assurance platform.

## 20. Architectural Gaps and Risks

The material gaps, ranked by their effect on credible assurance, are:

1. **No first-class governed evidence and lineage model.** The empty
   `evidence` schema leaves the central source-to-conclusion chain unavailable.
   Filesystem YAML is useful but cannot support general relational traceability,
   controlled lifecycle or tenant access.
2. **No control evaluation, finding or assurance-state model.** The empty
   `assurance` schema means ControlOps can classify a pilot sample but cannot
   yet represent a repeatable evaluation and approved assurance conclusion.
3. **No tenant/customer isolation architecture.** Storing customer evidence
   without enforced scope and access boundaries would create unacceptable
   confidentiality and cross-customer risks.
4. **The canonical entity and temporal model is too narrow.** Permissions are
   well represented, but tenants, identities, resources, services, workloads,
   configurations and their changing relationships are absent. Current valid
   time is not a general observation-time or bitemporal model.
5. **Review and adjudication are pilot-specific and provenance is incomplete.**
   There is no general identity/role model, transition control, publication
   state or model/prompt/context provenance. Empty disagreement tables do not
   demonstrate adjudication.

Additional risks are:

- no executable, versioned rules engine with acceptance tests, exception
  handling and replay semantics;
- no relational framework registry or mapping semantics, despite semantic CAF
  content;
- no reporting model, disclosure boundary or stable API;
- no defined retention, deletion, legal hold, database audit or backup/restore
  regime;
- no general schema-migration lifecycle for already-initialised databases;
- no confidence-calibration method or evidence-sufficiency policy shared across
  classifications and conclusions;
- AI reviews do not retain model, prompt and retrieval provenance, limiting
  reproducibility and later challenge;
- model-seeded analyst drafts could be mistaken for human work if consumers
  ignore review status and creation lineage;
- append/immutability is architectural intent but not database-enforced; and
- the data platform has no authenticated service boundary, making safe agent
  and consumer integration undefined.

## 21. Recommended Next Architectural Steps

### Near term

1. Define the smallest complete assurance spine before expanding taxonomy:
   `tenant/scope`, `collection_run`, `observation`, `normalised_fact`,
   `evidence`, `classification_proposal`, `review_decision`, `control`,
   `control_evaluation`, `finding` and `assurance_conclusion`. Specify stable
   identifiers and exact relationships rather than implementing all source
   types at once.
2. Implement `evidence` around one end-to-end permission use case. Link the raw
   snapshot and normalised permission to the pilot proposal, human decision
   and an explicit test control. Preserve artefacts by hash/reference and prove
   reverse traceability with SQL.
3. Separate proposal, review and approved state. Do not publish pilot rows
   directly into `catalogue.permission_classification` until the approval and
   supersession contract is defined. Add actor type, model/prompt/context or
   rule version, reviewer identity and decision lineage.
4. Decide taxonomy ownership and versioning. Define how changes to pillars,
   domains and classification vocabularies affect historical records and
   reprocessing.
5. Correct the agent configuration structure so execution limits are under the
   intended `execution_policy` mapping, and validate enforcement before agents
   receive data-platform write capability.

### Medium term

1. Build a use-case-led entity model for tenant, source instance, identity,
   workload/resource, configuration item and relationship. Avoid a universal
   JSON entity until query and integrity requirements are understood.
2. Implement a versioned control registry, framework registry and mapping
   model. Prove separately that content can be stored, mappings reviewed,
   evidence evaluated and verdicts approved.
3. Introduce a deterministic rules service or library with rule versions,
   effective dates, input schemas, tests, exceptions and replay. Record rule
   outputs as derived records, never mutations of observations.
4. Implement analyst work queues, comparison and adjudication transitions with
   roles, segregation of duties, optimistic concurrency and complete history.
5. Create reporting read models only after approved-state semantics exist.
   Validate that draft/model-only records cannot leak into customer outputs.
6. Define a narrow authenticated data-platform API for agents. Use commands
   such as append observation, submit proposal and record decision rather than
   granting unrestricted table writes.

### Later / production architecture

1. Select and test a tenant-isolation pattern, encryption boundaries, customer
   export/deletion and customer-specific control overlays before customer data
   is admitted.
2. Establish database roles, audit logging, tamper-evident change history,
   retention/legal hold, backup/restore, disaster recovery and availability
   objectives.
3. Add partitioning and performance design based on measured observation,
   telemetry, evidence and history volumes; do not infer scale requirements
   from the permission pilot.
4. Operationalise source freshness, schema drift, collector health, rule/model
   change impact and re-evaluation scheduling.
5. Introduce Power BI or equivalent reporting and external APIs through
   publication-safe contracts, tenant-aware authorisation and versioned output
   semantics.

## 22. Diagram Consistency and Recommended Diagram Changes

The diagram is directionally consistent with the repository in its separation
of PostgreSQL, LanceDB, sources, reviews and future consumers. Its principal
weakness is that visual containment can make target-state boxes look equally
mature.

Recommended changes for a later diagram revision are:

1. Add a legend or line style for Implemented, Partially Implemented, Planned
   and Conceptual. At minimum, mark Evidence, Governed Assurance State,
   Reporting Views, Power BI and API as target state.
2. Split “Source Systems” into **authoritative knowledge/control sources** and
   **tenant/environment observations**. Architecture documentation and
   standards should feed semantic knowledge or documentary evidence, not look
   equivalent to a tenant configuration observation.
3. Add explicit logical objects for Observation/Fact, Control Evaluation and
   Finding. The present diagram jumps from evidence/reviews to governed
   assurance state and does not show the required trace chain.
4. Show tenant/scope as a cross-cutting partition and access boundary across
   raw, evidence, assurance and reporting. Mark the mechanism as undecided.
5. Clarify that `permission_pilot` is an experimental sidecar and that the
   implemented production-named permission-classification tables are not
   populated by the pilot.
6. Label the LanceDB arrow as **retrieved context/candidate documentary
   support**, not an assurance-state write. This reinforces that retrieval is
   not evidence acceptance.
7. Show rule/model/analyst provenance and approval/supersession between
   classification proposals and governed state. “Agent review” alone does not
   identify the model, prompt, rule or human acceptance boundary.
8. Consider renaming “Catalogue” to “Catalogue and Normalised Entities” and
   marking resources, workloads, controls and assertions as target objects;
   today only the permission subset is implemented.

The diagram should remain logical rather than reproduce every PostgreSQL
schema. Its labels should, however, prevent a reader from interpreting empty
schemas and future consumer boxes as current service capability.

## 23. Architectural Position

**Is the current ControlOps Assurance Data Platform direction fundamentally
sound? Yes, as a foundation—not yet as a complete assurance platform.**

The separation of governed relational state from semantic knowledge is correct.
The Graph catalogue demonstrates useful raw preservation, source hashing,
stable identifiers and versioned normalisation. The taxonomy and permission
pilot demonstrate that controlled vocabularies, independent proposals, human
correction and SQL validation can be represented without automatically
promoting model output into approved state.

The experimental slice stops before the architecture's central promise. There
is no governed general evidence store, observation-to-conclusion lineage,
control evaluation engine, finding/conclusion model, tenant isolation or
reporting boundary. Independent review is pilot-specific, and model provenance
and adjudication are incomplete. These are structural gaps, not missing polish.

The sensible next move is to complete one narrow, tenant-scoped assurance chain
with explicit evidence, deterministic derivation, human decision and approved
conclusion before broadening ingestion or adding frameworks. If that boundary
is preserved, the existing PostgreSQL and LanceDB choices provide a credible
prototype foundation while leaving later production technology decisions open.

## 24. Related Architecture Documents

- [ControlOps Assurance Intelligence — Contextual Architecture](01-controlops-contextual-architecture.md)
- [ControlOps Knowledge and RAG — Component Architecture](02-controlops-knowledge-rag-component-architecture.md)
- [Current logical data architecture diagram](diagrams/03-ControlOps-Assurance-Data-Platform-Logical-Data-Architecture.png)

## 25. Document History

| Version | Date | Description |
| --- | --- | --- |
| 0.1.0 | 16 August 2026 | Initial repository-grounded logical data architecture and maturity assessment |
