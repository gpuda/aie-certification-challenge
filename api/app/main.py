import os
import re
import asyncio
from pathlib import Path
from typing import List, Literal, Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langchain_openai import ChatOpenAI

# Agent + vectorstore + duckdb
from app.agent import (
    get_agent,
    get_vectorstore,
    get_duckdb,  # <-- direct DuckDB access for fast analytics
    SYSTEM_PROMPT as AGENT_SYSTEM_PROMPT,
)

# Load env from api/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
MAX_HISTORY_MESSAGES = int(os.getenv("CHAT_MAX_HISTORY", "10"))

FAST_RAG_MODEL = os.getenv("FAST_RAG_MODEL", MODEL)
FAST_RAG_TIMEOUT_S = float(os.getenv("FAST_RAG_TIMEOUT_S", "20"))

AGENT_TIMEOUT_S = float(os.getenv("AGENT_TIMEOUT_S", "60"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def last_user_text(messages: List[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role == "user" and (m.content or "").strip():
            return m.content.strip()
    return ""


def to_lg_messages(messages: List[ChatMessage], keep_last: int) -> list[dict]:
    recent = messages[-keep_last:] if keep_last > 0 else messages
    out: list[dict] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    out.extend(
        [{"role": m.role, "content": m.content} for m in recent if (m.content or "").strip()]
    )
    return out


def is_greeting_or_intro(q: str) -> bool:
    qlow = q.lower().strip()

    if re.search(r"^(bok|pozdrav|hello|hi|hey)\b", qlow):
        return True
    if re.search(
        r"^(bok|pozdrav|hello|hi|hey)[,\-!\s]+(ja sam|moje ime je|i'?m|my name is)\b",
        qlow,
    ):
        return True
    if re.search(r"^(ja sam|moje ime je|i'?m|my name is)\b", qlow):
        return True

    return False


def is_faq_question(q: str) -> bool:
    qlow = q.lower().strip()
    phrases = [
        "kojim podacima",
        "kakvim podacima",
        "kojim podatcima",
        "tko si",
        "ko si",
        "pomoc",
        "help",
        "koje su ti mogucnosti",
        "koje su ti mogućnosti",
        "what data",
        "data do you have",
        "what can you do",
        "capabilities",
        "who are you",
    ]
    return any(p in qlow for p in phrases)


def greeting_answer() -> str:
    return (
        "Bok! Ja sam BroadcastIQ. 🙂\n\n"
        "Mozes me pitati o internom IPTV datasetu (kanali, gledanost, unique viewers, minute gledanja). "
        "Za brojke i agregacije koristim SQL, a za definicije mogu koristiti RAG."
    )


def faq_answer() -> str:
    return (
        "Imam pristup:\n"
        "- Internom IPTV datasetu (DuckDB/CSV + Qdrant RAG).\n"
        "  Polja: month_partition, watch_date, channelname, content_playback_type, daily_total_minute, nr_unique_viewers.\n"
        "- Javnom webu preko Tavily (za vanjske / real-time informacije).\n\n"
        "Pravilo: brojke/agregacije -> SQL. Definicije/objasnjenja -> RAG."
    )


def is_analytical_question(q: str) -> bool:
    qlow = q.lower()
    keywords = [
        "top",
        "bottom",
        "rank",
        "ranking",
        "avg",
        "average",
        "mean",
        "sum",
        "total",
        "trend",
        "growth",
        "change",
        "compare",
        "comparison",
        "mom",
        "month-over-month",
        "month over month",
        "last ",
        "latest month",
        "previous month",
        "group by",
        "by ",
        "top 5",
        "top5",
        "last 3 months",
        "last three months",
        "last 31 days",
        "past 31 days",
    ]
    return any(k in qlow for k in keywords)


def looks_like_definition_lookup(q: str) -> bool:
    # samo definicije (ne analitika)
    if is_analytical_question(q):
        return False

    qlow = q.lower()
    hints = [
        "what does",
        "meaning",
        "represent",
        "definition",
        "nr_unique_viewers",
        "daily_total_minute",
        "month_partition",
        "watch_date",
        "channelname",
        "content_playback_type",
        "iptv",
        "youbora",
    ]
    return any(h in qlow for h in hints)


def fast_rag_answer(question: str) -> str:
    vs = get_vectorstore()
    retriever = vs.as_retriever(search_kwargs={"k": 4})
    docs = retriever.invoke(question)

    if not docs:
        return "Ne nalazim relevantan kontekst u internom datasetu za ovo pitanje."

    context = "\n".join([f"- {d.page_content}" for d in docs])

    llm = ChatOpenAI(
        model=FAST_RAG_MODEL,
        temperature=0.0,
        request_timeout=FAST_RAG_TIMEOUT_S,
    )

    prompt = f"""You are BroadcastIQ.
Answer using ONLY the internal context below.
If the context is insufficient, say so. Keep it concise (1-6 sentences).

Internal context:
{context}

User question:
{question}
"""
    resp = llm.invoke(prompt)
    return getattr(resp, "content", "") or str(resp)


# -----------------------
# FAST ANALYTICS (NO LLM)
# -----------------------
def _get_last_3_months(con) -> list[int]:
    df = con.execute(
        "SELECT DISTINCT month_partition FROM tv ORDER BY month_partition DESC LIMIT 3"
    ).df()
    return [int(x) for x in df["month_partition"].tolist()] if len(df) else []


def fast_analytics_answer(question: str) -> Optional[str]:
    """
    Direct DuckDB analytics for quick questions.
    Returns None if not matched.
    """
    q_raw = (question or "").strip()
    q = q_raw.lower()

    # ---------------------------------------------------------
    # NEW: "viewer statistics for <CHANNEL> over the last N days"
    # (and "past N days") -> fast DuckDB, avoids agent timeouts
    # ---------------------------------------------------------
    m = re.search(
        r"(?:for)\s+(.+?)\s+over\s+the\s+(?:last|past)\s+(\d+)\s+days",
        q_raw,
        flags=re.IGNORECASE,
    )
    if not m:
        # alternative phrasing: "<CHANNEL> over the last N days"
        m = re.search(
            r"(.+?)\s+over\s+the\s+(?:last|past)\s+(\d+)\s+days",
            q_raw,
            flags=re.IGNORECASE,
        )

    if m:
        channel = m.group(1).strip().strip('"').strip("'")
        days = int(m.group(2))

        # clamp for sanity
        days = max(1, min(days, 365))

        con = get_duckdb()

        # Use dataset max_date as anchor (not today), because dataset may not be up-to-date.
        summary_sql = f"""
        WITH bounds AS (
          SELECT MAX(watch_date) AS max_date FROM tv
        ),
        filtered AS (
          SELECT t.*
          FROM tv t, bounds b
          WHERE t.channelname ILIKE ?
            AND t.watch_date >= b.max_date - INTERVAL '{days} days'
        )
        SELECT
          COUNT(DISTINCT watch_date) AS days_covered,
          MIN(watch_date) AS start_date,
          MAX(watch_date) AS end_date,
          SUM(daily_total_minute) AS total_minutes,
          AVG(daily_total_minute) AS avg_daily_minutes,
          AVG(nr_unique_viewers) AS avg_daily_unique_viewers,
          MAX(nr_unique_viewers) AS max_daily_unique_viewers
        FROM filtered
        """
        row = con.execute(summary_sql, [channel]).fetchone()

        if not row or row[0] == 0:
            return (
                f"Nisam nasao podatke za kanal '{channel}' u zadnjih {days} dana "
                f"(prema max datumu u datasetu)."
            )

        days_covered, start_date, end_date, total_minutes, avg_daily_minutes, avg_uv, max_uv = row

        breakdown_sql = f"""
        WITH bounds AS (SELECT MAX(watch_date) AS max_date FROM tv),
        filtered AS (
          SELECT t.*
          FROM tv t, bounds b
          WHERE t.channelname ILIKE ?
            AND t.watch_date >= b.max_date - INTERVAL '{days} days'
        )
        SELECT
          content_playback_type,
          SUM(daily_total_minute) AS minutes,
          AVG(nr_unique_viewers) AS avg_daily_unique_viewers
        FROM filtered
        GROUP BY 1
        ORDER BY minutes DESC
        LIMIT 10
        """
        rows = con.execute(breakdown_sql, [channel]).fetchall()

        lines = []
        lines.append(
            f"Viewer stats za '{channel}' u zadnjih {days_covered} dana "
            f"(od {start_date} do {end_date}, prema datasetu):"
        )
        lines.append(f"- Total viewing minutes: {int(total_minutes):,}".replace(",", "."))
        lines.append(f"- Avg daily viewing minutes: {avg_daily_minutes:,.1f}".replace(",", "."))
        lines.append(f"- Avg daily unique viewers: {avg_uv:,.1f}".replace(",", "."))
        lines.append(f"- Max daily unique viewers: {int(max_uv):,}".replace(",", "."))
        lines.append("")
        lines.append("Breakdown po content_playback_type (top):")
        for cpt, mins, a_uv in rows:
            mins_i = int(mins) if mins is not None else 0
            lines.append(
                f"- {cpt}: {mins_i:,} min, avg daily UV {a_uv:,.1f}".replace(",", ".")
            )

        lines.append("")
        lines.append(
            "Napomena: 'nr_unique_viewers' je dnevna metrika; sumiranje kroz dane moze "
            "double-countati iste korisnike. Zato prikazujem prosjek/max po danu."
        )
        return "\n".join(lines)

    # match your 3 quick questions (accept small variations)
    is_q1 = "top 5" in q and "avg" in q and "viewing minutes" in q and "last 3 months" in q
    is_q2 = "top 5" in q and "avg" in q and "unique viewers" in q and "last 3 months" in q
    is_q3 = (
        "avg" in q and "viewing minutes" in q and "content_playback_type" in q and "last 3 months" in q
    )

    if not (is_q1 or is_q2 or is_q3):
        return None

    con = get_duckdb()
    months = _get_last_3_months(con)
    if len(months) < 3:
        return f"Nemam dovoljno mjeseci u datasetu za 'last 3 months'. Pronadjeno: {months}"

    months_str = ", ".join(str(m) for m in months)

    if is_q1:
        sql = """
        WITH last_months AS (
          SELECT DISTINCT month_partition
          FROM tv
          ORDER BY month_partition DESC
          LIMIT 3
        ),
        monthly AS (
          SELECT t.month_partition, t.channelname, SUM(t.daily_total_minute) AS month_minutes
          FROM tv t
          JOIN last_months m USING(month_partition)
          GROUP BY 1,2
        ),
        avg3 AS (
          SELECT channelname, AVG(month_minutes) AS avg_monthly_minutes
          FROM monthly
          GROUP BY 1
        )
        SELECT channelname, avg_monthly_minutes
        FROM avg3
        ORDER BY avg_monthly_minutes DESC
        LIMIT 5
        """
        df = con.execute(sql).df()
        if not len(df):
            return f"Nema podataka za zadnja 3 mjeseca ({months_str})."

        lines = [f"Top 5 kanala po AVG mjesecnim minutama (zadnja 3 mjeseca: {months_str}):"]
        for i, row in enumerate(df.itertuples(index=False), start=1):
            ch = getattr(row, "channelname")
            val = float(getattr(row, "avg_monthly_minutes") or 0.0)
            lines.append(f"{i}. {ch}: {val:,.2f} min".replace(",", " "))
        return "\n".join(lines)

    if is_q2:
        sql = """
        WITH last_months AS (
          SELECT DISTINCT month_partition
          FROM tv
          ORDER BY month_partition DESC
          LIMIT 3
        ),
        monthly AS (
          SELECT t.month_partition, t.channelname, SUM(t.nr_unique_viewers) AS month_uv
          FROM tv t
          JOIN last_months m USING(month_partition)
          GROUP BY 1,2
        ),
        avg3 AS (
          SELECT channelname, AVG(month_uv) AS avg_monthly_uv
          FROM monthly
          GROUP BY 1
        )
        SELECT channelname, avg_monthly_uv
        FROM avg3
        ORDER BY avg_monthly_uv DESC
        LIMIT 5
        """
        df = con.execute(sql).df()
        if not len(df):
            return f"Nema podataka za zadnja 3 mjeseca ({months_str})."

        lines = [
            f"Top 5 kanala po AVG mjesecnim unique viewers (zadnja 3 mjeseca: {months_str}):"
        ]
        for i, row in enumerate(df.itertuples(index=False), start=1):
            ch = getattr(row, "channelname")
            val = float(getattr(row, "avg_monthly_uv") or 0.0)
            lines.append(f"{i}. {ch}: {val:,.0f}".replace(",", " "))
        return "\n".join(lines)

    if is_q3:
        sql = """
        WITH last_months AS (
          SELECT DISTINCT month_partition
          FROM tv
          ORDER BY month_partition DESC
          LIMIT 3
        ),
        monthly AS (
          SELECT t.month_partition, t.content_playback_type, SUM(t.daily_total_minute) AS month_minutes
          FROM tv t
          JOIN last_months m USING(month_partition)
          GROUP BY 1,2
        ),
        avg3 AS (
          SELECT content_playback_type, AVG(month_minutes) AS avg_monthly_minutes
          FROM monthly
          GROUP BY 1
        )
        SELECT content_playback_type, avg_monthly_minutes
        FROM avg3
        ORDER BY avg_monthly_minutes DESC
        """
        df = con.execute(sql).df()
        if not len(df):
            return f"Nema podataka za zadnja 3 mjeseca ({months_str})."

        lines = [f"AVG mjesecne minute po content_playback_type (zadnja 3 mjeseca: {months_str}):"]
        for row in df.itertuples(index=False):
            t = getattr(row, "content_playback_type")
            val = float(getattr(row, "avg_monthly_minutes") or 0.0)
            lines.append(f"- {t}: {val:,.2f} min".replace(",", " "))
        return "\n".join(lines)

    return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(payload: ChatRequest):
    try:
        question = last_user_text(payload.messages)
        print("CHAT HIT:", question)

        if not question:
            raise HTTPException(status_code=400, detail="No user message provided.")

        # 0) greeting
        if is_greeting_or_intro(question):
            return {"type": "message", "content": greeting_answer(), "model": MODEL}

        # 1) faq
        if is_faq_question(question):
            return {"type": "message", "content": faq_answer(), "model": MODEL}

        # 2) FAST ANALYTICS (NO LLM, super fast)
        fa = fast_analytics_answer(question)
        if fa is not None:
            print("ROUTE: fast_analytics")
            return {"type": "message", "content": fa, "model": "duckdb"}

        # 3) FAST RAG only for definitions
        if looks_like_definition_lookup(question):
            print("ROUTE: fast_rag")
            text = fast_rag_answer(question)
            return {"type": "message", "content": text, "model": FAST_RAG_MODEL}

        # 4) agent for everything else
        print("ROUTE: agent")
        ag = await get_agent()
        lg_msgs = to_lg_messages(payload.messages, MAX_HISTORY_MESSAGES)

        async def _run_agent():
            try:
                return await ag.ainvoke({"messages": lg_msgs}, config={"timeout": AGENT_TIMEOUT_S})
            except TypeError:
                return await ag.ainvoke({"messages": lg_msgs})

        try:
            result = await asyncio.wait_for(_run_agent(), timeout=AGENT_TIMEOUT_S)
        except asyncio.TimeoutError:
            return {
                "type": "message",
                "content": (
                    "Agent timeout: nisam stigao izracunati odgovor na vrijeme.\n"
                    "Savjet: za brojke probaj format 'for <KANAL> over the last <N> days' "
                    "ili pitaj 'Top 5 ... last 3 months'."
                ),
                "model": MODEL,
            }

        msgs = result.get("messages", []) if isinstance(result, dict) else []
        text = ""
        if msgs:
            last = msgs[-1]
            text = _get(last, "content", "") or ""

        if not text:
            text = "No response content"

        return {"type": "message", "content": text, "model": MODEL}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))