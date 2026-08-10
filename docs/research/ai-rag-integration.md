# **Production-Grade AI Architecture for Educational Platforms: End-to-End PDF Ingestion, Multi-Stage Vector Retrieval, and Grounded Question Answering**

Modern educational web applications require scalable mechanisms to enable administrators, teachers, and staff to interact with diverse repositories of academic resources, institutional regulations, and administrative policies. Integrating artificial intelligence into an established educational platform—such as a monorepo featuring frontend dashboards, backend API services, relational databases, and background job processors—demands an architecture that seamlessly bridges relational user contexts with high-dimensional vector spaces.
A production-grade Retrieval-Augmented Generation (RAG) system decouples document processing into two isolated workflows: an offline, asynchronous ingestion pipeline responsible for extracting, chunking, deduplicating, and indexing unstructured documents, and a real-time, low-latency retrieval and generation pipeline designed to process user queries with strict authorization enforcement and precise source citations.

## **Architectural Topology and System Decoupling**

Modern educational platform codebases typically adopt monorepo or modular microservice architectures, housing web dashboards built with frameworks like Next.js or SvelteKit, application APIs powered by Node.js or Python, and relational database layers utilizing PostgreSQL or SQLite1. Injecting AI capabilities directly into synchronous web API handlers creates severe bottlenecks because document parsing, visual layout analysis, and vector embedding generation are computationally intensive operations. To maintain high web application availability and sub-second response times, the system architecture separates synchronous user interaction paths from asynchronous data processing pipelines.
The offline ingestion workflow handles raw document processing asynchronously. When an administrator or teacher uploads a policy manual or course syllabus through the web dashboard, the primary API service writes the file metadata to the relational database and enqueues a background job into a distributed message broker, such as BullMQ or Celery backed by Redis. Independent background worker pools ingest these job payloads to execute compute-heavy PDF parsing, semantic text chunking, SHA-256 deduplication, vector embedding generation, and database upserts. Upon completion, the worker updates the document status in the relational database, notifying the frontend application through webhooks or WebSocket events.
The runtime retrieval workflow executes synchronously when a user submits a question regarding institutional policies or teaching materials. The web API intercepts the incoming HTTP request, extracts the authenticated user's JSON Web Token (JWT), and retrieves the user's role and organizational clearance level. The retrieval engine translates these security claims into pre-retrieval metadata filters, executing a multi-stage search across the vector database. The retrieved context chunks are assembled, validated for relevance, and formatted into an augmented prompt supplied to the Large Language Model (LLM), which returns a grounded answer accompanied by explicit document title and page-level citations.

## **Enterprise Document Ingestion and PDF Parsing**

Educational documents present significant structural complexity. Course syllabi, institutional compliance handbooks, government education policy directives, and academic reports frequently combine multi-column text formatting, embedded schedules, nested grading tables, and inline metadata. Standard text extraction libraries rely on basic physical text streams, which scramble reading order in multi-column documents and flatten complex tables into uninterpretable text strings, causing downstream AI models to fail or generate inaccurate responses.
To ensure high retrieval quality, platforms must employ layout-aware document parsers. Modern parsing solutions employ vision-language models (VLMs) and layout detection networks to interpret documents as structured visual artifacts rather than flat character streams.

| Feature / Metric | Docling (IBM Research) | LlamaParse (LlamaIndex) | Unstructured (Open Source) | Firecrawl (Fire-PDF) |
| :---- | :---- | :---- | :---- | :---- |
| **Primary Approach** | Layout detection \+ VLM (Granite-Docling-258M) | Vision-Language Model Cloud API | Rule-based partitioning \+ OCR models | Millisecond page classification \+ Neural OCR |
| **Table Extraction Accuracy** | **97.9%** (TableFormer engine) | High (handles complex merged cells) | Variable (100% simple, 75% complex) | High (dedicated compute allocation) |
| **Deployment Model** | Open-Source / Local Self-Hosted (Apache 2.0 / MIT) | Proprietary Managed Cloud / Customer VPC | Open-Source Core / Commercial SaaS | API-First Cloud / Managed Credit Billing |
| **Processing Throughput** | \~6.28s (1-page) to \~65s (50-page linear) | **\~6s uniform** per document | 51s (1-page) to 141s (50-page) | **\<400ms per page** average |
| **Data Privacy & Cost** | Zero per-page API fees; full on-premise privacy | Usage-based API pricing; cloud transmission | Open-source self-host option available | Credit-based usage fees; cloud transmission |
| **Best EdTech Fit** | Self-hosted deployment for sensitive policies | High-fidelity extraction of complex academic tables | Multi-format ingestion (PDF, DOCX, HTML) | Web-based PDF scraping and rapid ingestion |

For educational platforms prioritizing data privacy, low operational expenditure, and accurate table extraction, self-hosted open-source solutions like IBM's **Docling** offer an optimal balance. Its TableFormer architecture reconstructs complex nested table cells without converting structure into lossy text strings.
Following visual extraction, the text stream undergoes mandatory boilerplate normalization:

* **Header and Footer Removal**: Running headers, page numbers, institutional logos, and repetitive copyright footers are stripped across page boundaries to prevent chunk noise.
* **Whitespace Normalization**: Multi-space indents and inconsistent line breaks are standardized into space delimiters while preserving logical paragraph breaks.
* **Table Structure Conversion**: Tables are converted into clean Markdown or HTML structures, maintaining cell relationships so that LLMs can interpret tabular policy data during inference.

## **Semantic Chunking Strategies, Hash Deduplication, and Metadata Enrichment**

Splitting educational documents using fixed character or token counts causes structural breakages, often splitting paragraphs mid-sentence or detaching policy section headings from their governing text clauses. Production RAG applications employ **semantic and layout-aware chunking**. Semantic chunking analyzes sentence embeddings sequentially, calculating the cosine distance between consecutive sentences and creating a dynamic chunk boundary whenever the semantic distance exceeds a pre-set threshold.
Optimal chunk configurations for educational administrative and policy documents maintain target sizes of **300 to 500 tokens** with a **10% to 20% overlap** (50 to 100 tokens). Chunks under 100 tokens lack sufficient context for semantic vector search, while chunks exceeding 1000 tokens dilute vector signals and introduce unnecessary noise into the LLM context window.
Before chunks are embedded, a cryptographic SHA-256 hash is generated for each text segment. If an identical document or policy clause is uploaded across multiple departments, the ingestion engine skips indexing duplicate chunks. This deduplication step reduces total vector index size by up to 40%.
Every chunk is enriched with mandatory payload metadata to enforce access control and facilitate precise targeted filtering.

| Field Name | Data Type | Purpose & Operational Scope | Example Value |
| :---- | :---- | :---- | :---- |
| chunk\_id | UUID / String | Unique identifier for vector storage tracking | "chk\_98f2a1b73c" |
| doc\_id | UUID / String | Relational database document record link | "doc\_policy\_2026\_v2" |
| tenant\_id | String | Multi-tenant organization isolation filter | "org\_district\_49" |
| required\_roles | Array\[String\] | Role-Based Access Control authorization list | \["admin", "teacher"\] |
| department | String | Academic or administrative division filter | "Computer Science", "HR" |
| doc\_type | String | Categorizes material type for precise search scope | "curriculum", "policy" |
| page\_number | Integer | Source provenance for inline answer citations | 14 |
| section\_heading | String | Maintains context hierarchy within long documents | "3.2 Evaluation Criteria" |
| created\_at | Timestamp | Temporal filtering for policy freshness | 1772841600 |

## **Vector Storage Mechanics, Embedding Models, and Indexing**

Converting text chunks into high-dimensional vector representations requires embedding models that capture semantic relationships. Standard choices include OpenAI text-embedding-3-large (3072 dimensions), Cohere embed-v4 (1024 dimensions), and open-source models like BGE-Large-EN-v1.5 or all-MiniLM-L6-v2.
Vector databases store embeddings to support sub-50ms Approximate Nearest Neighbor (ANN) searches. Selecting a vector database depends on whether the system is in an early Proof of Concept (PoC) phase or scaled for high-concurrency production2.

### **Proof of Concept (PoC) Vector Store Options with SQLite**

When developing a PoC or local prototype using SQLite, setting up external database servers or cloud vector services introduces unnecessary operational complexity1. Embedded (in-process) vector stores allow developer workflows to run entirely on local disk files2.

| Engine / Extension | Architecture | Key Characteristics & Trade-offs | Best PoC Use Case |
| :---- | :---- | :---- | :---- |
| **sqlite-vec** | C/C++ Extension for SQLite1 | Enables vector distance functions directly inside standard .sqlite database files1. Allows executing relational SQL joins and WHERE metadata filters alongside vector similarity queries1. | Minimalist tech stacks keeping 100% of app data and vectors in a single SQLite database file1. |
| **LanceDB** | Embedded Columnar Engine (Rust/Node/Python)2 | In-process columnar vector database using disk-backed storage1. Delivers high query throughput and low memory overhead without server dependencies1. | Local development requiring fast search performance across large datasets without Docker processes1. |
| **ChromaDB (Embedded)** | In-Process Python / JS SDK2 | Runs in embedded mode by default, persisting embeddings to local disk files or an embedded SQLite instance4. Provides developer-friendly APIs4. | Rapid prototyping and quick integration with frameworks like LangChain or LlamaIndex4. |

### **Production Vector Database Comparison**

| Evaluation Vector | pgvector (PostgreSQL Extension) | Qdrant | Pinecone |
| :---- | :---- | :---- | :---- |
| **Architectural Model** | Database extension / Relational Hybrid | Dedicated Vector Search Engine (Rust) | Managed Serverless Cloud Service |
| **Indexing Algorithms** | HNSW, IVFFlat | Filterable HNSW, Inverted Payload Index | Proprietary Serverless ANN Graph |
| **Metadata Filtering** | SQL WHERE clauses combined with vector distance | **Payload HNSW integration** (Pre-filtering) | Metadata filters via Namespaces/Metadata |
| **Multi-Tenancy** | Schema / Row-Level Security (RLS) | Tenant Collections / Payload Filtering | Namespaces / Collection Isolation |
| **Operational Effort** | **Minimal** (Uses existing PostgreSQL instance) | Low to Moderate (Self-host Docker/Cloud) | **Zero** (Fully managed cloud API) |
| **Best EdTech Fit** | Early-to-mid stage apps using PostgreSQL | High-concurrency platforms needing sub-5ms filtering | Cloud-native applications wanting managed scaling |

For systems operating on PostgreSQL in production, **pgvector** simplifies operational overhead by allowing relational user records and vector embeddings to reside within the same database instance, avoiding the complexity of running a dedicated vector database. When scaling beyond tens of millions of embeddings with heavy metadata filtering across multiple roles, **Qdrant** provides high performance.

### **PoC-to-Production Migration Path**

> 1. **Phase 1 (PoC / Local Prototyping)**: Utilize **sqlite-vec** or **ChromaDB**1. This approach keeps all code, relational data, and vector indexes contained on a local developer machine with zero infrastructure cost1.
> 2. **Phase 2 (Production Deployment)**: Migrate vector tables to **PostgreSQL with pgvector** (if transitioning the primary relational database from SQLite to Postgres) or deploy a dedicated instance of **Qdrant**2.

The mathematical similarity between a query embedding vector ![][image1] and a candidate document chunk vector ![][image2] is computed using Cosine Similarity:
![][image3]
Key HNSW configuration parameters for production index tuning include:

* ![][image4] (Number of bi-directional links per node, range: 16–64): Higher values increase accuracy on dense datasets at the cost of higher memory consumption and longer index build times.
* ![][image5] (Search depth during index construction, range: 100–200): Controls the trade-off between index build time and query recall performance.

## **Multi-Stage Hybrid Search, Reciprocal Rank Fusion, and Reranking**

RAG architectures that rely exclusively on dense vector similarity often struggle to locate exact keyword matches, such as precise policy section numbers (e.g., "Clause 4.2.1"), specific course codes, or specialized terminology. Production systems implement a **four-stage hybrid retrieval strategy** combining lexical (sparse) and semantic (dense) search methods.

### **Stage 1: Role-Based Metadata Pre-Filtering**

Before executing vector or keyword searches, the query engine applies authorization filters derived from the user's validated JWT permissions. This narrows the candidate pool by filtering out inaccessible documents before ranking occurs.

### **Stage 2: Dual Sparse-Dense Retrieval**

The system executes two retrieval requests in parallel:

> 1. **Sparse Lexical Search (BM25)**: Evaluates exact term frequencies, inverse document frequencies, and field lengths to score exact keyword matches.
> 2. **Dense Vector Search (ANN)**: Computes high-dimensional vector similarity using the HNSW index to catch conceptual matches and paraphrased questions.

### **Stage 3: Reciprocal Rank Fusion (RRF)**

To combine ranking outputs from systems with different scoring scales (BM25 scores vs. cosine distances), the system applies Reciprocal Rank Fusion. The RRF score for a document chunk ![][image6] across the result sets ![][image7] is calculated as:
![][image8]
Where ![][image9] is a smoothing constant (typically set to ![][image10]), and ![][image11] represents the ordinal rank position of document ![][image6] within retrieval system ![][image12].

### **Stage 4: Cross-Encoder Reranking**

The top 20 to 50 candidate chunks selected by RRF are passed to a Cross-Encoder reranking model (such as Cohere ReRank or bge-reranker-large). Unlike bi-encoders, which generate separate query and document embeddings, cross-encoders compute joint attention across the query and chunk text simultaneously. This produces accurate relevance scoring, allowing the system to select the top ![][image9] (typically 5 to 10\) most contextually relevant chunks.

### **Context Assembly and Prompt Injection**

The final context payload is constructed using the following principles:

* **Maximal Marginal Relevance (MMR)**: Filters out semantically redundant chunks. If three retrieved chunks contain identical policy text, MMR selects the highest-scoring chunk and discards the remaining duplicates.
* **Context Budget Optimization**: Context window allocation is capped at **60% to 70% capacity**. Overfilling context windows increases processing costs and can lead to the "lost in the middle" phenomenon, where LLMs overlook information placed in the middle of long prompts.
* **Provenance Tagging**: Chunks are wrapped in explicit XML context tags that detail source metadata (document ID, title, page number, and section). This structure enables the LLM to output accurate, verifiable inline citations.

## **Security, Governance, and Role-Based Access Control**

Educational platforms serve distinct user personas with varying security clearances. Administrators require access to restricted financial data, HR policies, and administrative reviews. Teachers require access to departmental curricula, teaching resources, and internal guidelines, but must not view confidential peer evaluations or student health files.
Security enforcement must happen **prior to context assembly and generation**. Relying on system prompts to enforce data privacy (e.g., instructing the LLM: "Do not answer if the user is a teacher") is unsafe, as prompt injection techniques can bypass instruction guardrails.
System authorization uses a multi-layered security approach:

> 1. **JWT Verification Layer**: The platform's API gateway interceptor validates incoming user requests, decoding JWT claims to establish tenant\_id, user\_id, and assigned roles.
> 2. **Payload Metadata Gatekeeper**: Query engines translate validated user claims into dynamic vector database payload filters. For instance, a query initiated by a teacher generates a payload filter restricting candidates to matching tenant\_id values and required\_roles arrays that contain "teacher" or "public" clearance.
> 3. **Multi-Tenant Namespace Isolation**: Dedicated vector database namespaces or collections isolate institutional data across distinct tenant organizations, preventing cross-tenant context leaks.

## **The Role of Redis in Production RAG Pipelines**

A high-performance RAG pipeline requires an in-memory data store like **Redis** to fulfill three critical operational roles:

### **1\. Distributed Asynchronous Job Broker**

PDF parsing, optical character recognition (OCR), layout detection via Docling, text chunking, and calling external vector embedding APIs are computationally heavy operations. Executing these operations inside a synchronous web HTTP request handler causes request timeouts (often taking 10 to 60+ seconds per multi-page document) and blocks the web server event loop. Redis acts as the in-memory message broker powering background task queues like **BullMQ** (Node.js) or **Celery** (Python). When a user uploads a document, the API server instantly returns an HTTP 202 Accepted response while writing a lightweight job payload to Redis. Background worker pools poll Redis, process the heavy document ingestion off-thread, and emit completion events.

### **2\. Semantic Query Caching**

In educational platforms, teachers and administrators repeatedly ask identical or semantically similar policy questions (e.g., *"What is the policy for annual sick leave?"* vs. *"How many sick days are teachers allowed per year?"*). Directing every user query to the vector database and LLM APIs introduces latency (1–3 seconds) and increases API expenses.
A **Redis Semantic Cache** optimizes this workflow:

> 1. Incoming user questions are converted into vector embeddings.
> 2. Redis executes an in-memory vector similarity lookup against previously cached query vectors.
> 3. If a match is identified within a strict threshold (![][image13]), Redis returns the cached answer instantly (![][image14] response time). This completely bypasses vector retrieval and LLM inference, reducing AI operational costs by **30% to 60%**.

### **3\. API Rate Limiting and Session Context Management**

* **Rate Limiting**: Redis key-expiration counters protect external LLM APIs from abuse by enforcing user-level quotas (e.g., capping requests at 50 queries/hour per teacher).
* **Active Chat Session Context**: Managing short-term multi-turn conversational memory in Redis ensures fast history retrieval during active chat sessions without polluting the relational primary database.

## **Phased Implementation Roadmap and Continuous System Evaluation**

Deploying an enterprise AI retrieval pipeline into an educational environment requires a structured implementation plan accompanied by continuous automated performance evaluation.

Phase 1: Ingestion Pipeline Setup
├── Deploy BullMQ/Redis worker service connected to API gateway
└── Integrate Docling framework for layout-aware PDF parsing

Phase 2: Vector Database & Security
├── Provision sqlite-vec/ChromaDB (PoC) or pgvector/Qdrant (Prod)
└── Index required\_roles and tenant\_id payload fields for pre-filtering

Phase 3: Hybrid Retrieval & Reranking Engine
├── Implement parallel BM25 (sparse) and HNSW (dense) search
└── Connect Reciprocal Rank Fusion (RRF) and Cross-Encoder reranker

Phase 4: Security Verification & Evaluation
├── Validate JWT metadata filtering across user clearance levels
└── Integrate RAGAS evaluation suite for automated regression testing

To prevent answer hallucinations and track retrieval performance over time, production applications utilize the **RAGAS (Retrieval-Augmented Generation Assessment)** evaluation framework. The system continuously tracks four primary metrics.

| Evaluation Metric | Target Threshold | Operational Focus | Primary Failure Mode Addressed |
| :---- | :---- | :---- | :---- |
| **Context Precision** | **![][image15]** | Evaluates whether retrieved chunks are relevant to the query. | Context window clutter and redundant information. |
| **Context Recall** | **![][image15]** | Measures whether all ground-truth facts required to answer the query were retrieved. | Incomplete retrieval caused by small chunk window sizes. |
| **Faithfulness (Groundedness)** | **![][image15]** | Verifies that every assertion in the generated response directly derives from context chunks. | AI model hallucinations and ungrounded fabrications. |
| **Answer Relevance** | **![][image15]** | Assesses how directly the generated output addresses the user's inquiry. | Off-topic generation and tangential responses. |

By combining layout-aware document extraction, semantic chunking, payload-filtered vector indexing, multi-stage hybrid search, and strict role-based access control, educational platforms can deploy an enterprise-grade AI assistant capable of delivering accurate, verifiable policy and curricular guidance.

#### **Works cited**

> 1. Embedded Vector Databases for Go in 2026: chromem-go vs sqlite-vec vs Bleve vs LanceDB \- Shaharia Azam, [https://shaharia.com/blog/choosing-embeddable-vector-database-go-application/](https://shaharia.com/blog/choosing-embeddable-vector-database-go-application/)
> 2. Best Vector Databases in 2026: A Complete Comparison Guide \- Firecrawl, [https://www.firecrawl.dev/blog/best-vector-databases](https://www.firecrawl.dev/blog/best-vector-databases)
> 3. For an absolute beginner, which is the vector database I should be starting with? : r/Rag, [https://www.reddit.com/r/Rag/comments/1i5rpyd/for\_an\_absolute\_beginner\_which\_is\_the\_vector/](https://www.reddit.com/r/Rag/comments/1i5rpyd/for_an_absolute_beginner_which_is_the_vector/)
> 4. Top Vector Databases for Enterprise AI: 2026 Comparison \- Atlan, [https://atlan.com/know/top-vector-databases-enterprise-ai/](https://atlan.com/know/top-vector-databases-enterprise-ai/)
> 5. Best Vector Databases in 2026: Complete Comparison Guide \- Encore Cloud, [https://encore.dev/articles/best-vector-databases](https://encore.dev/articles/best-vector-databases)
> 6. Best Vector Databases 2026: Pinecone, Chroma, Qdrant & More | DataCamp, [https://www.datacamp.com/blog/the-top-5-vector-databases](https://www.datacamp.com/blog/the-top-5-vector-databases)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAaCAYAAACD+r1hAAAAlklEQVR4XmNgGAXDGjChC4DAZiD+j4a1gXgFlI0CnkIF0SWQNcOBAJJgDLIEEIQgycGBBZKgFLIEENggycFBCzZBKMCqwQFJkBtZggGHBhCACU5AE+9EkkMBaUgS6kDMCMQdSGIYGkCAF4jPMEAkfwFxKRCXQflYNWADtNWA7H4YZkVRgQb8GCDBCopYSyB2ZIAExmADANUXOu/mKWquAAAAAElFTkSuQmCC>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA0AAAAZCAYAAADqrKTxAAAAk0lEQVR4XmNgGHmAHYhlgdgYXQIXuAHE/5Ew0cCDgQxNtgxkaLJhIEJTNxB/BuIrQNzEQECTAQNCEqQQFGrFSGJYNcEkUtDEy5DkUIA3LgkGPJo6cUkw4NEUi0uCAY8mEIBJWKCJVyDJYYBWBoQkN1QsF0kMhEG2MkLl4EAXiN8wQBT8A+I2BlTngTATXPUooCcAAIY4O2CvrmstAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,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>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABYAAAAaCAYAAACzdqxAAAABC0lEQVR4XmNgGAX0BvVA/AWI/0PxWVRpDPCQAaEWpK8YVRoTwBSDMC6gB8S1DBA1xmhyOMETBoTLcYHHQHyMAb8aFOAFxClAvIUBt6Z1UJqQr1DACSgNCi9smniAOBfKBsmvRpLDC2CGgcINxJZBkgOBH1DanQEir4Ukhxc8RWKDNMYh8fOBmBvKBvkMm4+wApAr0pD4II0LkfjI3iYrfGEApBEU+yDwDFmCASK3Ck0MJ0B3AcxVtkCsgyTuDRXXRhLDC16i8d8wQAy4jSYOypHojsAKGIH4LgMkiyKD5QzYDSAqfHuA+AMQvwXiz0D8B0nOB4hDkfhfGRBqPwHxbyCuRJIfBaNgFBADAG1ESZl9s8ZBAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJQAAAAaCAYAAABRhnV8AAAFDklEQVR4Xu2Zd4hkRRCHy5xzxLiCCbOigqLemjCiYMasYMKcUVTMGDAheCroHSiKGTEhZkH9Q0yYEWVNIIoBzNn6tqvv1dT0DPtm4W5v7Q+K6fpVT7/uN/26q9+IVCqVSqVSGSMbq10bxUplEM5Q+1LterV/Q6wy85imdkgUZ0eYRLvb5x8hNhlgXLtGcRZBXxaJojKHpNgVMTC7sZZM7lVpfUnjmzMGZgEnyuS+16NMlck9yIdk4ozvW5k4fWnNbpJu5pQYMDaTVOdHaba8nTpqDMY2kq57QgwYS6jdbrZAiN2idpTzd1a7V21fp5XgWrepbeA0vss2x9h+kzTWrV38VrXtrLyQ2p1qGzbhUTZSu1tt8aDDklEwVlKbrnaRNKviLtL05XVJfVnHYrCepPyp3yq6o9p9ascHfVlJfRwyf26109RuljSucXOepI5vaz578g1NeAbHSbowdT+28skdNdqxhqS28oTYX+3PJjwKk/dxKzNw6u9j/qfS5BGXqf0uqc2scYMiC0qK5ZzkYUkTGhjPWRa/y/wdLDYiTbvPqT0j6cf8RW1lq8PDdY2kB5J6Hvx3gga/qj1t5YWl+R7XPsf8S8xf22JXSppwl1o8sqkkfUvz9zM/84Xaiqbtpfa86fz+pfZakSeTn+lLqb3s/Aj1e60mY4UfgXb2dBo+k8L7/HAevx29ZZ/48Ubgx8kJrDw+iaUeP04m509MHs/79knsJys/ZX4ml6cFHfAPLGivBt9/r1f+9Ll9vi3d8dz/uBqiTVc7X20ZaSZUvL9oWwWtFTTwrpXnUTvatF6wXBIvnTraEG8erODKr0l3HNhm0BdTW840/LySZNAeCRrk6/L+jDYiD0j3dak3ZGVi2zchmcuVh+2TOh86nVQhthknI/i24BvprsNEH7Iyseua0Azt+6AB+g/SLAQ3meZZ17TYjzHDvkwD3MTL1Y6VtDr140zp7khbWA1pg+2hF8RLK8zf0nn9uJzD/KZxgyIHSIpl8ysEoJEIl2CFideK5C3V5zuPmubB/ytoEeqwIpfYQ7rbHDatlNeivxL8eH+fNH1gLpD2DbD0t/1OhBdxtLFKDDiI89I0gv6Z80v9ub+gRTaR9P4s1sM/JWgZVp1YP0LuGevgf13QOGT0IudrJPkl6HucECTg8dpwsCR9Tafhx/dXaEyqgWGvLHUA6EQJ6o9EsSU5fypxqH0SP8gHlKtM9/kevn/yspZzwJ+DnhN8WNW0DCcn3z4nOr+VEnvB+SVKExz/VCt/4LTDrezhUAFsTb6di9WWdj6xva3MwQAuND2CxvaZWd40DgGZmMqQnw0EjRwZNHKq0rIJ1Of0MV5o55igMYhzrczfOh+52OaSvuO3EkDLR3mvbSEp97nHNG4YJyo/GTkl+iN1TgEyMRchNhy0SHxH95L5q6kdJs1J7Su1T3Il42xpJtzV0rTDa5M3rAyru9jpaou6GHq+BjwmzYTL3CidfQT+SssaDx359EBwgzn50BgWs37PfJLqkCeMl3mleZ+FcXRG87xoMezZEAOS+Hhj4EFJelxN+MFye/9I5wkzwyQm/mbQe12rxHvSXIfJkLfBmK/lgwc2IunPdk9Oykt51HeSYicFnVWMseV2j+gMj8IqGscHOQVgpZ4p8DT3u6l5EP2Ml3iV/zlMBI65PL1PhFil0gpekDGh+Iui3+pUqYyZKWp3RLFSqVQqlUqlUqlUKhOI/wCDLG89Ly0NuAAAAABJRU5ErkJggg==>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAZCAYAAADnstS2AAAAqUlEQVR4XmNgGDJAAohl0AXRwUIg/g/FRWhyWIEmA0QxC7oENrCSAaKYKABS+BVdEBn0AHETlA1SXIMkBweVQPwLylZlQHiOHa4CClKhEhxIYpegYhgAJPgci9h3NDEGD6hEOpo4SKwBTYxhMwOmdSlIYpZAzAWTSEOSgAGQR2FiH5ElQOA3EBcyQEz5wwAJGZBiZSBehKQODtQYIO6HASEgdkTijwI6AQCURSXAcD7IXAAAAABJRU5ErkJggg==>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAaCAYAAAC+aNwHAAAAy0lEQVR4Xu2TsQ5BQRRER6XSqiVahW8Qrd6/+AGFUqXyIVoKlQbRqXSCkIggzObuS3bHPgrtO8k0M7M3797kAQXKgDpRL68rtafugVfLyt/IysoE5tc1UFxpqiZpwbKlBiFdWKmtARnBsrH4ESukP9+Rt1pEqtSkHtRW/CTusbv8nFpQN++Vw1Ie2f7uWCFr7/9kg3SxD/OrGiip/R0XmF/SQHGlmZrIHxzRg5U6GuBzQDRsSJ2pA+z6R+oZFkgD9mgH+z8qcVxQ8Cdv6xI9Jx1I6SMAAAAASUVORK5CYII=>

[image8]: <data:image/png;base64,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>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAbCAYAAACqenW9AAAAo0lEQVR4XmNgGNrgKhD/AeL/QMyJJocV7GWAKCYKgBSSpHg6uiA2IMUAUSyBLoENzGJAdUIbED9FE4MDZPceAmI+IF6FJIYCQIJzgfgSELNCxeYB8T24CiiQZECYnIMmhwEiGCAKQREDovegSqOC6wyobgOxpyDxUQBI8hoafyWU/RFJHAxAkmFo/GwgZgTiY0jiDGJQSWTgBxX7gCY+CgYbAADqfCrdk3T3XwAAAABJRU5ErkJggg==>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAYCAYAAAAVibZIAAABF0lEQVR4Xu2TsU4CQRCGJxKjICIFPAQdLfEReAILExJ63sDQyAsQQmXsLCwpCAWGgsRWMRA6WksTKTQkKP5zO6fj3G5Jd1/yJ/t/c7uXbO6IUvbNKbJCdsiTmcVcIWvkA2maWYIGucMOpbeR99+pY4mMVV8gj6r/o0zuwGPluHNiCqbHsCtaydgDmJzpM0o+w7C7sZLhwVzWNXJ3a/G9mPH6isg75AU5QXriNN7NFPAXgcE38qm67xnG6+siX42fiI/xbqaAz4q8NX4g/ly6dzOFfSSHxj2IP5J+L93CrmMl80zuDjVb5Ev1PLkDMsqdiQvCw76sW9IP/sYRU+RN9Q0FvlHNJbl//toOFFVkhHSRkpmlpOyDH+0CUjl+rWU1AAAAAElFTkSuQmCC>

[image11]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAaCAYAAAD1wA/qAAACNUlEQVR4Xu2WTahNURiG38hPBoQBSVyKgQwMDUQyNhFlKLpuRkb+kzKSgQxuMRAGJElkJBO3GKg7uWUm3WKAAZn4udf/9961lv3td/+c9tmuo5yn3s5e7/ettb+91tlrL6DP/8ts0yI1O7BBjX+Bb2rUsNo0I17/9IFe8x1ZYXW8RSicSvmrTO9/Z/SQy6Z7atZwE8VV+GjaLt5fR4vqBPM/iLcm+j1jF5oXwPwTaiL489RUuDucM82K7b2mM1m4a16aHqspLDBdMe03rUMomDucQv+smh52emTaiZD82bQM4WGazqbC/oNqOp6ZRuP1QWQvehkPTJNqeh7G3wMIgyyPbV7zRm3gGNvUjIyjWHSayDIuopif42T81YHnuutu4XjcPpXFCLEh8emdEi9xBB0eJMGkETVbwjEH1DSeoFhU2pmqJvAQin1KYdIWNVvCMbeqieBrUddKPM8F1Men2I36pOemH6b5CO/Na9N6hOW+ZHqXpebgmPvURPC/lnjpZS6r5b7pk5rKU5R3JlzymQjxw9FbEdsJFrDUtROvkG0mnuPI9x+J7dsI97rrYgnGz6up8EA3rKbgb3zadNW1qyZhD6pj1xFiXOmVyN6RLz7JwdhCNZuyFvllnUA4oRIezVlMFVUP0gR+Ev7EOFMv4jHX9oPeMh1FPu65Y7qhZkN4+t2hZjfwr+eP4S/c9UbTmGmT85Q2s7nE9EbNXjEH1V/sTrSZhGmBWzcPiE3YrEafPn264xc2q4PN0erGrAAAAABJRU5ErkJggg==>

[image12]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAaCAYAAAC6nQw6AAAA0UlEQVR4Xu2QMQ5BQRRFR0QlNoBSRWMBEo1CJdEpxRJENCIilqCSKGxFJDag0uppNRLu/f/98TxTKhRzkhOc9zJ/Pucikd/RhBtYlN8lOIdjmMuWwBTuYEU1TwEeYA8+4cqly2QhrQ7PMA/L0qqy49nL59ClC8v3KLkZ20U1wjYxLXkFwidyQTMKNN6KrWG6h8OjabyJPYg3tu0DDruBlr26blfTPAMXfgpbO9A68v2uB+Tkvg8K/T8t1WawpmYJD7g2bQtvphE2Hta3g0jkb3gB7yMuJV7Xm78AAAAASUVORK5CYII=>

[image13]: <data:image/png;base64,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>

[image14]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEQAAAAZCAYAAACIA4ibAAACP0lEQVR4Xu2VP0hXURTHT38wo2jQcBEi1CFwaU9oERrCwVxbG0oRBAVb7Ie4S6IQVjTpIA7aKE1NFUEUIW5iJf0BQ00dVNDz5dyLx/O71/eUN/yq+4Ev73e+57537zvv3PsjSiQSicrmLGvbmoom1lvWHuuVyf1TLJC8pFeIm3Q4d93EfwW3rZHBOsVfEv5946Gb3hivIhln7bCu2UQGsYLUkfi4auacX7FgX69R+cLzEivIAIX9F3TgXybpoGF3BbdYE6xmF4N21hSrW3me06xnrK+sIVbv4XQ+cBDOs5ZY503uuMQKMkNhf4wO/AbWUxejQ784H4WC10fStRdIXhzeqhsDzjgvFmdyifWT9Z5kgiKIFeQ1hf3HJH698hDbsehaeFXKe+g8T6eJwayJg2DyTdZLmyiAWEEmKeyPkvjoUg/iRRUDfDh7f4/xalwMjbCuqNyR4KDcZT2xiQKIFSR2hjynch8xtrDmm/M1XQHvrvO89JbKxHdKrrbKSawgN0h8e1iH/mUQfzIeDkk77oHxzqnfYJAkXzJ+JhdZy6x3rFMmd1xiBQHw7xhvg/XbeBj32XihDrFnxiNWv4rBR5Kinwicyh9I9m+1yeVli8oX7sHCsFU9KD7GXlUegIeO0KD17XN9B2DdoORizQ9Wq/FOBLYRvlytTUT4w/pO8iIQOg73N+pBJF8M23SaZPF6sW0khyfuR0esOB9XxPB/sVpI5sMc8DAv/iBKrA43Bs+G7lHBFP7ARCKRSCQS/yX7KdeoEM1m8xAAAAAASUVORK5CYII=>

[image15]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADMAAAAWCAYAAABtwKSvAAAAkUlEQVR4Xu3WsQ2CQByF8dPC4AAmrEBha2nhFs7AGjAGYQwdgJLGAYxuYGIriXyEylfZPvL/JV9zr7rqLqUQQliSgx4429CTOlr9Tr7WdKMHbWWzdqE35To4a2mgvQ7OavrSUQdHZZovc9bBSZXmS5x0cNLQhwodnFzpRTsdXEwPZU93ymSzM31nFvPyhxD+MwLN1xHWYB0oVwAAAABJRU5ErkJggg==>
