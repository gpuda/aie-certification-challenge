import os
import json
from pathlib import Path
from typing import Optional, List

import duckdb
from dotenv import load_dotenv
from qdrant_client import QdrantClient

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from langgraph.prebuilt import create_react_agent


# =======================
# PATHS + ENV
# =======================
API_DIR = Path(__file__).resolve().parent.parent   # .../ai-tv-pro/api  (agent.py je u api/app)
ROOT_DIR = API_DIR.parent                          # .../ai-tv-pro

load_dotenv(API_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.local", override=True)

# OPENAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# timeouts / agent settings (da ne visi)
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "60"))
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "4"))

# TAVILY
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# COHERE (optional rerank)
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(f"OPENAI_API_KEY missing in {API_DIR / '.env'}")

# QDRANT (CLOUD)
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "tv_monthly_channel_rating")

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL / QDRANT_API_KEY missing in api/.env")

# CSV (local)
TV_CSV_PATH = os.getenv(
    "TV_CSV_PATH",
    str(API_DIR / "tv_data" / "Monthly iptv - channel monthly rating.csv"),
)


# =======================
# SYSTEM PROMPT
# =======================
SYSTEM_PROMPT = """
You are BroadcastIQ, an IPTV analytics assistant.

You have tools:
1) tv_sql: run SQL on the IPTV dataset (DuckDB view: tv) for ALL quantitative questions.
2) tv_schema: inspect columns, date range, and categories if unsure.
3) tv_rag_search: basic internal retrieval for qualitative explanations or definitions.
4) advanced_retrieve: wide internal retrieval + optional rerank for higher-quality qualitative retrieval.
5) web_search: ONLY for external/public information not contained in the dataset.

STRICT TOOL ROUTING RULES:

1. You MUST use tv_sql for ANY question involving:
   - top, bottom, ranking
   - average, avg, mean
   - sum, total
   - trend, growth, change, comparison
   - distribution, segmentation
   - month-over-month (MoM)
   - last X months
   - numeric values of any kind

2. You are NOT allowed to:
   - compute averages or totals from retrieved RAG text chunks
   - infer rankings from partial context
   - answer numeric questions without executing tv_sql

3. Use tv_schema only when:
   - you are unsure about column names
   - you need to identify available months or categories

4. Use tv_rag_search / advanced_retrieve only for:
   - definitions (e.g., "What does nr_unique_viewers represent?")
   - descriptive explanations of metrics
   - qualitative context
   Prefer advanced_retrieve when you want better context selection.

5. Use web_search only if the question is clearly external
   (news, public facts, real-time events, non-dataset info).

TIME PERIOD RULES:

- "Latest month" = MAX(month_partition).
- "Last 3 months" = the three largest month_partition values.
- When computing "average over last 3 months":
    Step 1: compute monthly totals per month and entity.
    Step 2: compute AVG of those monthly totals.
    Never average daily rows directly unless explicitly asked.

DATA INTEGRITY RULES:

- Never fabricate numbers.
- If tv_sql returns no data, explicitly state that.
- If the query is ambiguous, ask a clarification question.

OUTPUT STYLE:

- 1-8 concise sentences.
- If tv_sql was used:
    - Clearly state the period analyzed.
    - Present the key results (Top 5, totals, etc.).
    - Avoid dumping raw JSON.
- Be precise, structured, and business-oriented.
""".strip()


# =======================
# VECTOR STORE (Qdrant)
# =======================
_vectorstore: QdrantVectorStore | None = None

def get_vectorstore() -> QdrantVectorStore:
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    embeddings = OpenAIEmbeddings(
        model=EMBED_MODEL,
        api_key=OPENAI_API_KEY,
    )

    _vectorstore = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=embeddings,
    )
    return _vectorstore


def _get_retrievers():
    """
    Helper: basic + wide retriever.
    - basic: k=6 (kao tv_rag_search)
    - wide: k=20 (za rerank / advanced retrieval)
    """
    vs = get_vectorstore()
    basic = vs.as_retriever(search_kwargs={"k": 6})
    wide = vs.as_retriever(search_kwargs={"k": 20})
    return basic, wide


# =======================
# DUCKDB (CSV -> view tv)
# =======================
_duck: Optional[duckdb.DuckDBPyConnection] = None

def get_duckdb() -> duckdb.DuckDBPyConnection:
    global _duck
    if _duck is not None:
        return _duck

    csv_path = Path(TV_CSV_PATH)
    if not csv_path.exists():
        raise RuntimeError(
            f"TV_CSV_PATH not found: {csv_path}. "
            f"Set env TV_CSV_PATH or place file at api/tv_data/Monthly iptv - channel monthly rating.csv"
        )

    con = duckdb.connect(database=":memory:")

    con.execute(f"""
        CREATE OR REPLACE VIEW tv AS
        SELECT
            CAST(month_partition AS INTEGER) AS month_partition,
            CAST(watch_date AS DATE) AS watch_date,
            channelname,
            content_playback_type,
            CAST(REPLACE(daily_total_minute, ',', '.') AS DOUBLE) AS daily_total_minute,
            CAST(nr_unique_viewers AS BIGINT) AS nr_unique_viewers
        FROM read_csv('{csv_path.as_posix()}', delim=';', header=true, all_varchar=true);
    """)

    _duck = con
    return _duck


# =======================
# TOOLS
# =======================
@tool
def tv_schema() -> str:
    """Return dataset schema + basic profiling (rows, date range, distinct playback types)."""
    try:
        con = get_duckdb()

        cols_df = con.execute("PRAGMA table_info('tv')").df()

        profile_df = con.execute("""
            SELECT
              MIN(watch_date) AS min_date,
              MAX(watch_date) AS max_date,
              COUNT(*) AS rows,
              COUNT(DISTINCT channelname) AS n_channels,
              COUNT(DISTINCT content_playback_type) AS n_playback_types
            FROM tv
        """).df()

        playback_df = con.execute("""
            SELECT DISTINCT content_playback_type
            FROM tv
            ORDER BY 1
        """).df()

        payload = {
            "csv_path": str(TV_CSV_PATH),
            "columns": cols_df.to_dict(orient="records"),
            "profile": profile_df.to_dict(orient="records")[0] if len(profile_df) else {},
            "playback_types": playback_df["content_playback_type"].tolist()
            if "content_playback_type" in playback_df.columns else [],
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return f"Schema error: {e}"


@tool
def tv_sql(query: str) -> str:
    """
    Execute a READ-ONLY SQL query against the IPTV dataset (DuckDB view: tv).
    Returns JSON records.

    Rules:
    - Only SELECT queries are allowed.
    - If no LIMIT and no GROUP BY, a LIMIT 50 is auto-added.
    """
    q = (query or "").strip().rstrip(";")
    if not q:
        return "SQL error: empty query."
    if not q.lower().startswith("select"):
        return "Only SELECT queries are allowed."

    q_low = q.lower()
    if " limit " not in q_low and "group by" not in q_low:
        q = q + " LIMIT 50"

    try:
        con = get_duckdb()
        df = con.execute(q).df()
        return df.to_json(orient="records", force_ascii=False)
    except Exception as e:
        return f"SQL error: {e}"


@tool
def tv_rag_search(query: str) -> str:
    """Search INTERNAL IPTV dataset stored in Qdrant and return relevant context."""
    basic, _wide = _get_retrievers()

    docs = basic.invoke(query)
    if not docs:
        return "No relevant internal context found in Qdrant."

    lines = []
    for d in docs:
        content = (d.page_content or "")[:450]
        lines.append(f"- {content} (meta={d.metadata})")
    return "\n".join(lines)


@tool
async def advanced_retrieve(query: str) -> str:
    """
    Wide retrieve (k=20) from Qdrant + optional Cohere rerank to top_n=3.
    If COHERE_API_KEY missing OR cohere not installed, fallback to top 3 from wide retrieve.
    """
    q = (query or "").strip()
    if not q:
        return "Empty query."

    _basic, wide = _get_retrievers()
    docs = await wide.ainvoke(q)

    if not docs:
        return "No relevant internal context found in Qdrant."

    # default fallback: first 3 from wide retrieval
    top_docs = docs[:3]

    # optional rerank via Cohere
    if COHERE_API_KEY:
        try:
            import cohere

            co = cohere.AsyncClientV2(api_key=COHERE_API_KEY)
            rerank_res = await co.rerank(
                model="rerank-v3.5",
                query=q,
                documents=[d.page_content for d in docs],
                top_n=3,
            )
            idxs = [r.index for r in rerank_res.results]
            top_docs = [docs[i] for i in idxs]
        except Exception:
            top_docs = docs[:3]

    return "\n\n".join([(d.page_content or "") for d in top_docs])


@tool
def web_search(query: str) -> str:
    """Search the public web using Tavily (if configured). Use only when needed."""
    if not TAVILY_API_KEY:
        return "Tavily is not configured (missing TAVILY_API_KEY)."

    q = (query or "").lower()

    internal_hints = [
        "unique viewers", "nr_unique_viewers", "daily_total_minute",
        "month_partition", "watch_date", "channelname",
        "iptv", "youbora", "playback_type", "content_playback_type"
    ]
    if any(h in q for h in internal_hints):
        return "Skip web search: this looks like an internal IPTV dataset question."

    try:
        from tavily import TavilyClient

        tv = TavilyClient(api_key=TAVILY_API_KEY)
        res = tv.search(query=query, max_results=5)
        results = res.get("results", []) if isinstance(res, dict) else []

        if not results:
            return "No web results."

        lines = []
        for r in results[:5]:
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = r.get("content", "") or r.get("snippet", "")
            snippet = (snippet[:180] + "...") if isinstance(snippet, str) and len(snippet) > 180 else snippet
            if snippet:
                lines.append(f"- {title} | {url} | {snippet}")
            else:
                lines.append(f"- {title} | {url}")

        return "\n".join(lines)

    except Exception as e:
        return f"Web search error: {e}"


# Export tools in one place (main.py moze ovo koristiti direktno ako zeli)
TOOLS: List = [tv_schema, tv_sql, tv_rag_search, advanced_retrieve, web_search]


# =======================
# AGENT
# =======================
_agent = None

def create_agent():
    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        temperature=0.0,
        request_timeout=OPENAI_TIMEOUT_S,  # bitno da ne visi
    )

    # ensure duckdb view is ready at startup
    get_duckdb()

    # Try multiple signatures (langgraph version differences)
    try:
        return create_react_agent(
            llm,
            TOOLS,
            max_iterations=AGENT_MAX_ITERATIONS,
            state_modifier=SYSTEM_PROMPT,
        )
    except TypeError:
        # fallback 1
        try:
            return create_react_agent(
                llm,
                TOOLS,
                max_iterations=AGENT_MAX_ITERATIONS,
            )
        except TypeError:
            # fallback 2
            return create_react_agent(llm, TOOLS)


async def get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent