# ControlOps End-to-End Assurance Process and Reality Assessment

Independent assessment of the intended assurance lifecycle against what
actually connects today.

A working component is not an end-to-end process. This review scores
**connections**, identifiers and operator seams, not isolated table or
script quality.

---

## Document Control

| Field | Value |
| --- | --- |
| Status | Draft — independent repository- and runtime-grounded process assessment |
| Version | 0.1.0 |
| Assessment date | 16 August 2026 |
| Intended audience | ControlOps architects, engineers, security architects and technical reviewers |
| Principal diagram | `docs/architecture/diagrams/04-ControlOps-Assurance-Workflow-End-to-End-Process.png` |
| ControlOps commit | `c33603808fb70e071ce97c92cd55770036afc80e` (dirty working tree) |
| Runtime verification | Read-only checks on 16 August 2026 |
| Document owner | 365signal / Jon Bruce |
| Related Codex assessment | [`04-controlops-end-to-end-assurance-process-and-reality-assessment.md`](04-controlops-end-to-end-assurance-process-and-reality-assessment.md) — read after the primary inspection; not modified |

# Part I — Reality Overview

## 1. Purpose and Intended Audience

This document answers:

> If a ControlOps operator starts with a Microsoft assurance question today,
> can the platform execute one governed process from scope through evidence,
> evaluation, human approval, persistence and report — without the operator
> manually stitching unrelated components together?

It is written for people who will ask “so can we run an assessment?” rather
than “do we have interesting parts?”

Previous architecture notes were used only as maps of where to look.
Maturity scores below come from this inspection of connections.

## 2. Executive Summary

**No.** ControlOps cannot run one governed assurance transaction today.

An operator can do useful work. They cannot do it as one process.

What they actually do is operate **two unjoined tracks**, plus optional
side tools:

| Track | How it starts | How it ends | Shared ID with the other track? |
| --- | --- | --- | --- |
| A — Documentary validation | Human writes YAML/Markdown; Hermes runs `controlops-msft-validator` | Markdown/YAML files; human review field stays `Pending` | None |
| B — Graph permission classification | Human runs a Python importer and `psql` migrations | Pilot review rows in PostgreSQL; production classification tables empty | None |
| Side — RAG | Human runs a CLI in a separate venv | Printed answer; not stored as assurance | None |
| Side — Graph MCP / Azure | Host binaries / scripts | Not invoked from Hermes in this review | None |

There is no `assessment_id`, `scope_id`, `decision_id` or `verdict_id`
anywhere in the ControlOps tree. Validator `task_id` / `run_id` do not
appear in PostgreSQL. Pilot `selection_id` / `review_id` do not appear in
validator reports. Hermes is an **agent runtime** for one development
profile, not an assurance orchestrator.

Overall process maturity is **Level 1**. Several components are Level 2.
No capability is Level 3. The overall score is not an average: a real
assurance transaction still requires stages that are Level 0–1
(tenant evidence, governed persistence, mechanical approval, publication,
shared identifiers).

## 3. Architecture Diagram

![ControlOps Assurance Workflow — End-to-End Process](diagrams/04-ControlOps-Assurance-Workflow-End-to-End-Process.png)

The image is
`docs/architecture/diagrams/04-ControlOps-Assurance-Workflow-End-to-End-Process.png`.
The banner “HERMES-ORCHESTRATED WORKFLOW” is **target-state**. Hermes does
not currently sequence steps 1–10.

Quick qualification of the numbered boxes:

| Box | Diagram claim | Reality |
| --- | --- | --- |
| 1 Assurance question | Architect / analyst / workflow | Human writes a file or decides to run SQL |
| 2 Scope and assertions | Tenant, workload, control | Tenant/workload not modelled. Assertions live in YAML or in a SQL sample list |
| 3 Collect evidence | Approved platform tools | Documentary web fetch in the validator. Catalogue file import. No verified tenant collection from Hermes |
| 4 Retrieve knowledge | LanceDB chunks and citations | Not called by Hermes or the validator |
| 5 Evaluate assertions | Verdict, confidence, rationale | Validator files, or pilot review rows — not one evaluator |
| 6 Rule vs judgement | Decision diamond | No executable assurance rule engine (`candidate_classification_rule` = 0 rows) |
| 7A Rule-derived result | Deterministic classification | Representational table only |
| 7B Independent reviews | Agent and analyst separately | Exists **only** in the permission pilot |
| 8 Review and adjudication | Resolve disagreement | Comparison view computes diffs; **0** disagreement rows; no adjudication exercised |
| 9 Persist assurance state | Decision, evidence links, history | `evidence` / `assurance` schemas empty |
| 10 Defensible result | Evidence pack, findings, reporting | Markdown reports; `reporting` empty; publication not mechanical |

The footer principles (human approval, no autonomous publication, audit
history) are **intent**. Approval is a prompt and a form field, not a gate.

## 4. Primary Question, Answered Directly

Starting from “Is this Microsoft claim / permission / control OK?”:

1. The operator chooses a track. Nothing registers an assessment.
2. Scope is prose in a file, or a hard-coded 36-row SQL sample.
3. Evidence is either Microsoft Learn pages fetched by the validator, or a
   **published Graph permission inventory file** — not tenant state.
4. RAG does not run unless the operator starts a different project.
5. Evaluation is either a Markdown verdict or a pilot review INSERT.
6. Human review is required by text; nothing blocks use of an unreviewed
   file. Test 001 is still `Pending`.
7. Nothing is written to `evidence` or `assurance`.
8. There is no published evidence pack regenerable from governed records.

The process **breaks at initiation** (no assessment object) and **again at
every hand-off**. Humans are the integration bus.

# Part II — Lifecycle Inspection

## 5. End-to-End Stage Inventory

Handoff values: **DB** database relation · **file** structured file ·
**SQL** operator-run SQL · **prompt** instructions · **human** manual
transfer · **none**.

| Stage | Intended I/O | What exists | Persisted where | Runtime | Human does | Maturity | Handoff to next |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 Intake | Question in | YAML/MD templates; operator intent | File / operator memory | Editor | Writes the question | L1 | file / human |
| 2 Scope | Tenant, control, exclusions | Not first-class. Task context or SQL sample | File or `permission_pilot` | Editor / psql | Invents scope | L0–1 | none (no scope object) |
| 3 Criteria | Versioned control/test | Claim text; taxonomy domains; CAF in LanceDB | Mixed; not executable criteria | — | Picks what “good” means | L1 | human |
| 4 Collect | Documentary and/or platform | Learn fetch (validator); Graph **catalogue file** import | HTML/YAML files; `raw.catalogue_snapshot` | Hermes web tools; Python importer | Starts the tool; supplies files | L1 (tenant: not evidenced) | none between tracks |
| 5 Preserve raw | Append-only artefact | Catalogue snapshots hashed. Validator saves some source HTML in test dirs | Postgres raw; workspace files | Importer / agent | Organises folders | L2 catalogue / L1 validator | DB within catalogue only |
| 6 Normalise | Observation | Permission definitions. No general observation | `catalogue.permission_definition` | Importer | Runs importer | L2 catalogue only | DB |
| 7 Knowledge | Retrieved guidance | LanceDB + `rag_query.py` | LanceDB; not linked to evals | Manual CLI | Switches project | L2 component / L0 in this process | none |
| 8 Deterministic derive | Rule result | Name `access_class`; CHECKs; empty rule table | Catalogue / empty rules | Importer / SQL | Interprets heuristics | L1 | human |
| 9 Proposal | Model or analyst | Validator report; Codex/analyst reviews | Files; `classification_review` | Hermes / SQL | Invokes agent or loads SQL | L2 within each track | none across tracks |
| 10 Evaluate | Compare to criteria | Agent judgement or review fields | Same | Same | Reads output | L1 | human |
| 11 Human review | Decision | Required in SOUL/templates; Pending on test 001; SQL corrections | Field / in-place UPDATE | Human | Decides, or not | L1 | human / SQL |
| 12 Adjudicate | Resolved disagreement | View computes 32 diffs; 0 persisted | View only | SQL | Has not run this step | Representational | none |
| 13 Verdict | Scoped conclusion | Validator overall verdict; no DB verdict | Markdown | Agent | Accepts file or ignores | L1 | none |
| 14 Finding / risk | First-class finding | Templates only | — | — | — | L0 | — |
| 15 Assurance state | Governed record | Empty `assurance` / `evidence` | — | — | — | L0 | — |
| 16 Report | Regenerable pack | Markdown generation | Workspace files (mostly untracked) | Agent | Copies/files | L1 | human |
| 17 Publish | Approved/published states | Instructional only | — | — | Informal | L0 | — |
| 18 Baseline | Approved state at T | Catalogue versions ≠ assurance baseline | Catalogue hashes | Importer | — | L0 as assurance baseline | — |
| 19 Recollect | Scheduled rerun | Cron denied to validator | — | — | Manual if at all | L0 | — |
| 20 Compare | Drift vs baseline | Second catalogue import was a no-op replay | Import counts | Importer | — | L0 as drift | — |
| 21 Materiality | Is the change assurance-relevant? | Not modelled | — | — | — | L0 | — |
| 22 Reassess | Triggered workflow | Not modelled | — | — | — | L0 | — |

## 6. Initiation and Scope

How work starts today:

- **Validator:** create `task.yaml` or a Markdown brief. Example:
  `task_id: validate-entra-connect-001`. Fields: title, submitter, claim,
  required sources, `human_review_required`.
- **Pilot:** run migrations against a hard-coded pilot code
  `MSGRAPH_PERMISSION_CLASSIFICATION_FINAL_36`.
- **RAG:** type a question into `rag_query.py`.
- **Ops:** `bash scripts/controlops start` starts containers, not an
  assessment.

There is no first-class assessment, customer, tenant, environment, workload,
control register or expected-outcome object in PostgreSQL. A repository-wide
search found **no** `assessment_id`, `scope_id`, `verdict_id`,
`decision_id` or `collection_id`.

`agent.yaml` says `task_id` identifies the work request and `run_id` the
execution attempt. Those IDs stay inside validator artefacts. They do not
span the platform.

## 7. Control and Requirement Ingestion

| Source | What it is today | Executable ControlOps criterion? |
| --- | --- | --- |
| Microsoft Learn | Fetched pages; Learn **catalogue** in LanceDB | No — documentary support |
| NCSC CAF | 82 LanceDB rows | No — framework content |
| CIS / NIST / CCM | XML or absent | No |
| Architecture patterns | 77 draft LLD chunks in LanceDB | No |
| Validator assertion | Claim sentence in YAML/MD | One-off test, not a register |
| Taxonomy domain | 34 assignment labels | No — a domain is not a control |
| Candidate classification rules | Empty table | No |

No versioned control/test-criteria register exists. “Versioned criteria”
closest cousins are catalogue `source_hash` and CAF content in LanceDB —
neither is an executable ControlOps control.

## 8. Evidence Collection

### Documentary / supporting knowledge — experimental, demonstrated

The validator can search and extract Microsoft Learn. Test 001 and 002
record URLs, excerpts and 404s. That is documentary support for a technical
claim, not tenant observation.

### Platform observations — not evidenced from Hermes

- **Graph catalogue importer:** reads a **file export** of the Microsoft
  Graph service principal. It is Microsoft’s published permission inventory.
  It is **not tenant evidence**.
- **Graph MCP:** host executable exists; **not visible inside the Hermes
  container**; no Graph process running; no live request tested.
- **Azure:** host `az` present; absent from Hermes; Azure inventory script
  lives in the RAG tree and is not part of this workflow; no Azure MCP.
- **Telemetry / tenant test harness:** not found as a ControlOps collector.

No verified tenant-scoped read-only collection runs end to end from Hermes.

## 9. Knowledge / RAG in This Process

RAG does **not** participate in the current assurance lifecycle unless a
human leaves ControlOps and runs the MultimodalIngest CLI.

- Hermes does not call `rag_query.py` or `rag_server.py`.
- The validator SOUL “retrieval” means fetching Learn pages, not LanceDB.
- `rag_server.py` is not listening.
- Doctor only checks that `/mnt/Storage/AI/RAG/MultimodalIngest` exists.
- Retrieved passages are not persisted as evaluations or written to
  PostgreSQL.

LanceDB is mounted into Hermes (`/opt/data/lancedb`). A mount is not a
workflow step. Historical Windows paths in RAG are **not** an end-to-end
ControlOps failure.

RAG may later *inform* an evaluation. It must not *become* the evidence
record.

## 10. Normalisation and Observation

The only implemented normalisation pattern is:

Graph catalogue JSON → `raw.catalogue_snapshot` →
`catalogue.permission_definition`.

That pattern has **not** been generalised to tenant observations. There is
no observation, evidence item, transformation or scope table. Validator
“evidence records” are YAML files.

## 11. Deterministic Evaluation

| Mechanism | What it is | Assurance rule? |
| --- | --- | --- |
| Importer `access_class` | Name heuristic | No |
| Sampling SQL labels | Stratification aid | No |
| CHECK constraints | Vocabulary enforcement | Integrity, not evaluation |
| Validation SQL | Fingerprints, counts, isolation | Engineering QA, not assurance |
| Validator stop conditions | 2 sources / budget | Process bound, not a control test |
| `candidate_classification_rule` | Empty | No engine |

No versioned, replayable, exception-aware assurance rules engine exists.

Diagram box 6 / 7A is therefore **representational / conceptual**.

## 12. Model and Agent Evaluation

One ControlOps agent is defined and active:
`controlops-msft-validator` (`development`, v0.1.0).

It produces **proposals**: verdicts, confidence, fact/inference labels, a
fact-check pass result, and `human_review_required: true`. It is not an
approval authority. Outputs are workspace files. Committed tests are only
`task.yaml` and `test.md`; generated reports are untracked.

`run_id` and model name appear on reports. Prompt/model digest is not a
platform register. Delegation is disabled. Research / assembly / fact-check
diagram boxes are roles inside this one agent, not deployed agents.

Track B “agents” are external Codex runs loaded by SQL, not Hermes agents.

## 13. Human-Intervention Map

Human involvement is not a defect. Unstructured stitching is.

| Stage | Human currently does | Judgement desirable? | Temporary PoC work? | Future control |
| --- | --- | --- | --- | --- |
| Intake | Writes the question | Yes | File format is temporary | Assessment record |
| Scope | Invents tenant/control in prose | Yes | Lack of scope object is temporary | Scope entity |
| Tool start | Starts LM Studio, Hermes, psql, RAG CLI | No | Yes | Orchestrated job |
| Evidence pick | Chooses URLs, files, sample of 36 | Mixed | Sample selection method can stay human | Collection plan on the assessment |
| State transfer | Copies meaning between files, SQL, chat | No | **Yes — this is the main seam** | Shared IDs / write contracts |
| RAG interpretation | Reads CLI output | Yes | Invocation is temporary | Optional research step on the job |
| Agent output review | Reads Markdown | Yes — remain | Pending field is temporary | Decision object; gate |
| Classification edit | Runs `011`/`012` UPDATEs | Yes | In-place SQL is temporary | Superseding review row |
| Adjudication | Not actually done | Yes — remain | Workflow missing | Persisted disagreement + decision |
| Publish | Informal / not done | Yes — remain | No mechanical gate | Status + role |
| Drift | Not done | Yes later | Entire stage missing | Scheduled job + materiality |

## 14. Independent Review and Disagreement

Applies to **Track B only**. Track A has a single agent and a Pending
reviewer field.

Independently re-queried on 16 August 2026:

- 72 reviews; analyst and Codex in separate rows;
- 28 analyst drafts **content-identical** to `codex_remaining_28`
  (model-seeded; stored as `reviewer_kind='analyst'`);
- 8 submitted analyst rows later **updated in place**;
- `review_comparison` shows 32 field disagreements on those 8;
- `disagreement` = 0; `domain_review` = 0;
- `catalogue.permission_classification` = 0.

Independent proposals exist. Provenance is imperfect. Disagreement is
computed, not persisted. Adjudication and promotion have not been
exercised. Representational capability ≠ operational workflow.

## 15. Verdict and Finding

| Kind | Where | Linked to scope/evidence? | Human-approved? | Versioned? |
| --- | --- | --- | --- | --- |
| Validator overall verdict | Markdown | To claim + cited URLs in the same file | Field = Pending on test 001 | No |
| Pilot review_status | `draft` / `submitted` / `superseded` | To a permission selection | Submitted ≠ published | Round exists; unused for corrections |
| Production classification | Empty table | — | — | 1:1 unique would prevent history |
| Finding / risk / exception / remediation | Not in PostgreSQL | — | — | — |

Do not infer a finding engine from the report template’s headings.

## 16. Persistence and “Where Is Approved Assurance State?”

| Store | Holds | Authoritative for assurance? | History | In lineage? |
| --- | --- | --- | --- | --- |
| Hermes profile/session | Runtime, logs, SOUL copy | No | Session files | No |
| Workspace files | Tests, reports, YAML | No | Git only if committed (mostly not) | Track A only |
| Git | Contracts, SQL, some tests | For definitions | Commit history | Partial |
| LanceDB | Semantic knowledge | No | Table generations | No |
| PostgreSQL catalogue/pilot | Inventory + reviews | For catalogue facts and pilot proposals | Catalogue versions; reviews overwritten | Track B only |
| `evidence` / `assurance` / `reporting` | Nothing | — | — | — |
| Raw Graph JSON file | Import input | Source file | File | Catalogue import |

**There is no general approved assurance state.**

The nearest durable governed facts are: current Graph permission
definitions, the taxonomy, and *unpromoted* pilot reviews. None of those
is an approved scoped assurance conclusion.

## 17. Reporting

Document generation exists (templates + two experimental reports).

Governed reporting does not. `reporting` has no tables or materialised
views. No Power BI assets. No API. A report **cannot** be regenerated
deterministically from persisted assurance records, because those records
do not exist. Regenerating a validator report would mean re-running the
agent, not reading a verdict table.

## 18. Publication

| State | Exists? |
| --- | --- |
| draft | Pilot reviews; validator “in progress” |
| review / pending | Report field; not a workflow state |
| approved | Production CHECK value; unused. Pilot definition status `approved` means the **sample** is approved, not the classifications |
| published | Not implemented |
| superseded | Pilot CHECK; unused for corrections |
| withdrawn | Not implemented |

Publication is **not** mechanically blocked. `publication_requires_human_review: true` is policy text. A file can be emailed without changing any database row.

## 19. Baseline

Versioned catalogue data (`source_hash`, `is_current`, import fingerprints)
can answer “what did Microsoft publish in this file on 2 August 2026?”

It cannot answer:

> What was the approved assurance state of customer X / tenant Y / control Z
> at time T?

That needs scope, approved verdicts and time. Those objects are absent.
Hashes are enabling primitives for a future baseline, not a baseline.

## 20. Drift

No drift engine exists.

Missing: schedule (cron denied), comparable scoped observations, baseline
of approved assurance state, materiality rule, drift event, alert, case,
triggered reassessment.

A second catalogue import that added 0 rows proves the importer is
idempotent. It does not detect assurance-relevant drift. Source JSON
difference ≠ material drift.

Diagram steps after “defensible result” (recollect / compare) are
**Level 0**.

## 21. Orchestration — What Hermes Actually Does

Hermes today:

- runs profile `controlops-msft-validator`;
- exposes a local dashboard (`127.0.0.1:9119`, HTTP 200);
- calls LM Studio for that agent;
- offers file/terminal/web tools inside policy;
- persists sessions and logs under `/mnt/Storage/AI/Hermes/data`.

Hermes does **not** coordinate RAG, Graph/Azure collection, PostgreSQL
writes, human review queues, reporting or multi-step jobs. There is no
workflow/state-machine definition for the numbered diagram.

`scripts/controlops` orchestrates **containers**, not assessments.

Agent runtime ≠ assurance orchestration.

## 22. Workflow State and Identifier Breaks

No single persisted assurance transaction exists.

| ID | Exists | Travels as far as |
| --- | --- | --- |
| `task_id` / `run_id` | Validator files | That run’s folder |
| `agent_id` / `agent_version` | YAML + report header | Same |
| `import_run_id` | PostgreSQL | Snapshot + counts |
| `permission_definition_id` | PostgreSQL | Catalogue / pilot FKs |
| `selection_id` / `review_id` | PostgreSQL | Pilot only |
| `pilot_code` | PostgreSQL | One sample |
| `assessment_id` | **Nowhere** | — |

Lineage breaks between Track A and Track B, between RAG and both, and
between any proposal and a published conclusion.

Minimal future transaction: one `assessment_id` owning scope, collection
run, observation, evaluation, decision, verdict and report ids.

## 23. Operational Governance (Process-Relevant Only)

Enough for a single-operator laboratory: loopback Postgres, secret file
outside Git, agent denylist, no Docker socket, doctor/smoke checks.

Not enough for a trustworthy customer assurance process: one DB superuser,
no process actor identity, no customer isolation, no mechanical approval
audit, backups that predate later reviews and were not restore-tested, no
environment separation, no release gate on validation SQL.

## 24. Product Language versus Reality

| Phrase | Supported? | Prefer |
| --- | --- | --- |
| Assurance platform | No | Assurance engineering foundation |
| Continuous assurance | No | Intended later evolution |
| Drift detection / drift engine | No | Versioned catalogue primitives |
| Governed evidence | Not as a store | File evidence + hashed catalogue snapshots |
| Autonomous / agentic assurance | Contradicted by design and by fact | Bounded evidence assistant + human decision |
| Operational assurance | No | Workstation proof of concept |
| Production-ready | No | Not for customer production use |

# Part III — Scores and Milestone

## 25. Component versus Workflow Maturity

Levels are not averaged. L2 describes a **component**. Overall L3 requires
one transaction.

| Capability | Level | Why this number |
| --- | ---: | --- |
| Knowledge/RAG | **2** | Live store, Linux search and embeddings work as a component. **Not used** in the assurance path (process participation L0). |
| Evidence collection | **1** | Documentary fetch demonstrated. Catalogue file import is L2 but is **not** tenant evidence. Tenant collection from Hermes not evidenced. |
| Assurance data platform | **2** | Catalogue, taxonomy, import, pilot are repeatable. Evidence/assurance/reporting empty — those workflow stores are L0. |
| Taxonomy/classification | **2** | Constrained taxonomy + reproducible pilot. Not published; not a control register. |
| Microsoft technical validation | **2** | Bounded agent with contracts, templates and two test briefs; rerunnable by an operator in Hermes. Quality/review still experimental. **Not integrated** with governed state (that is an L3 concern). |
| Human review/adjudication | **1** | People can review. No decision object, no gate, no exercised adjudication. |
| Reporting | **1** | Documents can be written. Not generated from governed records. |
| Workflow orchestration | **1** | Hermes runs one agent. Humans connect everything else. |
| Drift detection | **0** | Intent plus hashes. No engine. |
| Operational governance | **1** | Useful local controls. Not an assurance operating model. |

**Overall ControlOps process maturity: Level 1.**

Reason: a governed assurance transaction cannot complete. The weakest
*required* stages (scope object, tenant or even documentary evidence
persistence, decision, verdict store, identifier chain) are L0–L1.

## 26. The Integration Boundary

ControlOps has not crossed from **a kit of useful components** to **one
assurance workflow**.

The precise missing contracts are:

1. **No assessment transaction** — nothing to hang steps on.
2. **No shared identifier chain** — `task_id` never meets `review_id`.
3. **No component write contracts** — validator ↛ Postgres; RAG ↛
   anything; Hermes ↛ Graph MCP (binary not in the container).
4. **No scoped observation** — catalogue facts ≠ tenant/platform
   observations; validator YAML ≠ `evidence`.
5. **No versioned test criterion** — claims and domains are not controls.
6. **No human decision object** — Pending fields and SQL UPDATEs.
7. **No verdict/publication state** that a report can be generated from.

The first of these is the organising gap. The third is the mechanical gap.
Together they keep the platform at Level 1.

## 27. Smallest Material Milestone

Do **not** start with a drift engine, a multi-agent mesh, Power BI, or a
larger corpus.

Implement **one operator-triggered transaction** that is otherwise
integrated:

1. Create `assessment` + `scope` (even “documentary claim” or “catalogue
   permission X” — do not wait for a customer tenant if that blocks the
   milestone).
2. Select one criterion (the claim or one permission test).
3. Collect one artefact (Learn page **or** one Graph/catalogue/tenant read
   if already authorised).
4. Persist raw artefact + normalised observation under the
   `assessment_id`.
5. Produce one evaluation (rule and/or validator proposal) linked to that
   observation.
6. Record a human decision row (approve / reject / qualify).
7. Persist a verdict.
8. Render the report **only** from those rows.

When that path exists, the overall rating can move to **Level 3** for that
slice — even if RAG, Azure and drift remain as they are.

If the first slice uses only documentary Learn evidence, say so on the
scope. Do not pretend it is tenant assurance. A later slice can replace
the collector without redesigning the transaction.

## 28. Closing Assessment

**Current ControlOps state.**  
If development stopped today: a local-first kit — Hermes + one development
validator, a hashed Graph permission catalogue, a taxonomy, an isolated
classification pilot, and a separately usable RAG corpus. Not an
assurance service.

**Current strongest capability.**  
The Graph catalogue import + taxonomy + validation-SQL discipline (Track
B data plane), and the bounded validator contract (Track A agent). Both
are Level 2 components.

**Current weakest link.**  
No assurance transaction / shared ID / write contract. That single
absence forces every other manual seam.

**Current automation level.**  
Islands of automation (import, embed, agent tool loop) inside a manually
assembled lifecycle.

**Current assurance maturity.**  
**Level 1.**

**Hermes assessment.**  
Runtime and dashboard for one validator profile. Not the orchestrator the
diagram names.

**Knowledge/RAG assessment.**  
Usable local knowledge store. Optional, operator-driven, outside the
assurance path. Not governed evidence.

**Data platform assessment.**  
Governed **catalogue and pilot** store. Not a governed evidence or
assurance-state store.

**Human review assessment.**  
Intended and sometimes recorded. Not mechanically enforced. Drafts can be
model-seeded; submitted rows can be overwritten; reports can remain
Pending indefinitely.

**Drift engine assessment.**  
Does not exist. Versioning/hashes are not a drift engine.

**Biggest architectural gap.**  
The missing assessment transaction that would let components exchange
governed records instead of relying on the operator’s working memory.

**Next material milestone.**  
One persisted slice: assessment → observation → evaluation → human
decision → verdict → report-from-state.

**Production readiness.**  
Blocked by: no tenant collection, no customer isolation, no mechanical
approval/publication, no operational identity/SoD, no regenerable
governed report, single-workstation deployment, dirty uncommitted state,
and no completed assurance transaction.

## 29. Comparison with Codex 04

Read after the inspection above.

**Strong agreements.**  
No end-to-end workflow; two manual tracks; Graph catalogue ≠ tenant
evidence; empty evidence/assurance/reporting; RAG not in the loop; no
drift engine; overall **Level 1**; next milestone is one narrow persisted
transaction.

**Maturity-score differences.**  
Codex 04 rates Microsoft technical validation at **Level 1**. This review
rates the **validator component** at **Level 2** (contracts, templates,
two tests, Hermes-rerunnable) and keeps overall process maturity at
Level 1 because integration is the L3 bar. “Operator-led” is expected at
L2; it should not pull a bounded component down to L1.

**Findings Codex 04 understated or this review sharpened.**  
Graph MCP is not merely “untested”: it is **not present in the Hermes
container**. Identifier search found **zero** assessment/scope/verdict
ids in the tree. 28 drafts are content-identical to Codex; 8 submitted
analyst rows were updated in place; 32 comparison disagreements are
unpersisted — process consequences, not only data-model notes.

**Findings not re-litigated.**  
Component internals of RAG and SQL CHECKs were re-checked only at the
seams (mount, doctor, empty schemas, live review counts). Deep RAG/SQL
detail remains in Cursor-02/03.

**Historical/runtime context.**  
Windows RAG paths are not scored as process failures. LM Studio and
Hermes were up (HTTP 200) during this review; that does not raise process
maturity.

**Next milestone.**  
Converges: one identifier-linked transaction. This review explicitly
allows the first slice to be documentary if that is what unblocks L3,
provided the scope says so.

## 30. Related Architecture Documents

| Document | Role |
| --- | --- |
| [Cursor-01 contextual](Cursor-01-controlops-contextual-architecture.md) | System boundary; not rescored here |
| [Cursor-02 RAG](Cursor-02-controlops-knowledge-rag-component-architecture.md) | Knowledge component; process use re-tested |
| [Cursor-03 data platform](Cursor-03-controlops-assurance-data-platform-logical-data-architecture.md) | Data objects; process connections re-tested |
| [Codex 04](04-controlops-end-to-end-assurance-process-and-reality-assessment.md) | Compared after inspection; not modified |

## 31. Document History

| Version | Date | Description |
| --- | --- | --- |
| 0.1.0 | 16 August 2026 | Independent end-to-end process and reality assessment. Focus on seams, identifiers and whether one governed transaction can complete. |
