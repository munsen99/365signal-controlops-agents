# ControlOps Knowledge and RAG — Component Architecture

Independent architecture assessment of the Knowledge and retrieval-augmented
generation (RAG) component.

This document is a repository- and runtime-grounded review. An architecture
diagram, table name, script or README is not proof that the corresponding
capability is currently operational under Linux or integrated with ControlOps.

---

## Document Control

| Field | Value |
| --- | --- |
| Status | Draft — independent repository- and runtime-grounded assessment |
| Version | 0.1.0 |
| Assessment date | 16 August 2026 |
| Intended audience | Security architects, Microsoft specialists, data architects, technical partners, prospective clients and ControlOps engineers |
| Principal diagram | `docs/architecture/diagrams/02-ControlOps-Knowledge-and-RAG-Component-Architecture.png` |
| Diagram revision | Not specified on the image |
| ControlOps repository | `/mnt/Storage/AI/Hermes/workspace` at `c33603808fb70e071ce97c92cd55770036afc80e` (dirty working tree) |
| RAG repository | `/mnt/Storage/AI/RAG/MultimodalIngest` at `ef6a918` (dirty working tree) |
| Live LanceDB store | `/mnt/Storage/AI/VectorDBs/LanceDB` |
| Runtime verification | Read-only inspection and a retrieval smoke search on 16 August 2026 |
| Document owner | 365signal / Jon Bruce |
| Related Codex assessment | [`02-controlops-knowledge-rag-component-architecture.md`](02-controlops-knowledge-rag-component-architecture.md) — inspected for context only; not treated as authoritative and not modified |

# Part I — Partner Architecture Overview

## 1. Purpose and Intended Audience

This document explains the ControlOps Knowledge and RAG component: how
technical knowledge is intended to be ingested, embedded, stored, retrieved
and supplied to a local model, and what of that chain actually exists today.

It is written for technically sophisticated readers. It is not a marketing
description of a production knowledge service.

The assessment separates four things that are easy to collapse:

1. **Historical implementation** — capabilities built and populated while the
   workstation was primarily Windows-based.
2. **Current assets** — code, tables and artefacts that still exist and remain
   usable.
3. **Current Linux operation** — capabilities demonstrated from this Linux
   ControlOps/Hermes environment.
4. **Current ControlOps integration** — capabilities actually connected to
   Hermes or ControlOps agents.

A Windows-era pipeline that produced the live corpus is still evidence that
the capability was built. That is not the same as saying the pipeline is
operationally verified, Linux-reproducible, or called by ControlOps today.

## 2. Executive Summary

The Knowledge and RAG component is a **local, filesystem-backed semantic
knowledge store** with several real ingestion generations and a working
vector-search path. It is **not** a governed assurance record, **not** a live
tenant-evidence collector, and **not** an operational ControlOps service.

What was genuinely built, mostly during the earlier Windows-oriented phase:

- inbox-driven processing of text, Markdown, PDF and architecture-diagram
  images;
- local embeddings through LM Studio (`nomic-embed-text-v1.5`, 768
  dimensions);
- a LanceDB corpus of roughly 22,500 rows across eleven tables;
- a CLI that can embed a question, search selected tables and prompt a local
  chat model;
- FastAPI source for a local RAG HTTP API;
- a structured NCSC CAF 4 ingest and a heading-aware architecture-pattern
  ingest;
- a Microsoft Learn catalogue ingest owned by ControlOps.

What is true on Linux today:

- the live store is at `/mnt/Storage/AI/VectorDBs/LanceDB` and is mounted into
  Hermes;
- `.env` in the RAG project already points at that path;
- LM Studio advertises the expected embedding model and produced a 768-d
  vector during this review;
- a Linux virtualenv can open the tables and return topically related PDF,
  architecture-pattern and Learn-catalogue hits.

What is not true today:

- Hermes and the Microsoft validator do **not** invoke RAG;
- no RAG HTTP process is running, and ControlOps does not expect one;
- citation integrity is prompt-level, not verified;
- retrieval quality has not been acceptance-tested;
- a clean Linux rebuild of the whole corpus has not been demonstrated;
- the Windows diagram/OCR pipeline is not currently runnable as written;
- retrieved passages do not become PostgreSQL assurance state.

The useful partner claim is therefore modest: ControlOps already has a
substantial local knowledge corpus and a demonstrated local retrieval path.
It does not yet have a dependable, agent-callable knowledge service with
consistent provenance and citation control.

## 3. Architecture Diagram

![ControlOps Knowledge and RAG — Component Architecture](diagrams/02-ControlOps-Knowledge-and-RAG-Component-Architecture.png)

The image lives at
`docs/architecture/diagrams/02-ControlOps-Knowledge-and-RAG-Component-Architecture.png`.
No older similarly named file was found in this tree. The diagram is the
principal visual reference. Several boxes describe target behaviour more
strongly than the implementation supports. Those qualifications are recorded
below.

The subtitle on the diagram — “Evidence ingestion, semantic retrieval and
grounded model responses with traceable citations” — uses “evidence” in a
documentary sense. In ControlOps terms that material is **retrieved
knowledge**, not governed assurance evidence.

## 4. Component Boundary and Responsibilities

### In scope

Turning approved or relevant **technical knowledge** into retrievable vectors
and using those passages to constrain a local model:

- Microsoft technical documents and Learn catalogue entries;
- architecture patterns and internal design notes;
- control-framework text (currently NCSC CAF 4);
- architecture-diagram interpretations.

The question this component answers is:

> What authoritative or relevant technical knowledge should the analyst or
> agent consider?

### Out of scope

- **Microsoft Graph / Azure / platform collection.** Those answer “what is
  actually configured in the assessed environment?” Graph MCP and Azure
  tooling belong to the current Linux ControlOps runtime. They are not part
  of the historical RAG subsystem. An Azure inventory script happens to live
  in the RAG repository; that does not make it RAG.
- **Governed assurance state.** PostgreSQL catalogue, taxonomy, reviews and
  (empty) evidence/assurance/reporting schemas are a different store.
- **Hermes orchestration**, except as a consumer that is not yet wired.

Retrieval may inform an assurance question. It does not observe a tenant, and
it does not approve a control.

## 5. How the Component Is Intended to Operate

The intended chain is:

**Source → processing → chunking → metadata → embedding → LanceDB →
query embedding → retrieval → context composition → local model → cited
response → human review.**

The diagram’s retrieval side starts from an “assurance query” issued by an
architect, agent or API. Today the only demonstrated issuer is a human
running a Python CLI against the RAG project.

# Part II — Implementation and Verification Record

## 6. Historical Windows-to-Linux Evolution

The RAG / LanceDB capability was originally developed and populated on a
Windows-oriented workstation. That history is still visible and should be
read as migration residue unless it blocks current operation.

| Artefact | Origin | Current meaning |
| --- | --- | --- |
| Commented `E:\AI\...` paths in `config.py` and README | Windows development | Harmless historical comments |
| Default `LANCEDB_PATH=/run/media/proteu5/Storage/...` | Earlier Linux mount of the same storage | Historical default; **not the live path** |
| RAG `.env` `LANCEDB_PATH=/mnt/Storage/AI/VectorDBs/LanceDB` | Linux normalisation (`1fb88fb`) | **Currently active** for `config.py` consumers |
| `process_inbox.py` `BASE_DIR=E:\ai\rag\...` and Tesseract `C:\Program Files\...` | Windows diagram pipeline | Blocks a clean Linux re-run of that pipeline |
| `embedding_client.py` default `http://192.168.8.174:1234/v1` | Earlier LAN LM Studio | Historical; unused if `.env` / `config.py` path is used |
| RAG `.venv` (`Lib/`, `Scripts/`) and LanceDB `venv_lancedb` (`*.exe`) | Windows Python environments | Not used by the current Linux venvs |
| `multimodal_docs` source_path `E:\AI\RAG\MultimodalIngest\Inbox\test.md` | First smoke ingest | Historical test row |
| `query_rag.py` / `ingest_0365_pdf.py` hard-coded `E:\AI\VectorDBs\LanceDB` | Early general-knowledge pipeline | Legacy scripts beside the live store |
| `m365_general_knowledge` (6,596 rows) | Early Windows PDF ingest | Live asset; ingestion script is legacy |

`/run/media/proteu5/Storage/...` does **not** exist on this host. That is
not evidence that the corpus is missing. The same store is available at
`/mnt/Storage/AI/VectorDBs/LanceDB`, Hermes mounts that path, and `.env`
points there.

A path discrepancy is classified as a **current operational problem** only
when a script that is still the intended entry point would write or read the
wrong location unless the operator remembers to export variables. Framework
ingest/inspect scripts use the `/run/media/...` default and do not load
`.env` themselves. `config.py` does load `.env`.

Tesseract is not installed on the current Linux host. Combined with the
hard-coded Windows executable path, the original diagram/OCR pipeline is
**historical implementation / current Linux operation not verified**.

## 7. Source Ingestion Architecture

Ingestion is **manual / batch**, not a service and not scheduled. ControlOps
denies cron to the validator. The RAG inbox was empty at inspection (only
`.gitkeep`).

### Source types

| Source type | Ingestion path | Actually ingested? |
| --- | --- | --- |
| `.txt` / `.md` | `scripts/handlers/text_handler.py` via `ingest_any.py` | Yes — at least a Windows-era test Markdown row |
| `.pdf` | `scripts/handlers/pdf_handler.py` via `ingest_any.py` | Yes — four technical books/chapters in `m365_technical_docs_nomic_v3`; a larger earlier PDF in `m365_general_knowledge` |
| Images / diagrams | Historical `scripts/process_inbox.py`; current `image_handler_stub.py` only detects | Yes historically — 16 diagram rows; stub does not embed |
| Office (`.docx` / `.pptx` / `.xlsx`) | Classified then moved to `failed/unsupported` | Not ingested as RAG text. A `.docx` companion exists next to the architecture-pattern Markdown |
| Microsoft Learn catalogue | Untracked ControlOps `ingest_learn_catalog.py` | Yes — 4,501 module/learning-path index rows |
| NCSC CAF 4 | `scripts/frameworks/*` | Yes — 82 structured rows |
| CIS / OSCAL mappings | XML in `Frameworks/CIS_CONTROLS_OSCAL/source/` | Scaffolding; no CIS LanceDB table |
| Architecture-pattern Markdown | `/mnt/Storage/AI/VectorDBs/LanceDB/ingest_architecture_pattern.py` | Yes — 77 rows from one draft LLD |

### Provenance

There is **no common provenance model**. Strength varies by generation:

| Store | Path / URL | Hash | Time | Authority / approval |
| --- | --- | --- | --- | --- |
| PDF v3 | Filename and original inbox path in artefacts | SHA-256 of **name + file size**, not file bytes | `created_at_utc` | None. Keyword `service_area` only |
| Learn catalogue | Canonical URL + catalogue URL | None at row level | Single `retrieved_at` for the batch | `evidence_classification=discovery_index` — correctly not full-page evidence |
| Architecture patterns | Absolute Linux `source_path` | Chunk hash in `id` | Not a first-class ingested-at column | `approval_status=draft`, `retrieval_enabled`, `authoritative_scope`, `customer_specific` |
| Framework CAF | Source PDF name and page range | None observed on the row | `created_at_utc` | Implicit: published NCSC framework |
| Diagrams | Filename + `artifact_dir` | None observed | `created_at_utc` | None. OCR/graph is interpretation |
| General knowledge | Metadata `source=O365_Pro_Reference`, page | None | Per-row `ingest_date` | None |
| `m365_controlops_knowledge` | None useful | UUID ids | `ingest_date` | Client/sensitivity labels on **customer-named** snippets |

Processed and failed folders exist and were used. Artefact run folders exist
for diagrams and PDFs. Those filesystem traces are operational history, not a
corpus manifest.

Duplicate/reingest behaviour:

- PDF writer **appends**. v1, v2 and v3 are successive generations of the
  same book rather than an in-place version.
- Diagram writer deletes-by-id then inserts, but several ExpressRoute and
  Lighthouse images were stored as separate runs.
- Learn ingest can delete-by-id and replace when `--overwrite` is not set.

Corpus freshness can be approximated from timestamps (PDF v3 through 8 July
2026; Learn catalogue 26 July 2026; CAF 1 July 2026; diagrams late June
2026). There is no freshness policy or scheduled refresh.

## 8. Content-Processing Pipelines

### Text and Markdown — implemented in the current inbox router

`ingest_any.py` routes `.txt` / `.md` to a character-window chunker and
writes `multimodal_docs_nomic_v1`. That table currently holds **one** test
row. Heading/section extraction is not applied.

### PDF — implemented; Linux-portable code; historical population

`pdf_handler.py` uses PyMuPDF (`fitz`) to extract per-page text, then
character-window chunks (2,500 / 300 overlap) **within a page**. There is no
OCR fallback for image-only PDFs. Table structure is not preserved. “Section
heading” is the first useful line on the page; many live rows are simply
`Page 107`.

A keyword classifier assigns `service_area` / `control_domain`. That is a
heuristic, not an approved taxonomy mapping.

An earlier pipeline, `ingest_0365_pdf.py` beside the LanceDB store, used
`pypdf` and hard-coded Windows paths to populate `m365_general_knowledge`
(6,596 pages 2–1307 of `O365_Pro_Reference`). That script is legacy.

### Diagram / image — historical implementation; current router is a stub

`process_inbox.py` is a real Windows pipeline: Tesseract OCR, image
description, graph JSON, schema validation, Mermaid, curated embedding text,
then LanceDB write. Artefacts under `artifacts/` match that design
(`00_original` … `08_validation.json`). Sixteen rows exist in
`multimodal_architecture_diagrams_v1`.

`ingest_any.py` does **not** call that pipeline. `image_handler_stub.py`
records a runtime artefact and moves the file. The diagram’s “diagram / image
analysis, OCR and visual description” box is therefore historically true and
currently unwired.

### Frameworks — implemented for CAF 4; CIS is scaffolding

CAF 4 has extract → parse → validate → canonical JSON → 82 LanceDB rows
(41 summaries + 41 sections) with objective/principle/outcome hierarchy and
source page ranges. CIS Control v8 OSCAL mapping XML is present; no CIS
table was found.

### Microsoft Learn — ControlOps batch script, not the inbox

`ingest_learn_catalog.py` fetches `https://learn.microsoft.com/api/catalog/`,
builds a short embedding text from title/summary/products/roles, and writes
`msft_learn_catalog_nomic_v1`. It does **not** download module bodies. Every
row is labelled `discovery_index`.

### Office documents — not evidenced as a processing path

Configured as a recognised type, then treated as unsupported.

## 9. Chunking and Metadata

The diagram’s phrase **“structure-aware chunks (headings · pages · overlap)”**
is only partly true.

| Corpus | Chunking | Structure awareness |
| --- | --- | --- |
| PDF v3 | Page boundary + character window + overlap | Partial. Page yes; heading weak |
| Text/Markdown inbox | Character window + overlap | No |
| Architecture patterns | Markdown heading stack; oversized sections split on paragraphs (3,500 chars) | **Yes** — the strongest structure-aware path |
| CAF 4 | One row per outcome summary/section | Hierarchical control structure, not sliding windows |
| Learn catalogue | One row per module or learning path | Catalogue metadata, not document structure |
| General knowledge | ~900-character page windows, 150 overlap (legacy script) | Page only |
| Diagrams | One embedding payload per processed image | Not chunked; whole interpretation |

Metadata that the diagram lists (source and document ID, title, section,
page, type, hash, timestamps) exists in **some** collections and is absent
or inconsistent in others. Embedding-model attribution is stored on
architecture-pattern rows (`nomic-embed-text-v1.5`) and missing from PDF v3.
`retrieval_enabled` exists only on the pattern table. There is no shared
approval-state or retrieval-enabled flag across the corpus.

## 10. Embeddings

| Item | Observation |
| --- | --- |
| Provider | Local LM Studio, OpenAI-compatible `POST /v1/embeddings` |
| Configured model | `text-embedding-nomic-embed-text-v1.5@q8_0` in RAG `.env` / `config.py` |
| Also advertised | `text-embedding-nomic-embed-text-v1.5@q4_k_m` |
| Other identifiers in code | `nomic-embed-text-v1.5`, `nomic-ai/nomic-embed-text-v1.5`, `nomic-embed-text-v1.5-GGUF` |
| Dimension | 768 on every inspected table and on a live embedding call |
| Query prefixes | Legacy `query_rag.py` uses SentenceTransformer `search_query:`; current `embed_text()` does not |

On 16 August 2026 LM Studio returned HTTP 200 for `/v1/models` and produced a
768-d embedding for the configured q8 model.

Stored rows do **not** consistently record which identifier or quantisation
produced the vector. Cross-collection comparison is therefore assumed
same-family (Nomic 1.5 / 768-d), not proven identical. No re-embed/migration
procedure is defined. v1/v2/v3 PDF tables are successive ingest generations,
not a documented model migration.

A responding embeddings endpoint proves availability, not retrieval quality.

## 11. LanceDB Collections and Live-Store Observations

The live store opened eleven tables. Approximate sizes match the earlier
filesystem survey (~3.8 GB). Hermes sees the same directory at
`/opt/data/lancedb`.

The diagram lists five logical collections. The store contains more. The
diagram is best read as a **logical family view**, not an inventory.

| Table | Rows | Role | Generation | In `rag_query.py`? |
| --- | --- | --- | --- | --- |
| `m365_technical_docs_nomic_v3` | 8,806 | Current PDF technical-doc family (4 source files) | Current for PDF RAG | Yes (via `PDF_LANCEDB_TABLE`) |
| `m365_technical_docs_nomic_v1` | 2,501 | First PDF generation (IT Pros 9 only) | Legacy duplicate | No |
| `m365_technical_docs_nomic_v2` | 2,501 | Second PDF generation (IT Pros 9 only) | Legacy duplicate | No |
| `m365_general_knowledge` | 6,596 | Early large PDF (`O365_Pro_Reference`) | Historical / still the largest table | No |
| `msft_learn_catalog_nomic_v1` | 4,501 | Learn module/path **index** | Current ControlOps ingest | No |
| `framework_controls_nomic_v1` | 82 | NCSC CAF 4 structured controls | Current | No |
| `m365_architecture_patterns_nomic_v1` | 77 | One draft Purview Customer Key LLD | Current, all `draft` | Yes |
| `multimodal_architecture_diagrams_v1` | 16 | Diagram OCR/graph payloads; some duplicate runs | Historical population | Yes |
| `m365_controlops_knowledge` | 3 | Experimental rows naming clients | Experimental; **not** a general ControlOps KB | No |
| `multimodal_docs` / `multimodal_docs_nomic_v1` | 1 + 1 | Early Markdown smoke tests | Legacy | No (`TEXT_LANCEDB_TABLE` unused by `rag_query.py`) |
| `controlops_docs/` | n/a | Directory, not a table | Scaffolding | No |

The store is **healthy enough to open and search**. It is a multi-generation
laboratory corpus, not a curated production index.

`m365_controlops_knowledge` contains client-named snippets (Tokamak, RBC,
Brewin) and an `OFFICIAL-SENSITIVE` label. That is a tenancy/sensitivity
finding: customer-flavoured text sits in the same shared knowledge directory
as generic technical books.

## 12. Retrieval Architecture

Current retrieval is a **CLI library**, not a running service.

`scripts/rag_query.py` (with `.env` loaded through `config.py`):

1. Embeds the question via LM Studio.
2. Vector-searches the PDF v3 table (`limit` default 6).
3. Vector-searches architecture patterns with
   `retrieval_enabled = true` (default 6).
4. Vector-searches diagram payloads (default 4).
5. Builds three context blocks and calls the local chat model.

It does **not** search Learn catalogue, CAF, general knowledge, or the
ControlOps-knowledge table. Multi-corpus search is therefore three families,
not the whole store.

Observed mechanics:

- similarity is LanceDB’s default vector search (distance returned as
  `_distance`; metric not explicitly set in the query code);
- top-k is a CLI/API limit;
- the only metadata filter in the live query path is
  `retrieval_enabled = true` on patterns;
- no freshness, version, tenant, source-approval or service-area filter is
  applied;
- no source deduplication across tables;
- if all three searches are empty, the CLI prints “no context found” and
  does not call the model.

`scripts/rag_server.py` exposes `/health` and `/query` but:

- no process was listening on port 8000;
- ControlOps runbook and doctor treat RAG as **batch/filesystem**, not an
  API;
- `/query` does not search architecture patterns;
- it calls `build_messages()` without the required
  `architecture_context_block` argument, so a live query would fail even if
  the server were started.

`query_pdf_docs.py` and `semantic_search.py` are narrower smoke helpers.

### Retrieval smoke test (this review)

From the Linux `multimodal-ingest` virtualenv, with `.env` active:

- query: “What is Conditional Access in Microsoft Entra?”
- PDF v3 returned five hits from *Microsoft 365 Security for IT Pros (2023)*
  pages 64 and 106–118, including a chunk that names Conditional Access
  components;
- architecture patterns returned three draft LLD sections (weaker distances,
  as expected for a Purview-key design);
- Learn catalogue returned Conditional Access / Entra training modules with
  live `learn.microsoft.com` URLs.

That is evidence that **search returns thematically related rows**. It is
not an acceptance test, a relevance judgement, or a grounded-answer test.
No chat completion was sent during this review.

## 13. Context Composition

`rag_query.py` concatenates numbered blocks. Each PDF block includes file,
page, heading, service area, chunk index, distance and chunk text. Pattern
and diagram blocks include their respective metadata. Diagram and pattern
payloads are truncated (4,000 / 5,000 characters) to keep local-model
prompts small.

There is no token budget beyond those caps, no cross-source ordering policy
beyond “PDF then patterns then diagrams”, and no duplicate suppression.
Weak retrieval is left to the model instructions (“if context is weak, say
so”) rather than a deterministic reject threshold.

`CHAT_MODEL` in `config.py` is still `local-model`. That identifier is **not**
in the LM Studio `/v1/models` list observed today. Chat invocation is
therefore **configured but not verified** on this host, even though the
embedding path works.

## 14. Model Invocation

Intended and configured path: LM Studio loopback
`http://127.0.0.1:1234/v1/chat/completions`, temperature 0.2, max 1,800
tokens.

The system prompt tells the model to treat retrieved Microsoft documentation
as primary, treat draft designs as non-authoritative, treat OCR as lower
confidence, label general knowledge separately, and include a “Sources used”
section.

No external/frontier model is enabled in this RAG path. Legacy
`query_rag.py` names a specific uncensored local chat model; that script
still points at `E:\AI\VectorDBs\LanceDB` and is not the current entry
point.

This review did not call the chat endpoint through `rag_query.py`.

## 15. Citation and Grounding

| Control | Status |
| --- | --- |
| Preserve source filenames | Yes on PDF, diagram and pattern rows |
| Preserve URLs | Yes on Learn catalogue; not on book PDFs |
| Preserve page numbers | Yes on PDF v3, CAF and general knowledge |
| Retain retrieved snippets | Yes in LanceDB text columns and in the prompt |
| Ask the model to cite | Yes, in the system/user prompt |
| Emit structured sources | CLI prints the model’s prose; API would return compact source summaries **if** it ran |
| Verify cited sources were retrieved | **No** |
| Validate claim-to-source alignment | **No** |
| Prevent fabricated citations | Instructional only |
| Deterministic citation anchors | **No** (no stable cite-id in the prompt beyond “Context N”) |
| Enough context for a human to inspect | Partially — file/page/snippet are present if the operator uses `--show-context` |
| Distinguish retrieved doc from claim support | Prompt asks for it; not enforced |

“Prompt asks for sources” is not citation integrity. Grounding is **best
effort**. A human still has to open the cited page.

Learn-catalogue hits are especially easy to over-read: they are module
summaries, not quotations from the module body.

## 16. RAG versus Governed Assurance Evidence

LanceDB is a **semantic technical-knowledge system**.

It may supply documentary context, Learn pointers, architecture patterns,
framework wording and research leads.

It does **not** automatically become:

- tenant evidence;
- an observed configuration fact;
- an approved classification;
- an assurance verdict;
- a control conclusion;
- an adjudicated human decision; or
- governed assurance state.

The Microsoft validator’s evidence records are workspace YAML/Markdown
produced from Microsoft Learn **page retrieval**, not from this RAG store.
PostgreSQL `evidence`, `assurance` and `reporting` schemas remain empty.
There is no RAG → PostgreSQL write path.

Calling a retrieved chunk “evidence” in a partner conversation should always
be qualified as **retrieved documentary context**.

## 17. RAG versus Graph / Azure Evidence Collection

These are different responsibilities.

| | RAG | Graph / Azure / platform tooling |
| --- | --- | --- |
| Question | What knowledge should we consider? | What is configured or observable? |
| Typical sources | Books, Learn, frameworks, designs, diagrams | Graph, Azure APIs, exports, telemetry |
| Historical home | Windows MultimodalIngest + LanceDB | Current Linux ControlOps runtime |
| Callable from RAG code? | n/a | No. RAG scripts do not call MCP |
| Callable from validator? | No automatic RAG call | Graph MCP host binary exists; not verified in Hermes. Azure MCP not evidenced |

`scripts/azure_controlops/collect_azure_inventory.sh` lives in the RAG tree
and authenticates with a service principal. That is **platform collection
code stored next to RAG**, not a RAG pipeline stage. This assessment does
not treat it as a Knowledge/RAG capability.

Absence of Graph/Azure calls from RAG is not a RAG defect.

## 18. Hermes / ControlOps Integration

| Question | Answer |
| --- | --- |
| Can Hermes access the LanceDB files? | Yes. Gateway bind-mount
`/mnt/Storage/AI/VectorDBs/LanceDB` → `/opt/data/lancedb` |
| Does the validator invoke RAG? | No. `SOUL.md` “retrieval” means fetching
Microsoft Learn pages, not LanceDB search |
| Is retrieval performed automatically? | No. Operator-run CLI only |
| Is there an operational RAG API? | No process; ControlOps does not expect one |
| Is there a library call from agents? | No |
| Do retrieved passages flow into validator reports? | Not observed |
| Are RAG results persisted as assurance state? | No |
| RAG → PostgreSQL? | No |
| What does ControlOps check? | `doctor` only tests that
`/mnt/Storage/AI/RAG/MultimodalIngest` exists |
| Operator steps today | Start LM Studio; use the RAG venv; run
`rag_query.py` or a one-off ingest script |

A mount is not a workflow.

The untracked ControlOps script `ingest_learn_catalog.py` is the only
ControlOps-owned writer into the store. It imports embeddings from the RAG
project (`RAG_ROOT = /mnt/Storage/AI/RAG/MultimodalIngest`). That is a
batch integration, not an agent integration.

## 19. Runtime and Operational Observations

16 August 2026, read-only except for a local embedding request and LanceDB
searches:

- Hermes gateway/dashboard running; LanceDB mount present; no Docker socket.
- PostgreSQL healthy and separate; not used by RAG.
- LM Studio `/v1/models` HTTP 200; embedding probe succeeded (768-d).
- `bash scripts/controlops doctor`: RAG directory **PASS**.
- No `uvicorn` / `rag_server` listener.
- Linux venvs: `/home/proteu5/.venvs/multimodal-ingest` and
  `MultimodalIngest/.venv-linux` both import `lancedb 0.33.0`.
- Host `python3` does not have `lancedb`.
- Tesseract is not on `PATH`.
- Inbox empty; 18 processed files and 43 artefact directories remain from
  earlier runs.

RAG operates as **CLI + batch scripts + a filesystem LanceDB**. It is not an
HTTP service in the supported ControlOps runtime.

## 20. Current Implementation-Status Assessment

Vocabulary: **Implemented**, **Validated**, **Experimental**, **Partially
Implemented**, **Historical Implementation**, **Configured but Not
Verified**, **Scaffolding**, **Planned**, **Conceptual**, **Not Evidenced**.

Where the Windows/Linux split matters, both are stated.

| Capability | Status | Notes |
| --- | --- | --- |
| Local LanceDB store at the ControlOps mount | Implemented | Opened 11 tables; Hermes can see the files |
| LM Studio embedding service | Implemented as a local service | Live 768-d vector returned |
| PDF text extraction + char chunk + embed | Historical Implementation / current Linux code present, not re-run today | v3 populated June–July 2026 |
| Text/Markdown inbox ingest | Experimental | One test row |
| Diagram OCR + graph + embed | Historical Implementation / current Linux operation not verified | 16 rows exist; Windows Tesseract path; stub in `ingest_any.py` |
| Structure-aware heading chunking | Partially Implemented | Patterns yes; PDFs mostly page windows |
| NCSC CAF 4 structured ingest | Implemented (batch) | 82 rows; scripts still default to `/run/media/...` without `.env` |
| CIS / other frameworks | Scaffolding | XML only |
| Architecture-pattern ingest | Implemented (narrow) | One draft LLD, 77 rows, Linux source_path |
| Microsoft Learn catalogue ingest | Implemented (index only) | 4,501 discovery_index rows |
| Multi-generation PDF tables v1/v2 | Historical Implementation | Superseded by v3 |
| Large general-knowledge table | Historical Implementation / still usable as an asset | Not on the current query path |
| Vector search from Linux | Implemented (smoke-demonstrated) | Related PDF/Learn/pattern hits; **not** quality-validated |
| Metadata filtering | Partially Implemented | Only `retrieval_enabled` on patterns |
| `rag_query.py` CLI | Implemented as a developer tool | Chat step not verified (`local-model`) |
| FastAPI RAG server | Scaffolding / stale | Source exists; not running; `/query` signature drift |
| Context composition + grounding prompt | Partially Implemented | Prompt-level; no citation verification |
| Human-reviewable output | Experimental | Printed answer; no review workflow |
| Agent / Hermes consumption | Not Evidenced | Mount only |
| Assurance-query API on the diagram | Planned / not operational | |
| Authoritative-source / approval filters | Conceptual except pattern `approval_status` | Not applied at query time |
| Retrieval acceptance tests | Not Evidenced | |
| Scheduled ingest / freshness | Not Evidenced | |
| RAG as governed evidence | Not applicable — correctly out of scope | Must stay that way |

## 21. Diagram / Code / Runtime Disagreements

- The diagram lists five collections; eleven tables exist, and the largest
  (`m365_general_knowledge`) and the Learn catalogue are omitted.
- `m365_controlops_knowledge` is not a populated ControlOps knowledge base.
- “Structure-aware chunking” overstates the PDF/text path.
- “Metadata filtering” is almost unused in the live query path.
- “Architect · agent · API” overstates current issuers. Only an operator CLI
  is demonstrated.
- “Grounded response with citations” and “unsupported claims identified”
  are prompt ambitions, not verified behaviours.
- “Human-reviewable output” is a printed answer, not a review control.
- Image analysis is shown as a current processing lane; the current inbox
  router stubs it.
- `multimodal_docs_nomic_v1` is listed as a live collection family; it holds
  a single test document.
- ControlOps runbook correctly assumes filesystem/batch RAG; the diagram
  implies a smoother query service than exists.

## 22. Security and Trust Considerations

Implemented or observed:

- Local embeddings and (intended) local chat — no RAG-path external model.
- Loopback LM Studio and `.env` API key `lm-studio` (not a secret).
- Inbox / processed / failed isolation for batch files.
- Pattern rows can be marked `customer_specific` and `retrieval_enabled`.
- Validator does not automatically pour RAG text into reports.

Absent or weak:

- No corpus-wide source-approval or trusted/untrusted flag.
- Ingested documents are untrusted content. There is no prompt-injection
  control around retrieved chunks.
- `m365_controlops_knowledge` mixes client names and an
  `OFFICIAL-SENSITIVE` label into the shared store.
- Diagram OCR/graph text can be wrong; it is still embedded and searchable.
- Stale-source risk: books from 2023 and a June/July 2026 ingest with no
  refresh policy.
- Append-only PDF writes can duplicate content across generations.
- Hermes has write access to the LanceDB mount (`HERMES_WRITE_SAFE_ROOT`
  includes `/opt/data`). Corpus integrity depends on operator discipline.
- The Azure inventory script in the RAG tree sources a host credentials
  file. That is a secrets-adjacent neighbour, not a RAG control.

Do not describe this corpus as tenant-isolated or as an approved-source
library. Parts of it are commercial books, draft internal designs, OCR
interpretations and experimental client notes.

## 23. Missing Architectural Concepts

These matter and are thin or absent:

- a single **corpus manifest** (what was ingested, from where, with which
  model, when);
- a shared **source-authority** and **approval** model used at query time;
- **ingestion lineage** that a partner can audit without reading run folders;
- a **freshness** policy;
- a **stable callable interface** that Hermes can use;
- **citation anchors** and post-answer source checks;
- **retrieval acceptance tests**;
- **observability** (other than print statements and artefact JSON);
- **tenancy / sensitivity** separation;
- an explicit **rebuild procedure** for Linux;
- connection from retrieved knowledge to PostgreSQL only through a human
  decision (the boundary exists by absence of a pipe, not by a designed
  promotion workflow).

## 24. Current Limitations and Unverified Claims

- Retrieval quality, grounded-answer quality and hallucination rate were
  not measured.
- Chat completion through `rag_query.py` was not executed.
- PDF/text/CAF/pattern ingest was not re-run on Linux during this review.
- Whether `LANCEDB_URI` was used for the Learn ingest is inferred from the
  table contents and script defaults, not from a captured command line.
- Diagram-type labels include obvious misclassifications
  (`azure_api_management_architecture` on an AVD diagram).
- Image-only PDF behaviour is untested.
- Concurrent Hermes read vs ingest write locking was not tested.
- Backup/restore of LanceDB was not tested.
- The Codex RAG assessment was not used as evidence.

## 25. Recommended Next Engineering Steps

Do not grow the corpus first. The store is already large relative to the
query surface.

Highest-value increment, in order:

1. **Normalise configuration** so every remaining writer/reader defaults to
   `/mnt/Storage/AI/VectorDBs/LanceDB` and loads the same `.env`. Leave
   historical `E:\` and `/run/media` comments in place; stop using them as
   live defaults.
2. **Define the current collection set** (PDF v3, Learn catalogue, CAF,
   architecture patterns, diagrams) and stop putting new data into v1/v2,
   `multimodal_docs*` and `m365_controlops_knowledge` until those tables
   have an explicit purpose.
3. **Publish a tiny callable retrieval interface** (library + CLI) that
   returns structured hits with source, page/URL, snippet and distance —
   without requiring a chat model. Point Hermes/the validator at that, as
   an optional research aid.
4. **Add a retrieval smoke/acceptance test** with a handful of known
   questions and expected source files/URLs.
5. **Fix citation anchors** (stable retrieved-hit IDs) before spending
   effort on a RAG API.
6. Only then decide whether to repair the Linux diagram/OCR path or to
   treat those 16 rows as a frozen historical corpus.

A FastAPI rewrite is not the first increment. The existing server is stale
and ControlOps does not assume it.

## 26. Overall Architectural Assessment

### Answers to the required questions

1. **What was genuinely built?** A local multimodal ingest workshop, several
   embedding generations, a sizeable LanceDB corpus, CAF and pattern
   pipelines, a Learn-catalogue loader, and a multi-source RAG CLI.
2. **What remains usable?** The live store, Linux venvs, `.env` path, LM
   Studio embeddings, and vector search over the current tables.
3. **What is operational under Linux?** Embedding + search, demonstrated.
   Ingestion code for PDF/text/CAF/Learn/patterns is portable if `.env` is
   used. Diagram/OCR is not.
4. **What is integrated with Hermes/ControlOps?** A bind mount, a doctor
   directory check, and an untracked Learn ingest script. No agent
   retrieval loop.
5. **Is the live store healthy and usable?** Yes, as a laboratory corpus
   that opens and searches. It is multi-generation and uneven.
6. **Can provenance be trusted consistently?** No. Some tables are strong
   (Learn URLs, CAF page ranges, pattern source paths); others are
   filename-only or experimental.
7. **Is ingestion reproducible?** Not as a documented one-command Linux
   rebuild. Pieces can be re-run; the Windows image path cannot as written.
8. **Is retrieval reproducible?** Yes for search, given the venv, `.env`
   and LM Studio. Not as a service.
9. **Is retrieval quality validated?** No.
10. **Are citations genuinely traceable?** Only as “the prompt included
    this file/page and asked the model to cite it.”
11. **Does RAG reduce hallucination risk?** It can, by supplying snippets
    and telling the model to stay inside them. It does not eliminate the
    risk, and the model is still allowed to add labelled general knowledge.
12. **Does any RAG result become governed assurance state automatically?**
    No.
13. **What Windows-era artefacts remain?** Hard-coded `E:\` / Tesseract
    paths, Windows venvs, legacy ingest/query scripts, `/run/media`
    defaults, and historically populated tables.
14. **Which discrepancies are harmless residue?** Commented Windows paths,
    superseded v1/v2 tables, README “next step is LanceDB write” (already
    done), and the missing `/run/media` mount when `.env` is used.
15. **Which create real current problems?** `process_inbox.py` cannot run
    on this Linux host as written; framework scripts ignore `.env`;
    `rag_server.py` is signature-stale; `CHAT_MODEL=local-model` does not
    match advertised models; customer-named rows sit in the shared store;
    Hermes never calls retrieval.
16. **Smallest increment to a dependable knowledge service?** One
    config-normalised, test-backed retrieval function over the current
    collections, returning structured sources, callable without a chat
    model — then optional validator use as research context.

ControlOps already has something more substantial than a prototype folder of
empty tables. It does not yet have a knowledge service that a partner should
describe as governed, validated or agent-integrated. The right next move is
to make the existing assets **callable, attributable and testable**, not to
ingest more documents.

## 27. Related Architecture Documents

| Document | Notes |
| --- | --- |
| [01 — Contextual architecture (Codex)](01-controlops-contextual-architecture.md) | System context; not modified |
| [Cursor-01 — Contextual architecture](Cursor-01-controlops-contextual-architecture.md) | Independent context assessment; not overwritten |
| [02 — Knowledge and RAG (Codex)](02-controlops-knowledge-rag-component-architecture.md) | Sibling assessment; inspected only |
| This document | Independent RAG assessment |
| [03 — Assurance data platform](03-controlops-assurance-data-platform-logical-data-architecture.md) | Governed-data counterpart |
| [04 — End-to-end process](04-controlops-end-to-end-assurance-process-and-reality-assessment.md) | Workflow counterpart |
| [05 — Deployment](05-controlops-deployment-architecture.md) | Host/runtime counterpart |

Diagrams for views 01–05 live under `docs/architecture/diagrams/`.

## 28. Document History

| Version | Date | Description |
| --- | --- | --- |
| 0.1.0 | 16 August 2026 | Independent Knowledge/RAG assessment against the RAG repository, live LanceDB store, ControlOps contracts and read-only Linux runtime. Codex document 02 inspected but not modified. |
