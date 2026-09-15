# **Architectural Design and Implementation Strategy for an AI-Driven Educational Content and Assessment Generation Pipeline**

The contemporary educational technology ecosystem is undergoing a fundamental paradigm shift. Traditional digital learning environments, often built as monolithic repositories using frameworks like Spring Boot or the MERN stack, have historically relied on manual content authoring1. As platforms scale, this manual approach creates an insurmountable bottleneck, limiting the volume, personalization, and adaptability of course materials. The demand for highly dynamic, algorithmically generated curriculum structures requires the integration of advanced artificial intelligence pipelines directly into the platform repository3.
Constructing a production-ready pipeline capable of ingesting broad topics, delineating them into granular sub-topics, generating robust banks of 60 to 80 assessment questions, and synthesizing complete lessons augmented with structural diagrams requires rigorous architectural oversight6. Naive approaches to large language model (LLM) integration—such as relying on zero-shot prompting to simultaneously generate text and assessments—fail to produce the structured, pedagogically valid, and reliable outputs required for enterprise deployment8. LLMs are inherently susceptible to hallucinating factual inaccuracies, defaulting to low-level cognitive assessments, and corrupting data schemas during extended generation sequences6.
This comprehensive report details an industry-standard architectural blueprint designed to automate the educational content generation lifecycle. By orchestrating specialized ingestion toolkits like Docling, schema-enforced generation via Pydantic and the instructor framework, deterministic mathematical distribution models, deterministic visual synthesis via Mermaid.js, and stateful workflow management via LangGraph, platforms can deploy resilient, autonomous educational pipelines that maintain rigorous human-in-the-loop oversight.

## **System Architecture and Repository Integration Blueprint**

Integrating a highly complex generative pipeline into an existing educational platform repository necessitates a decoupled, asynchronous microservices architecture. Embedding computationally intensive LLM orchestration and document parsing directly within a primary application thread (e.g., a Node.js Express server or Java Spring Boot controller) introduces unacceptable latency and risks system instability1.
The industry standard approach isolates the artificial intelligence pipeline as a dedicated, stateful backend service—typically authored in Python to leverage the native ecosystems of Docling, Pydantic, and LangGraph11. Communication between the primary platform repository and the generative microservice is mediated through asynchronous message brokers and webhook callbacks, ensuring that the user experience remains responsive while background generation tasks execute2.

| Architectural Component | Technology Stack | Operational Responsibility |
| :---- | :---- | :---- |
| **Primary Backend** | Spring Boot / Node.js (MERN) | Manages user authentication, core relational database storage, and API routing1. |
| **Message Broker** | Redis / RabbitMQ / Kafka | Queues asynchronous document ingestion and generation jobs3. |
| **Generative Microservice** | Python (FastAPI / Flask) | Executes the LangGraph state machine, invoking Docling, Instructor, and LLM endpoints11. |
| **Vector Storage** | OpenSearch / ChromaDB | Indexes semantically chunked document data for retrieval-augmented generation11. |
| **Primary Database** | PostgreSQL / MongoDB | Persists the final generated curriculum trees, Markdown lessons, and structured quiz arrays2. |

The end-to-end pipeline operating within this microservice architecture is categorized into five highly specialized phases: high-fidelity document ingestion, algorithmic curriculum structuring, automated item generation, diagrammatic lesson synthesis, and stateful orchestration.

## **Phase 1: High-Fidelity Document Ingestion and Hierarchical Chunking**

The baseline capability of any content synthesis pipeline is defined by the quality of its initial data extraction. Traditional Optical Character Recognition (OCR) systems flatten intricate educational documents into unstructured text strings. This destructive process strips away pedagogical context, such as section hierarchies, tabular data, and visual captions, severely degrading the downstream LLM's ability to comprehend the source material15.
To mitigate this, the architecture standardizes document processing around Docling, an open-source parsing toolkit optimized for generative artificial intelligence workflows14. Docling transforms diverse, complex formats—including PDFs, DOCX, PPTX, and HTML—into a unified, machine-readable structured format known as a DoclingDocument14.

### **Multimodal Parsing and Structural Preservation**

Docling operates by dynamically identifying the ingested file format and selecting the optimal processing backend. For digitally born documents, it utilizes native extraction pathways, avoiding the computational overhead of visual models15. For scanned materials or complex layouts featuring multi-column text and merged cells, the pipeline leverages specialized layout and table recognition models, such as TableFormer11. Developers can explicitly configure these extraction pipelines using parameter flags such as do\_table\_structure and do\_ocr to tailor the ingestion process to the platform's specific content profile11.
The preservation of structure is paramount for educational content generation. For example, when parsing a chemistry textbook, the relationships between main concepts (H1 headers), sub-concepts (H2 headers), and constants (data tables) dictate the logical flow of the subject14. The resulting DoclingDocument retains this hierarchy, allowing the data to be exported losslessly into JSON or Markdown formats14. This ensures that when the LLM is subsequently tasked with synthesizing lessons, it has access to the precise spatial and logical relationships authored in the original text17.

### **Advanced Semantic Chunking Methodologies**

Following the extraction of a structured DoclingDocument, the content must be segmented into discrete chunks. These chunks must fit within the strict context window token limits of embedding models and generative LLMs while maintaining absolute semantic coherence16. Naive character-splitting algorithms arbitrarily truncate sentences and sever data tables from their headers, destroying meaning15. The integration of Docling provides specialized chunking algorithms that operate natively on the document's structured object model19.

| Chunking Strategy | Mechanism of Action | Optimal Use Case |
| :---- | :---- | :---- |
| **Hierarchical Chunker** | Segments content based on natural document breaks, such as sections, paragraphs, and figures, embedding the parent hierarchy in the chunk metadata14. | Preserving the logical flow of narrative textbook chapters for sub-topic generation17. |
| **Line-Based Token Chunker** | Preserves line boundaries within a defined token limit, omitting prefixes only upon strict overflow conditions19. | Processing code blocks, logs, and structured lists within technical computer science courses19. |
| **Hybrid Chunker** | Applies tokenization-aware refinements over the hierarchical base, recursively splitting oversized chunks while merging smaller, compatible peers14. | General-purpose ingestion where both semantic integrity and strict LLM token limits are critical16. |

For an automated educational pipeline, the HybridChunker represents the optimal standard. It features advanced handling capabilities for structured data, specifically tables. When a large table spans multiple chunks, the HybridChunker intelligently repeats the table headers in subsequent segments15. Consequently, when an LLM evaluates a fragmented tabular chunk to formulate a multiple-choice question, it retains the contextual schema of the data columns, preventing hallucinated interpretations19.

### **Vectorization and Contextual Indexing**

To support dynamic generation and future curriculum updates, the generated chunks must be persistently indexed. The pipeline interfaces the chunked DoclingDocument outputs with an enterprise-grade vector database, such as OpenSearch or ChromaDB11. The system generates high-dimensional vector embeddings for each text chunk using standardized embedding models (e.g., OpenAI or HuggingFace tokenizers), storing these vectors alongside the rich hierarchical metadata captured by Docling16.
This architectural pattern enables hybrid search capabilities—combining k-Nearest Neighbor (k-NN) semantic search with BM25 keyword matching—to drastically improve retrieval precision17. When the generation pipeline initiates the creation of a specific sub-topic lesson, it executes a targeted query against the vector store. Because the metadata retains the document hierarchy, the retrieval system can employ context expansion, automatically pulling adjacent chunks from the parent section to provide the LLM with a complete, coherent foundation for synthesis14.

## **Phase 2: Curriculum Structuring and Sub-Topic Generation**

Once the repository's foundational materials are ingested and indexed, the pipeline proceeds to synthesize a structured curriculum ontology. The objective of this phase is to accept a broad subject matter input and algorithmically decompose it into a logical, hierarchical progression of sub-topics.

### **Algorithmic Curriculum Mapping**

The curriculum generation process begins by querying the vector database for the structural metadata preserved during the Docling extraction phase. The pipeline aggregates the primary headers (H1, H2, and H3 elements) to form a skeletal syllabus outline17. An LLM, operating under strict prompt constraints, is then deployed to refine this raw outline into a cohesive pedagogical sequence.
The prompt engineering for this phase explicitly directs the model to consolidate redundant nodes, expand upon overly dense thematic areas, and enforce a strict prerequisite progression. The model must output this sequence according to a predefined JSON schema representing a directed acyclic graph, ensuring the curriculum tree can be natively ingested by the platform's relational database2.

### **Importance Weighting and Deterministic Distribution**

A core requirement for the educational pipeline is the generation of a substantial assessment bank—specifically 60 to 80 multiple-choice questions—that must be proportionally distributed across the generated sub-topics based on their relative importance. Employing a flat distribution strategy (e.g., arbitrarily assigning 10 questions to every sub-topic) severely compromises assessment validity. Minor tangential subjects become over-tested, while foundational core concepts are under-evaluated6.
To programmatically resolve this, the pipeline calculates a continuous "Importance Weight" (![][image1]) for each sub-topic. This weight is derived via a multi-factor analytical approach:

> 1. **Semantic Token Mass:** The system queries the vector database to calculate the total token volume associated with a sub-topic's semantic cluster. A sub-topic that constitutes 45% of the source material's mass is empirically assigned a higher weight than one constituting 5%.
> 2. **LLM Foundational Evaluation:** A dedicated LLM evaluation pass is executed, prompting the model to score each sub-topic (from 0.0 to 1.0) based on its criticality as a prerequisite for subsequent topics.
> 3. **Graph Centrality Metrics:** Utilizing the generated curriculum tree, nodes with a higher degree of outbound edges (indicating they serve as foundational knowledge for many future sub-topics) are mathematically weighted higher.

These variables are synthesized and normalized to ensure that the sum of all weights equals exactly 1.0 (![][image2]). To determine the exact number of questions per sub-topic (![][image3]) given a target total pool (![][image4], e.g., 80 questions), the pipeline multiplies the total pool by the normalized weight (![][image5]).
Because this operation inevitably produces fractional targets, standard rounding algorithms are insufficient, as they frequently result in a final sum that deviates from the strict total quota. To guarantee exact integer distribution, the architecture implements the **Largest Remainder Method**22.
Consider a scenario where the pipeline must distribute exactly 80 questions across Sub-topics Alpha, Beta, and Gamma, with calculated weights of 0.46, 0.33, and 0.21 respectively.

> * **Unrounded Quotas:** Alpha \= 36.8, Beta \= 26.4, Gamma \= 16.8.
> * **Lower Bounds (Guaranteed Items):** The system isolates the integer portion. Alpha \= 36, Beta \= 26, Gamma \= 16\. The sum of these integers is 78, leaving a deficit of 2 questions.
> * **Remainder Isolation:** The fractional components are Alpha (0.8), Beta (0.4), and Gamma (0.8).
> * **Deficit Allocation:** The remaining 2 questions are allocated one-by-one to the sub-topics with the largest fractional remainders. Alpha and Gamma tie for the largest remainder, so each receives one additional question22.
> * **Final Integer Quotas:** Alpha \= 37, Beta \= 26, Gamma \= 17\. The sum is precisely 80\.

This deterministic mathematical allocation guarantees that the downstream assessment generator receives precise, integer-based targets, ensuring structural stability throughout the generation loops22.

## **Phase 3: Automated Item Generation (AIG) via Structured Outputs**

The synthesis of 60 to 80 high-quality multiple-choice questions represents the most computationally and pedagogically complex phase of the architecture. Traditional text-based LLM generation is critically flawed for Automated Item Generation (AIG)7. When permitted to generate raw text, LLMs frequently hallucinate incorrect answers, formulate mathematically or logically invalid distractors, exhibit severe response distribution bias (e.g., disproportionately assigning 'C' as the correct option), and consistently violate JSON formatting, causing catastrophic parsing failures in the backend6.
To achieve enterprise-grade reliability, the architecture abandons raw text generation in favor of forced structured outputs, leveraging the instructor Python library built atop the Pydantic data validation framework13.

### **Enforcing Strict Schemas with Pydantic and Instructor**

Pydantic provides sophisticated data validation and settings management by enforcing Python type hints at runtime, generating rigorous JSON schemas from class definitions12. The instructor framework acts as an intermediary between Pydantic and the LLM API, translating the Pydantic models into strict tool-calling or JSON-mode schemas13.
This ensures the LLM's output is not merely a string of text, but a strongly typed data object. If the LLM generates an invalid schema, hallucinates a data type, or violates a custom validation rule, Pydantic immediately raises a ValidationError. The instructor library intercepts this error, appends the precise failure context to the prompt, and automatically re-queries the LLM to correct its mistake without developer intervention20.
For this educational pipeline, assessment items are defined using complex, nested Pydantic schemas.

| Schema Field | Type Hint | Architectural Function and Validation Logic |
| :---- | :---- | :---- |
| question\_stem | str | The primary interrogative body. Validated for length constraints and clarity. |
| options | List\[str\] | The answer choices. Enforced to contain exactly four unique strings28. |
| correct\_index | int | The zero-based array index identifying the correct option. Enforced to be between 0 and 3\. |
| blooms\_level | Enum | The cognitive depth classification. Enforced to match predefined taxonomy constants28. |
| correct\_rationale | str | Explicit explanation of the correct option. |
| distractor\_rationale | List\[str\] | Detailed reasoning outlining why each specific distractor is incorrect, mapping to common student misconceptions. |

Crucially, the prompt engineering mandates that the LLM generates the correct\_rationale and distractor\_rationale fields *prior* to finalizing the options array. This technique forces the LLM to execute a Chain-of-Thought reasoning process29. By explicitly articulating why a wrong answer is plausible but incorrect before generating the text of the wrong answer, the system drastically reduces the incidence of nonsensical or overly transparent distractors—a pervasive flaw in AI-generated multiple-choice items6.

### **Cognitive Calibration and Bloom's Taxonomy Alignment**

Pedagogically sound assessments do not exclusively evaluate rote memorization; they must measure higher-order cognitive capabilities30. Research indicates that without strict systemic constraints, LLMs default to generating low-complexity, factual recall items, severely limiting the assessment's validity6.
To rectify this, the Pydantic generation schema natively incorporates the Revised Bloom's Taxonomy of Educational Objectives30. The pipeline dynamically adjusts the prompting strategy based on the target sub-topic and its calculated importance weight, explicitly instructing the model to distribute the cognitive load31.

| Cognitive Classification | Description & Targeted AI Execution | Prompt Action Verbs |
| :---- | :---- | :---- |
| **Remember** | Recognizing explicit knowledge from long-term memory. The AI extracts and reformulates direct facts from the Docling chunks. | Define, duplicate, list, memorize, state.32 |
| **Understand** | Constructing meaning from instructional messages. The AI must interpret data, translate concepts, or summarize text. | Classify, describe, discuss, explain, interpret.32 |
| **Apply** | Executing a procedure within a novel situation. The AI generates unique scenarios requiring the application of a learned rule or formula. | Calculate, demonstrate, employ, illustrate, solve.32 |
| **Analyze** | Deconstructing material and determining relational hierarchies. The AI formulates complex, multi-step logical reasoning problems. | Appraise, compare, contrast, differentiate, test.32 |
| **Evaluate** | Making judgments based on specific criteria. The AI presents competing hypotheses and tasks the student with determining the optimal approach. | Argue, assess, defend, judge, value.32 |

Foundational introductory sub-topics may receive a higher distribution quota of "Remember" and "Understand" items, while advanced, heavily weighted sub-topics trigger prompts designed to synthesize "Apply" and "Analyze" questions10.

### **Systemic Mitigation of Item-Writing Flaws**

Automated item generation is chronically vulnerable to established item-writing flaws (IWFs), which compromise test integrity by providing unintended clues to the test-taker10. These flaws include cueing (where the longest option is statistically correct), absolute terminology (using "always" or "never" exclusively in incorrect options), and the inclusion of lazy fallbacks like "All of the above"34.
The pipeline leverages Pydantic's custom field validators @field\_validator to algorithmically detect and reject these flaws during the generation cycle20.

> 1. **Format Rejection:** Validators scan the options array, immediately rejecting any output containing the strings "All of the above", "None of the above", or True/False binary structures34.
> 2. **Length-Based Cueing Prevention:** A validator calculates the character length of the option identified by the correct\_index. If this length exceeds the mean length of the remaining distractors by a predefined threshold (e.g., 40%), the validator raises an exception, forcing the instructor loop to rewrite the item34.
> 3. **Semantic Overlap Detection:** To prevent overlapping distractors, the system can rapidly calculate cosine similarity between the options. If two distractors are highly synonymous, a ValidationError triggers regeneration6.

This robust, self-healing validation loop operates continuously in the background, ensuring that the final output batch of 60 to 80 questions is structurally flawless and ready for database insertion without manual structural formatting4.

## **Phase 4: Lesson Synthesis and Diagrammatic Generation**

Parallel to the assessment generation, the architecture synthesizes the retrieval-augmented text chunks into comprehensive, consumable lessons mapped to each sub-topic. This phase transforms the highly structured JSON data extracted by Docling into narrative Markdown suitable for rendering on the platform's frontend frameworks2.

### **Markdown Synthesis and Pedagogical Formatting**

The LLM is provided with the sub-topic title, the overarching curriculum map, and the highly relevant semantic chunks retrieved from the OpenSearch vector database. The system utilizes a system prompt tailored to the desired instructional tone, mandating the output strictly as Markdown18.
The lesson generation follows a standardized pedagogical template:

> 1. **Learning Objectives:** Explicitly stating the intended cognitive outcomes, mapped to Bloom's Taxonomy32.
> 2. **Core Exposition:** Delivering the primary thematic material. Crucially, because Docling preserves the original structure of tables and lists, the prompt instructs the LLM to inject these tables directly into the Markdown flow, avoiding the data corruption common when LLMs attempt to reconstruct tables from flattened text14.
> 3. **Applied Examples:** Grounding theoretical frameworks in practical case studies.
> 4. **Summary Consolidation:** A concise review synthesizing the lesson ahead of the subsequent quiz evaluation.

### **Dynamic Visual Generation via Mermaid.js**

Modern educational platforms require engaging visual aids; text-dense AI-generated lessons suffer from significant drop-offs in user retention7. To fully automate the creation of visual assets without relying on computationally expensive and uneditable pixel-based image generators, the architecture implements Mermaid.js36.
Mermaid.js is a sophisticated JavaScript-based diagramming tool that utilizes Markdown-inspired text syntax to render complex scalable vector graphics (SVGs) directly in the browser36. Because Mermaid relies exclusively on plain text, LLMs are highly proficient at generating it, and the resulting syntax can be efficiently stored alongside the lesson text in the primary database38. Depending on the sub-topic context, the LLM generates syntax for flowcharts, sequence diagrams, state machines, or entity-relationship models.

### **The Self-Healing Syntax Validation Loop**

While LLMs demonstrate high competence in Mermaid generation, they occasionally hallucinate unsupported syntax, omit structural brackets, or introduce cyclic dependency errors37. If an invalid Mermaid block is committed to the database, the platform frontend will fail to render the SVG, displaying an error to the user.
To guarantee absolute visual reliability, the pipeline introduces a dedicated syntax validation node. When the LLM generates a Mermaid block within the Markdown lesson, the specific syntax string is isolated and passed to a programmatic validator, such as the mermaid-parser-py library or a Model Context Protocol (MCP) Mermaid validation server39.

> 1. **Parsing Execution:** The validator processes the text block against the official Mermaid grammar rules39.
> 2. **Error Trapping:** If the parser detects an anomaly (e.g., Parse error on line 4: Unrecognized token), the pipeline traps the error output39.
> 3. **Algorithmic Remediation:** The original, flawed Mermaid code and the explicit parser error message are concatenated and returned to the LLM via a feedback prompt. The LLM is instructed to identify the syntax error and return a corrected block39.
> 4. **Commitment:** This loop iterates rapidly until the validator returns a success code. Only then is the Mermaid block injected into the final lesson payload42.

This automated syntax validation ensures the platform never deploys corrupted assets, maintaining the professional integrity of the learning environment41.

## **Phase 5: Stateful Orchestration and Human-in-the-Loop (LangGraph)**

Executing the comprehensive sequence outlined above—document ingestion, curriculum graphing, mass item generation with validation, and lesson synthesis with diagrammatic self-healing—requires orchestrating multiple, interdependent LLM calls and validation scripts. Attempting to manage this complexity through linear execution scripts or standard LangChain sequences leads to fragile pipelines that crash mid-execution, losing significant computational progress43.
To manage this intricate multi-agent workflow, the architecture standardizes on LangGraph. LangGraph models the application as a highly controllable, cyclical directed graph42.

### **State Management and Graph Construction**

In LangGraph, individual operational steps are defined as Nodes (e.g., "Parse Document", "Generate Quiz Item", "Validate Mermaid"), while conditional logic routing the execution flow is defined by Edges44. The entire execution sequence revolves around a global typed state schema (often defined via Pydantic). As each Node executes, it updates specific fields within the state object, incrementally constructing the final educational module44.
The operational architecture of the graph is constructed as follows:

| LangGraph Node | Operational Function | Routing Edge Logic |
| :---- | :---- | :---- |
| Ingestion\_Node | Invokes the Docling container to parse documents and populate the vector store. | Always proceeds to the Curriculum\_Node. |
| Curriculum\_Node | Generates the hierarchical curriculum tree and executes the Largest Remainder distribution matrix. | **Interrupt:** Pauses execution for Human-in-the-Loop approval45. Upon resumption, fans out execution to Lesson\_Node and Quiz\_Node. |
| Lesson\_Node | Generates narrative Markdown and synthesizes initial Mermaid strings. | Routes to Mermaid\_Validator\_Node. |
| Mermaid\_Validator\_Node | Evaluates syntax via mermaid-parser-py. | If invalid, routes back to Lesson\_Node for correction. If valid, proceeds40. |
| Quiz\_Node | Iterates through sub-topics, generating constrained items via the instructor library. | Loops internally to handle Pydantic ValidationErrors20. Upon completing the quota, proceeds to QA\_Review\_Node. |
| QA\_Review\_Node | Aggregates the completed JSON assessment objects and Markdown lessons. | **Interrupt:** Pauses for final Human-in-the-Loop audit45. |
| Commit\_Node | Serializes data for REST API insertion into the platform's primary database. | Terminates graph execution. |

### **Implementing Human-in-the-Loop (HITL) Oversight**

Despite the rigorous algorithmic constraints and validation loops, educational content demands absolute pedagogical safety and factual accuracy5. Generating 80 questions entirely autonomously introduces an unacceptable risk vector into a production environment, as subtle contextual errors may bypass programmatic validation4.
LangGraph features robust Human-in-the-Loop (HITL) capabilities facilitated through its persistence layer (checkpointers)44. The persistence layer saves the entire state of the graph to a database (such as SQLite or PostgreSQL) at every step, allowing execution to be suspended and resumed indefinitely44.
The pipeline utilizes this mechanism to insert two mandatory review checkpoints:

> 1. **Strategic Curriculum Review:** Before the system commits extensive compute resources to generating 80 complex quiz items and lengthy lessons, the graph hits an interrupt node45. The state is serialized, and a webhook alerts the primary platform backend. An instructional designer accesses a dashboard to review the proposed sub-topics and their assigned importance weights. The designer can manually alter a weight or redefine a sub-topic title. Upon saving, the platform sends a REST call back to the AI microservice, updating the state and resuming the graph with the human-optimized parameters45.
> 2. **Final Quality Assurance (QA) Audit:** Once the rigorous generation cycles conclude, the graph pauses again45. The platform's frontend renders the 80 generated items—easily parsed due to their strict JSON schema compliance—into an audit table8. The human reviewer can evaluate the distractor\_rationales, preview the Mermaid diagrams, and flag specific items for deletion or manual revision4. If 5 items are rejected, the designer can trigger the graph to loop back and regenerate the missing quota4. Only after final human sign-off does the graph proceed to the Commit\_Node.

This robust orchestration methodology directly maps the AI outputs to standard platform schemas, seamlessly integrating the generated Course, SubTopic, and Quiz collections into the overarching MERN or Spring Boot repository architecture without requiring manual data wrangling1.

## **Conclusion**

Transitioning an educational platform from a static repository to an autonomous, AI-driven generation ecosystem represents a highly complex engineering challenge. Relying on basic prompt engineering to generate dense curriculum maps, extensive question banks, and structural diagrams inevitably fails to meet the stringent quality, formatting, and pedagogical standards required for production deployment.
By implementing the sophisticated microservice architecture detailed in this report, development teams can achieve unprecedented scaling while enforcing rigorous quality controls. High-fidelity document ingestion via Docling ensures that critical layout elements, table structures, and reading hierarchies are not lost during vectorization, providing a superior semantic baseline14. The utilization of deterministic mathematics, such as the Largest Remainder Method, alongside Bloom's Taxonomy frameworks ensures that the generation of 60 to 80 assessment items is mathematically precise and cognitively balanced22.
Furthermore, the enforcement of stringent JSON schemas through Pydantic and the instructor framework fundamentally eliminates the structural instability inherent to LLMs, programmatically rejecting item-writing flaws and hallucinated data types20. The integration of self-healing Mermaid.js validation loops ensures visually engaging, error-free diagrammatic assets37. Crucially, the holistic orchestration of these systems via LangGraph state machines provides necessary Human-in-the-Loop oversight checkpoints, merging the autonomous speed of generative artificial intelligence with the essential pedagogical authority of human educators44. This architectural design constitutes the current industry standard, establishing a resilient and highly extensible foundation for next-generation educational technology platforms.

#### **Works cited**

> 1. STUDY STREAM – JAVA SPRING BOOT BASED E-LEARNING, [https://github.com/Ayushkhodankar/StudyStream](https://github.com/Ayushkhodankar/StudyStream)
> 2. Muskansahuincredible/StudyNotion-An-Online-Education-Platform, [https://github.com/Muskansahuincredible/StudyNotion-An-Online-Education-Platform](https://github.com/Muskansahuincredible/StudyNotion-An-Online-Education-Platform)
> 3. education-platform · GitHub Topics, [https://github.com/topics/education-platform](https://github.com/topics/education-platform)
> 4. Expanding the Team: Integrating Generative Artificial Intelligence, [https://www.mdpi.com/2076-3417/15/18/9976](https://www.mdpi.com/2076-3417/15/18/9976)
> 5. AI-Assisted Model for Generating Multiple-Choice Questions \- arXiv, [https://arxiv.org/pdf/2602.08383](https://arxiv.org/pdf/2602.08383)
> 6. Evaluating the ability of AI models to generate level-specific medical, [https://pmc.ncbi.nlm.nih.gov/articles/PMC12934029/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12934029/)
> 7. Reliable generation of isomorphic physics problems using ... \- arXiv, [https://arxiv.org/pdf/2508.14755](https://arxiv.org/pdf/2508.14755)
> 8. Generating Structured Outputs from LLMs \- Towards Data Science, [https://towardsdatascience.com/generating-structured-outputs-from-llms/](https://towardsdatascience.com/generating-structured-outputs-from-llms/)
> 9. Scalable Generation and Validation of Isomorphic Physics Problems, [https://arxiv.org/html/2602.05114v2](https://arxiv.org/html/2602.05114v2)
> 10. Crowdsourcing the Evaluation of Multiple-Choice Questions Using, [https://dev.stamper.org/publications/LS2023Moore.pdf](https://dev.stamper.org/publications/LS2023Moore.pdf)
> 11. Docling: A Guide to Building a Document Intelligence App | DataCamp, [https://www.datacamp.com/tutorial/docling](https://www.datacamp.com/tutorial/docling)
> 12. How to Use Pydantic for LLMs: Schema, Validation & Prompts, [https://pydantic.dev/articles/llm-intro](https://pydantic.dev/articles/llm-intro)
> 13. Bridging Language Models with Python with Instructor, Pydantic, [https://medium.com/@jxnlco/bridging-language-model-with-python-with-instructor-pydantic-and-openais-function-calling-f32fb1cdb401](https://medium.com/@jxnlco/bridging-language-model-with-python-with-instructor-pydantic-and-openais-function-calling-f32fb1cdb401)
> 14. Building powerful RAG pipelines with Docling and OpenSearch, [https://opensearch.org/blog/building-powerful-rag-pipelines-with-docling-and-opensearch/](https://opensearch.org/blog/building-powerful-rag-pipelines-with-docling-and-opensearch/)
> 15. What Is Docling? Document Parsing for RAG Explained \- Cody AI, [https://meetcody.ai/blog/docling-document-parser-rag-guide/](https://meetcody.ai/blog/docling-document-parser-rag-guide/)
> 16. Building Your Own Data Parser with Docling \- DEV Community, [https://dev.to/gathu17/building-your-own-data-parser-with-docling-1co9](https://dev.to/gathu17/building-your-own-data-parser-with-docling-1co9)
> 17. Beyond Basic Chunks: Supercharge Your RAG with Docling and, [https://alain-airom.medium.com/beyond-basic-chunks-supercharge-your-rag-with-docling-and-opensearch-a07aed56179e](https://alain-airom.medium.com/beyond-basic-chunks-supercharge-your-rag-with-docling-and-opensearch-a07aed56179e)
> 18. docling \- Skill | Smithery, [https://smithery.ai/skills/enuno/docling](https://smithery.ai/skills/enuno/docling)
> 19. Chunking \- Docling \- GitHub Pages, [https://docling-project.github.io/docling/concepts/chunking/](https://docling-project.github.io/docling/concepts/chunking/)
> 20. Instructor \- Multi-Language Library for Structured LLM Outputs, [https://python.useinstructor.com/](https://python.useinstructor.com/)
> 21. Improving Learning Outcomes through Well Designed MCQ Tests, [https://www.qeios.com/read/133VY7](https://www.qeios.com/read/133VY7)
> 22. Cognitively Grounded Multi-Agent Social Simulation with Anchoring, [https://www.researchgate.net/publication/404838026\_ScioMind\_Cognitively\_Grounded\_Multi-Agent\_Social\_Simulation\_with\_Anchoring-Based\_Belief\_Dynamics\_and\_Dynamic\_Profiles](https://www.researchgate.net/publication/404838026_ScioMind_Cognitively_Grounded_Multi-Agent_Social_Simulation_with_Anchoring-Based_Belief_Dynamics_and_Dynamic_Profiles)
> 23. Structured generation with instructor \- Distilabel Docs, [https://distilabel.argilla.io/1.5.2/sections/pipeline\_samples/examples/mistralai\_with\_instructor/](https://distilabel.argilla.io/1.5.2/sections/pipeline_samples/examples/mistralai_with_instructor/)
> 24. JSON Schema | Pydantic Docs, [https://pydantic.dev/docs/validation/dev/concepts/json\_schema/](https://pydantic.dev/docs/validation/dev/concepts/json_schema/)
> 25. Models | Pydantic Docs, [https://pydantic.dev/docs/validation/dev/concepts/models/](https://pydantic.dev/docs/validation/dev/concepts/models/)
> 26. Structured output with Instructor \- Writer AI Studio, [https://dev.writer.com/home/integrations/instructor](https://dev.writer.com/home/integrations/instructor)
> 27. Pydantic: Simplifying Data Validation in Python Quiz, [https://realpython.com/quizzes/python-pydantic/](https://realpython.com/quizzes/python-pydantic/)
> 28. Using Pydantic Models for Structured Outputs \- Instructor, [https://python.useinstructor.com/concepts/models/](https://python.useinstructor.com/concepts/models/)
> 29. Automatic Generation of Inference Making Questions for Reading, [https://aclanthology.org/2025.bea-1.31.pdf](https://aclanthology.org/2025.bea-1.31.pdf)
> 30. (PDF) Automatic generation of physics items with Large Language, [https://www.researchgate.net/publication/384865973\_Automatic\_generation\_of\_physics\_items\_with\_Large\_Language\_Models\_LLMs](https://www.researchgate.net/publication/384865973_Automatic_generation_of_physics_items_with_Large_Language_Models_LLMs)
> 31. Automatic generation of physics items with Large Language Models, [https://journal.uny.ac.id/index.php/reid/article/view/76864](https://journal.uny.ac.id/index.php/reid/article/view/76864)
> 32. Bloom's Taxonomy of Educational Objectives, [https://teaching.uic.edu/cate-teaching-guides/syllabus-course-design/blooms-taxonomy-of-educational-objectives/](https://teaching.uic.edu/cate-teaching-guides/syllabus-course-design/blooms-taxonomy-of-educational-objectives/)
> 33. Misclassification Analysis in Automated Bloom's Taxonomy Classifiers, [https://www.icck.org/article/abs/jse.2026.118512](https://www.icck.org/article/abs/jse.2026.118512)
> 34. We Trained an AI Model That Writes Better Multiple Choice, [https://questionwell.org/blog/we-trained-an-ai-model-that-writes-better-multiple-choice-questions-heres-the-evidence](https://questionwell.org/blog/we-trained-an-ai-model-that-writes-better-multiple-choice-questions-heres-the-evidence)
> 35. Docling integration \- Docs by LangChain, [https://docs.langchain.com/oss/python/integrations/document\_loaders/docling](https://docs.langchain.com/oss/python/integrations/document_loaders/docling)
> 36. mermaid-js/mermaid: Generation of diagrams like ... \- GitHub, [https://github.com/mermaid-js/mermaid](https://github.com/mermaid-js/mermaid)
> 37. Diagram Syntax | Mermaid, [https://mermaid.ai/open-source/intro/syntax-reference.html](https://mermaid.ai/open-source/intro/syntax-reference.html)
> 38. Generating MermaidJS Programmatically in Python \- DevTools daily, [https://www.devtoolsdaily.com/blog/build-mermaidjs-markup-in-python/](https://www.devtoolsdaily.com/blog/build-mermaidjs-markup-in-python/)
> 39. @rtuin/mcp-mermaid-validator \- npm, [https://www.npmjs.com/package/@rtuin/mcp-mermaid-validator](https://www.npmjs.com/package/@rtuin/mcp-mermaid-validator)
> 40. mermaid-py-parser \- PyPI, [https://pypi.org/project/mermaid-parser-py/](https://pypi.org/project/mermaid-parser-py/)
> 41. lvy010/mermaid-validator: Ensure 100% correct Mermaid ... \- GitHub, [https://github.com/lvy010/mermaid-validator](https://github.com/lvy010/mermaid-validator)
> 42. LangGraph Test Automation: Planner-Generator-Healer Pipeline, [https://scrolltest.com/langgraph-test-automation-planner-generator-healer/](https://scrolltest.com/langgraph-test-automation-planner-generator-healer/)
> 43. What is LangGraph \- GeeksforGeeks, [https://www.geeksforgeeks.org/machine-learning/what-is-langgraph/](https://www.geeksforgeeks.org/machine-learning/what-is-langgraph/)
> 44. LangGraph: a guide to stateful AI agent orchestration, [https://mastra.ai/articles/langgraph](https://mastra.ai/articles/langgraph)
> 45. LangGraph Human-in-the-Loop: Add Approval Steps, [https://machinelearningplus.com/gen-ai/langgraph-human-in-the-loop-approval-steps/](https://machinelearningplus.com/gen-ai/langgraph-human-in-the-loop-approval-steps/)
> 46. Human-in-the-loop \- Docs by LangChain, [https://docs.langchain.com/oss/python/langchain/human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABkAAAAZCAYAAADE6YVjAAABNElEQVR4Xu2TTytEURjG32KrsDHyAfgQg43FpGRvwZSN1aR8AUqxVXYWNixk6TNYioUsbKTY2VAk8ud5Ou/U2+PcOzOhlPnV08x5f3eee+7tjFmXv0gPco98hNy5G0MexV26Izfi5oLL8mTpwhzNkhxLyIoOiziz4qKym7zqoIxDS0XDMp9H3t0p28igDsvYsFQ0LvNn5Nhdr7gLWbdk0VJRPcz2kT5kz91ocOfhe9tMWipaD7MT/1xzN+3rAUuvqmNGLBUd+Po6uAV3DV+/BKfE32VhEXdfQTbDvOpuC5lCZoNT+NSlsOgBeZM5TxzdUcZ1DIsY7lZpuiEVTs3SKazL/AssKXrfdFc6DOwiM8ipCoVFPDk56FrB/xQP0K/Szka+xSqyg0zI/EfpR26RZRVd/imfDgdPUixjsZ8AAAAASUVORK5CYII=>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFgAAAAZCAYAAAC1ken9AAACpElEQVR4Xu2Y26sOURjGHxFuEGHb+QOcXXCLTbmiuECOOeTCmW1v5cKVUti5UYoSbSHJjZI/waW4EHEjIYkSIYcc3se7pm99r2/WN2tm72Y286un+eZ9Zq1vzZo176y1gJqaf4EVolWiNaK1onVO6zOqpg2/nDaJZopmOPH3LNEc0TzRYtFh0R2vDDUfNUEmoNFZMcyGlnlrDcdw0Xs0P4zk2umiT8Z74jzywngbPK9sDol22WA7jkJvhB0SS7sH8xnp14Qe7E5Rrw2WxDXRNzTau7vZzsY7aOET1mjDEoT/8D7SOzHUwd9toCLk7mCS3PBkaxTgBrTOThPfLPrpPMsZaOqqIoU6eC7CoyoPx6H1LTTxL2h8MEcY76E5rxKFOpjchFbif3SKsB1a31YvdlU0RnTFedM874H3u4oU7mDyA1rRRmvkoAta1zEvdtcdk4/rMnc+HpoeinA5oEuiftFF0QXRedGoP6Wyw/buscFYOMVKUoV9fWOZCq3nujt/5nlbnLffnfNLnUY//k4zZcD27rPBPKyGVjbSGjlgPRy1U9A8S1ngvNOipaKVnmc5YgMl4Q+IQjyCLggGAjbqAzT1+HBmQe9WCy8vfZEaq8Uyw/Z222As50Q7bLAASbrhKLUkXoc1HMyR90SPrVESbOtBG4xhOXREDSRsVFp+pffUBj0+uiOvK5uJ0HacskZWOIpe2WAGuDkUgo3iDKEVWTruJPStKgsult5A90ieu+NrpA+algyDrqxiOQvd+BlMsjyEypPnJrYhX7kYRqPx4Bf5xlCCw32SDQYYBy3DzuVsY7DhspofuiHJbdFX6F4tO405+CU0z1A8Z/5JVndW3JSvCcB9172iA9D5HacgPUaM0eM1nGTzei4XC6/Ja2pqav5TfgOdG76P3dnFLwAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAZCAYAAAA8CX6UAAAAzUlEQVR4XmNgGAXEgs1A/J8EjBOAJMOwiKFr0sAiBgdCDBAXIQMmBoiGC2jiIPAIXQAGtgIxI5pYAQPEIH80cTYg7kMTg4N8dAEgeM+A3QsCQCyOLogPYAsfkgEzA8SQM+gSpIJyBohB3ugSSGABENuiC6KDzwyEvVWNLoANUCV8QNGLL3zYgfg8EN9El0AHsxkgBiWgicPAFyiN1cVBQPyNAZJ23kIxKJx+MWDX0AnEM9AFyQHYDCcZcADxPyjbDlmCHPCDARLgo2CgAAAoJTeRY/JtsgAAAABJRU5ErkJggg==>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAC8AAAAZCAYAAAChBHccAAAB6UlEQVR4Xu2XPShFYRjHH5QkX5OPKKsyMhgImZVBmRhYlcUkAxmYfCsLGSyyEIuiTMpHdhYGSkJEUfLx/Hve4z73uefe40qdO5xf/bvPx7/3vOe873k7lygi4t+pZi2y5llFppexTLO+WN0uL2M9st5+HBlINsmkT23Dgd6nLWYKmNyzLSoGSDxtthE2VyQTS0U5iWfdNsKkmWRSe7bhA3wPthgm7ySTwp5PRQeJb802wgQTCtoyYIfE12UbYVFKMqFX2/Ah2U0W2EIKfusdI7lWhW1ockhMx7ZhqCHxLZt6Mf3++EzHC/weVAIwBQ2a7KlPsWZsMQnpeAvJ/3oJPFHMmOfiXdaCqyH2G8i7IehG1ZtY16wjiq1UMu8ga5t1wdpS9QnWkspTgkFxft+qGj4JzkhuLkvVNfam+lj7KkcfT9GLNf2sDRfnUnwfJ2CVygO5IxkATwzbCHGn6uerGJRQ4nazE0ReS8HeXpIV9rDjpM05q1XlWAHNJGtW5d7JpfFy661UPXDJanQxTiQ7TtpgH2KQF/dbF9+mD5IvTqxIg6vpi2JLjLs4yOvFm6wh1grJcflnRkkGhQ5MD7SzTlgjqtZD8nF3z2pRdT/vHMkWxf+FVdahq+P9wioPu/zP1FPshYuIiAiRb7SIgiHZPFwqAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGEAAAAZCAYAAAAhd0APAAADO0lEQVR4Xu2ZS8hNURTHl7e8Rx4hA+WRZEAyIGRkIIoyYkAZSMljJAOPASNvpUQGDGRCRAoZKe8BEyafQiTkTeSx/tbe7rp/Z99zzv2oe7/Or1Z37/Vf3z5nP8865xOpqKioaAvGqB1SO6A2iLSK/8wetZ9qy0J9mNobtS9/IrouT8X6Hu272vSgPSYN49E/aPhlrSm6izVwh4UAtB/s7KKgr/fYqUwW0w6zEIDWKdDAe3Y61orFzGOhC4J+fmKnMktMu8SCskFtIjvL8ETyZ3G4WMwpFlqAEWI7uRHz2dGAeKww0d/BgvKKHWWYLdbwZRYyQNxrdrYIuLee7Ax8VevHzgZkTcI2tbEJ7bykr12Ib2KN5q2kRWJxJ1loIXB/vciH/g0gXx5ZA/0s/LLWQ+2CqzcFN5rioljcUhZaDD8RmICBTisKj8k1qS1S1l66clMMFWvwMwsZ8MUjZVZZ0djtYtfCWd8M+FtMQLPvN76vfaX+Oei18WrrncYgtc8FWwkN3mSBmCAWd5T8g6V42lomFmRNeFFwHVgfFgqCPD9enzNGPwmN7rGb2mJ2pkBDeYOT2gW71fayM0GZWBwhWdcrAvoSdxzKvZ1WlPti15+itoq0OBZI2aH/E95KrcPYeigjDz4YfChnDUi8Gdhz50cujTfPG1LbOanYjWrnxFK+s86/U+2IqxfFT4D38cM6jzOSXngfxfzvWHAgW0LKWipjQqM49144H86zB2KThK2VBd/kSrWrrg49Phg5do3a6VDGavU6zvNRrl4EfGJIpaGYiDIDskvsfsaxoNwV01JHHZ6zSGVvqy0kLRc85dE4VjBuGuUlTucODpG/jzEeaNQnSX7sCql/C+V28kCn846d+C2sCKslnfWckPqFlqJsHzJ5qDbX1bEjPFgt+1w9ZlqeWOfYkU4Dj9RmhjKOE26n3cDbOU6RTtMhNhgfwu/Uevn39scXVuyQGcHnBw9HzY5QzouNZZzFm9SOiaWp7Qqyq9FqV1goy1axwYHhZYVZoHZLbYvzLRdL6fBQmuP8WbH7xY4+/L/iuNr14MfzB7tuc6i3I+vE+lb2uZbJNGnujbOioqKioqKiJL8AZqnmdx+CExUAAAAASUVORK5CYII=>
