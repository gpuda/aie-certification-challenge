
# TASK 1 - Defining the Problem, Audience, and Scope

### 1.1. Problem + Audience (1-Sentence Problem Statement):
IPTV business stakeholders rely on data analysts to answer routine natural-language questions about channel performance and viewership metrics, creating reporting bottlenecks and slowing decision-making.

### 1.2. Why This Is a Problem:
In my telco company, stakeholders such as product managers, marketing teams, and content strategy leads frequently ask ad-hoc questions like “What was the most watched channel last night?” or “How did sports perform this weekend compared to last month?”. While these questions are simple from a business perspective, they require SQL queries, data validation, and formatting — which means they flow through analysts.
This creates a bottleneck. Analysts spend a significant portion of time answering repetitive questions instead of focusing on deeper analysis and strategic insights. For stakeholders, this delays decisions related to scheduling, promotions, and customer engagement. A natural language IPTV analytics agent would allow business users to self-serve insights while maintaining data accuracy and governance.

Target User
Primary User:
TV Product Manager / Content Strategy Manager / Marketing Analyst
Job Function Being Automated:
Ad-hoc viewership performance analysis and basic reporting.
Pain Point:
They need fast answers but lack SQL skills or direct access to structured data.

### 1.3. Evaluation questions:
 - Top 5 channels by average viewing minutes in the last 3 months?
 - Top 5 channels by average unique viewers in the last 3 months?
 - Average viewing minutes by content_playback_type in the last 3 months?
 - Which channel had the highest total viewing minutes last month?
 - What are the viewer statistics for Doma TV over the last 31 days?
 - What does nr_unique_viewers represent in this dataset?

----------

# TASK 2. Propose a Solution

### 2.1. Propose a Solution 1-2 paragraphs
We propose building a Natural Language IPTV Analytics Agent that allows stakeholders to query TV viewership data through a simple chat interface. The user asks a question in plain English, and the system executes controlled, read-only SQL queries against an internal IPTV dataset using DuckDB. The results are summarized in clear, business-oriented language.

The system combines structured SQL execution with internal retrieval. Quantitative KPI questions (rankings, averages, comparisons, trends) are answered via SQL execution over a validated in-memory dataset view. When metric definitions or schema clarification are required, the agent uses dedicated schema inspection and internal retrieval tools. An orchestration agent (LangGraph ReAct) enforces strict tool routing rules to ensure numeric answers are always computed from the dataset and never inferred from partial text context.

### 2.2. Create an infrastructure diagram of your stack showing how everything fits together. Write one sentence on why you made each tooling choice. 

#### 2.2.1. Infrastructure Diagram

                                   User 
                                    ↓
                            Next.js Frontend 
                                    ↓
                            FastAPI Backend 
                                    ↓
                            LangGraph ReAct Agent
                                    ↓
                            Tools:
                                • tv_sql → DuckDB
                                • tv_schema → DuckDB schema
                                • tv_rag_search / advanced_retrieve → Qdrant
                                • web_search → Tavily
                                    ↓
                            OpenAI LLM (gpt-5-mini)
                                    ↓
                            Formatted Business Response → Frontend

#### 2.2.2. Tooling Decisions and Rationale
**LLM – gpt-5-mini**  
Chosen for strong reasoning performance with controlled cost, suitable for structured analytical responses.

**Agent Framework – LangGraph (ReAct)**  
Used to enforce explicit tool routing rules and structured multi-step reasoning.

**SQL Engine – DuckDB (tv_sql tool)**  
Provides fast, in-memory analytical queries over structured IPTV data, ensuring numeric answers are computed directly from the dataset.

**Schema Tool – tv_schema**  
Allows safe inspection of columns and date ranges before query execution.

**Vector Database – Qdrant**  
Enables dense retrieval of internal context for qualitative metric explanations.

**Embeddings – text-embedding-3-small**  
Lightweight and cost-efficient model for structured dataset embeddings.

**Advanced Retrieval – wide retrieval + optional rerank**  
Improves context precision for qualitative questions.

**External Search – Tavily**  
Used only for clearly external, non-dataset questions.

**Backend – FastAPI**  
Lightweight API layer for agent orchestration.

**Frontend – Next.js + shadcn/ui**  
Provides a modern conversational interface.

**Evaluation – RAGAS**  
Used to benchmark retrieval quality and answer faithfulness.


### 2.3. RAG and Agent Components (What Exactly Is What?)

**RAG components (retrieval + context):**
- **Qdrant Vector Store** contains embedded internal IPTV context/documents.
- **Embeddings (text-embedding-3-small)** are used to index and search this internal context.
- **Retrieval tools:**  
  - 'tv_rag_search' (basic retriever, k=6)  
  - 'advanced_retrieve' (wide retriever, k=20 + optional Cohere rerank)

These are used for **qualitative** questions such as metric definitions, dataset explanations, and business context.

**Agent components (orchestration + tool routing):**
- **LangGraph ReAct agent** is the orchestrator that decides which tool to call.
- **Strict routing rules in the SYSTEM_PROMPT** enforce that all numeric / KPI questions must use SQL execution and cannot be answered from retrieved text.
- **Quantitative toolchain:**  
  - 'tv_sql' executes read-only SELECT queries in *DuckDB* over the in-memory view 'tv'.  
  - 'tv_schema' inspects columns, date ranges, and categories when needed.  
- **External tool:** 'web_search' (Tavily) is used only for clearly external questions not covered by the dataset.

In short: *RAG provides internal qualitative context*, while the *agent enforces safe tool routing and uses SQL execution for all quantitative KPI answers*.

----------

# TASK 3 - Dealing with the Data

### 3.1. Describe all of your data sources and external APIs, and describe what you’ll use them for.

1) *Monthly IPTV dataset (CSV):* 'Monthly iptv - channel monthly rating.csv'  
   - Columns: 'month_partition', 'watch_date', 'channelname', 'content_playback_type', 'daily_total_minute', 'nr_unique_viewers'.  
   - Used as the single source of truth for all quantitative KPI answers (rankings, averages, totals, comparisons). The backend loads it into an in-memory DuckDB view called 'tv'.
2) *DuckDB in-memory analytics layer (SQL execution via tool 'tv_sql'):*  
   - Used to compute all numeric outputs deterministically from the dataset. 
3) *Qdrant vector store (collection: 'tv_monthly_channel_rating'):*  
   - Stores embedded internal documents derived from the dataset so the agent can answer qualitative questions (definitions, explanations, dataset context) via 'tv_rag_search' and 'advanced_retrieve'.
 
 #### External APIs
1) *OpenAI API (LLM + embeddings):*  
   - LLM ('gpt-5-mini') is used for orchestration and response generation; embeddings ('text-embedding-3-small') are used to index/search internal context in Qdrant. 
2) *Tavily Web Search (tool: 'web_search'):*  
   - Used only for clearly external/public questions not answerable from the dataset. The agent explicitly avoids web-search for internal KPI terms. 
3) *Cohere (optional rerank in 'advanced_retrieve'):*  
   - If configured, reranks a wider set of retrieved documents (k=20) down to the best top_n=3 to improve qualitative context selection; if not configured, it falls back to the top 3 results from the wide retrieve. 

#### How they interact at runtime
- Quantitative questions -> *tv_sql (DuckDB)* is mandatory (numbers come from SQL, not from retrieved text).  
- Qualitative questions -> *Qdrant retrieval* provides internal context, then the LLM writes a concise explanation.  
- External questions -> *Tavily* is used only when the question is outside the dataset scope. 


### 3.2 Describe the default chunking strategy that you will use.  Why did you make this decision?

#### Strategy
- *Document creation:* During ingestion, each row of the IPTV CSV dataset is converted into a structured text document.  
All relevant fields are serialized into a compact '"key=value"' format and concatenated using '" | "' as a separator.

Each row is treated as a primary semantic unit and stored as a LangChain 'Document' with associated metadata (e.g., row index and source file).

This preserves the full structured context of each record while enabling semantic retrieval.

#### Chunking Configuration
After document creation, the documents are processed using:
- 'RecursiveCharacterTextSplitter'
- 'chunk_size = 1000'
- 'chunk_overlap = 200'

This ensures that:
- Documents remain small enough for high-precision retrieval.
- Overlap prevents accidental loss of adjacent contextual fields.
- Important attribute combinations (e.g., channel + month + playback type) remain within the same chunk.

#### Why This Strategy Was Chosen
1. *Structured Dataset Nature*  
   The IPTV dataset is tabular and repetitive. Representing each row as a structured text record allows the vector store to retrieve field-level examples and metric context efficiently.
2. *Separation of Responsibilities*  
   Quantitative KPI calculations (rankings, averages, totals) are always executed via SQL (DuckDB). The vector store is used only for qualitative questions (definitions, explanations, schema understanding). Therefore, chunking is optimized for semantic clarity rather than numeric aggregation.
3. *Precision vs. Recall Balance*  
   A 1000-character chunk size provides sufficient contextual coverage without introducing excessive noise, while a 200-character overlap improves retrieval robustness.

In practice, most row-based documents in this dataset are shorter than 1000 characters, meaning they are typically not further split. Therefore, the chunking configuration primarily acts as a safeguard rather than an active fragmentation mechanism.

The 200-character overlap ensures that if a document exceeds the chunk size (e.g., due to additional metadata or formatting), important attribute combinations are not split in a way that reduces semantic coherence during retrieval.

Since all quantitative KPI calculations are executed via SQL (DuckDB), the vector store is not responsible for numeric aggregation. The chunking strategy is therefore optimized for semantic clarity and contextual retrieval, not for computational accuracy.

----------

# TASK 4 - Build an End-to-End Prototype (Local Deployment)

I built an end-to-end prototype *BroadcastIQ* with a Next.js chat frontend and a FastAPI backend that hosts the LangGraph ReAct agent. The application runs fully locally: the frontend sends user questions to a '/chat' endpoint, the agent routes the request to the appropriate tools (DuckDB SQL for quantitative KPIs, Qdrant retrieval for qualitative context, and Tavily only for external questions), and the final answer is returned to the UI.

**How to run locally:**
- *Backend:* 'cd api' → activate venv → 'uvicorn app.main:app --reload' (http://localhost:8000)  
- *Frontend:*  'npm run dev' (http://localhost:3000)


----------

# TASK 5 – Evals

## 5.1 RAGAS Evaluation

To assess retrieval quality and grounding reliability, I evaluated the pipeline using the RAGAS framework on a synthetic test set generated in 'generate_testset_tv.ipynb'. The evaluation was executed in 'evaluate_tv.ipynb'.

The following RAGAS metrics were used:

- **Faithfulness** – measures whether the generated answer is supported by retrieved context.
- **Context Recall** – measures how much of the relevant ground-truth context was successfully retrieved.
- **Factual Correctness (F1 mode)** – measures semantic alignment between the expected answer and the generated response.

Although RAGAS also supports metrics such as Response Relevance and Context Precision, the current evaluation run focused on Faithfulness and Context Recall, as these were most relevant for assessing grounding quality in this SQL-first architecture.

---

#### Evaluation Results (27 test cases)

| Metric | Score |
|--------|-------|
| Faithfulness | 0.0541 |
| Context Recall | 0.0000 |
| Factual Correctness (F1) | 0.0870 |

### 5.2 Conclusions and Interpretation

The RAGAS evaluation results show low Context Recall and modest Faithfulness scores. This outcome is largely explained by the architectural design of the system.

BroadcastIQ follows a SQL-first design for quantitative KPI questions. All numeric answers (rankings, averages, totals) are computed deterministically via DuckDB using the 'tv_sql' tool. These answers are not derived from retrieved text chunks, which means that RAGAS Context Recall does not reflect actual numeric correctness. Since SQL execution bypasses vector retrieval, Context Recall remains near zero for SQL-dominated queries.

This highlights an important architectural distinction: RAGAS primarily evaluates text-based retrieval grounding, while this system separates numeric computation (SQL) from semantic retrieval (RAG).

#### Why SQL Correctness Was Introduced:
Because the application is an analytics system, numeric correctness is critical. RAGAS does not validate whether:
- Rankings are mathematically correct
- Aggregations are computed accurately
- Top-N results are properly ordered

For this reason, a dedicated SQL correctness evaluation layer was implemented. SQL outputs were compared deterministically against ground-truth results derived directly from the dataset.

This additional evaluation step ensures:
- Numeric integrity
- Deterministic KPI validation
- Reduced hallucination risk for quantitative answers

#### Overall Effectiveness
The evaluation demonstrates that:

1. The system produces stable and deterministic SQL results.
2. RAGAS metrics are not fully representative of performance in a SQL-first analytical architecture.
3. Retrieval quality mainly affects qualitative explanation tasks rather than quantitative KPI accuracy.

Therefore, the combined use of RAGAS (for retrieval grounding) and SQL correctness (for numeric validation) provides a more complete and architecture-aware evaluation framework.


---------

# 6. Improving Your Prototype

### 6.1 Choose an advanced retrieval technique that you believe will improve your application’s ability to retrieve the most appropriate context. Write 1-2 sentences on why you believe it will be useful for your use case.

I implemented a *wide dense retrieval strategy* ('k=20') with optional reranking to improve context selection for qualitative questions such as metric definitions and dataset explanations. 

In a SQL-first architecture where numeric answers are computed deterministically, retrieval quality primarily affects explanation grounding rather than KPI correctness. Therefore, advanced retrieval is expected to improve semantic precision without impacting SQL-based computations.


### 6.2. Implementation of Advanced Retrieval

The baseline pipeline used a standard dense retriever ('k=6') to fetch context from the Qdrant vector store.

To implement the advanced retrieval strategy, I introduced a wide retrieval configuration ('k=20') combined with optional reranking (Cohere) to select the top 3 most relevant context chunks. This was implemented through the 'advanced_retrieve' tool, while keeping the original 'tv_rag_search' retriever as the baseline reference.

The agent routing logic remained unchanged: 
- Quantitative KPI queries continue to use 'tv_sql' (DuckDB).
- Qualitative questions can now use the advanced retrieval pipeline for improved context selection.

This allowed a controlled comparison between baseline and advanced retrieval strategies without modifying the SQL execution layer.


### 6.3 Performance Comparison (Baseline vs Advanced Retrieval)

The advanced retrieval pipeline was evaluated using the same synthetic test set and RAGAS configuration as the baseline system.

### Results (27 test cases)

| Metric | Baseline | Advanced Retrieval |
|--------|----------|-------------------|
| Context Recall | 0.000 | 0.000 |
| Faithfulness | 0.151 | 0.140 |
| Factual Correctness (F1) | 0.000 | 0.016 |
| Success Rate | 96% | 100% |

#### Interpretation

The advanced retrieval configuration (wide retrieve + reranking) did not materially improve RAGAS metrics on this dataset.

- *Context Recall remained 0.0* in both configurations, reflecting the SQL-first architecture where quantitative answers are computed deterministically rather than retrieved from text.
- *Faithfulness showed minor variation*, indicating that reranking did not significantly change grounding quality for the evaluated queries.
- *Factual Correctness improved slightly*, suggesting marginal improvement in semantic alignment.
- *Success Rate improved to 100%*, indicating more stable evaluation execution.

#### Engineering Conclusion

The limited metric improvement is expected because:

1. The evaluation dataset is dominated by quantitative SQL-style queries.
2. Retrieval quality has limited impact on numeric correctness.
3. Advanced retrieval primarily benefits qualitative explanation tasks rather than KPI computation.

This experiment confirms that, in a SQL-first analytical architecture, retrieval enhancements influence explanation grounding but do not significantly alter numeric performance metrics.

#### SQL Correctness Note
SQL correctness results are identical between baseline and improved retriever variants.
This is expected because SQL-style questions are executed deterministically via the 'tv_sql' tool and are not influenced by retrieval strategy or reranking.
Therefore, SQL correctness evaluation is reported once in the baseline notebook.

---------

# TASK 7 – Next Steps

For Demo Day, I plan to keep the dense vector retrieval layer, but not as the primary analytical engine.

In this specific use case, the core value of the system comes from deterministic SQL execution over structured IPTV KPI data. Numeric correctness, ranking integrity, and aggregation accuracy are mission-critical. Dense vector retrieval does not directly improve quantitative computation and therefore does not materially affect KPI correctness.

However, I will retain the RAG layer as a complementary semantic component. It is valuable for:
- Metric definitions
- Schema explanations
- Dataset clarification
- Business-context enrichment

#### Strategic Next Steps

Given that the primary data source is structured database data, the most impactful next improvements would be:

1. **Direct database integration (production DB instead of CSV ingestion)**  
   Connecting the agent directly to a governed analytics database rather than static CSV exports.
2. **Query validation and guardrails**  
   Implementing stronger SQL validation and schema-aware query planning to ensure production safety.
3. **Monitoring and Hybrid Retrieval Strategy**  
   Implement performance monitoring (latency, SQL correctness, usage patterns) and explore metadata-aware or hybrid retrieval to improve qualitative explanations.

### Conclusion

In a structured analytics use case like this one, Dense Vector Retrieval plays a supporting role rather than a central one. The long-term strategic focus should be on robust SQL execution, database integration, and production-grade monitoring rather than purely on retrieval improvements.

---------

### LOOM VIDEO:

Link: https://www.loom.com/share/3c82379fdcc84da3adba1a060690d85a

---

### GitHub Repository:

Link: https://github.com/gpuda/aie-certification-challenge

---