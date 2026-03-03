# BroadcastIQ

BroadcastIQ is an IPTV analytics assistant that enables natural language exploration of monthly channel performance datasets using an Agentic RAG architecture.
The system allows business stakeholders to query structured IPTV KPI data without writing SQL, while maintaining data governance and accuracy.

---

### LOOM VIDEO

Link: https://www.loom.com/share/3c82379fdcc84da3adba1a060690d85a

---

### GitHub Repository:

Link: https://github.com/gpuda/aie-certification-challenge

---

## What This Project Does:
BroadcastIQ enables:

- Natural-language KPI queries over IPTV datasets
- Channel ranking and aggregation (Top N, averages, comparisons)
- Playback-type performance analysis
- Controlled routing between internal RAG data and external web search (Tavily)

---
## Architecture Overview

- **Frontend:** Next.js + shadcn/ui  
- **Backend:** FastAPI  
- **Agent Framework:** LangGraph (ReAct Agent)  
- **LLM:** gpt-5-mini  
- **Embeddings:** text-embedding-3-small  
- **Vector Database:** Qdrant  
- **Evaluation:** RAGAS  

Detailed Certification Challenge documentation (Tasks 1–7) is available here:
➡️ [Certification Writeup](docs/certification_readme.md)

---
## How to Run Locally

### Backend (http://localhost:8000): 
cd api
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app

### Frontend (http://localhost:3000):
npm run dev


### Evaluation notebooks:
api/notebooks/ingest_tv_data.ipynb
api/notebooks/generate_testset_tv.ipynb
api/notebooks/evaluate_tv.ipynb
api/notebooks/evaluate_tv_improved.ipynb

### Project structure
api/        -> main.py, agent.py, notebooks, dataset (tv_data)
app/        -> Next.js frontend
docs/       -> Certification Challenge writeup (certification_readme.md)
