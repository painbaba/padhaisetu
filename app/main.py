"""FastAPI entrypoint. Mounts simulator + whatsapp channels and the judge dashboard."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from . import db, qbank, rag, config
from .channels import simulator, whatsapp
from .dashboard import router as dashboard_router
from .flows import get_or_create_user, load_session, ragflow


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    qbank.ensure_loaded()
    try:
        rag.get_retriever()  # BM25 over 2816 NCERT/MPBSE chunks; loaded once (~3s)
    except Exception:
        import traceback
        traceback.print_exc()  # app still boots; explain degrades to no-hits
    yield


app = FastAPI(title="PadhaiSetu", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True}


class ExplainRequest(BaseModel):
    question_id: int
    lang: str = "hi"


class ExplainResponse(BaseModel):
    hint: str
    source: str  # "gpt" | "stored"


@app.post("/explain", response_model=ExplainResponse)
async def explain(req: ExplainRequest) -> ExplainResponse:
    """Optional GPT hint path. Falls back to the stored bilingual solution on ANY failure.
    Never blocks the chat flow; works with no OPENAI_API_KEY at all."""
    row = qbank.get_question(req.question_id)
    if row is None:
        return ExplainResponse(hint="", source="stored")
    stored = row["hint_hi"] if req.lang == "hi" else row["hint_en"]
    stored = stored or row["solution_hi" if req.lang == "hi" else "solution_en"]
    if not config.OPENAI_API_KEY:
        return ExplainResponse(hint=stored or "", source="stored")
    try:
        import httpx

        prompt = (
            "Tum ek MP Board tutor ho. Is MCQ ka simple {lang} hint do (max 2 lines), "
            "answer mat batao.\nPrashn: {q}\nVikalp: {o}".format(
                lang="Hindi" if req.lang == "hi" else "English",
                q=row["text_hi"] if req.lang == "hi" else row["text_en"],
                o="; ".join(row["options_json"].split("|")),
            )
        )
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                json={
                    "model": config.OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                },
            )
            r.raise_for_status()
            data = r.json()
            hint = data["choices"][0]["message"]["content"].strip()
            return ExplainResponse(hint=hint or stored or "", source="gpt" if hint else "stored")
    except Exception:
        return ExplainResponse(hint=stored or "", source="stored")


class RagExplainRequest(BaseModel):
    phone_or_session: str
    query: str
    lang: str | None = None  # optional override; defaults to the user's saved lang


class RagExplainResponse(BaseModel):
    answer_text: str
    source: str
    chunks: list[dict]


@app.post("/api/explain", response_model=RagExplainResponse)
def api_explain(req: RagExplainRequest) -> RagExplainResponse:
    """Grounded explain: BM25 top-2 chunks filtered by the student's class+subject,
    best excerpt + bilingual citation; GPT polish only when OPENAI_API_KEY is set.
    Sync def on purpose -> runs in FastAPI's threadpool."""
    user = get_or_create_user(req.phone_or_session.strip())
    lang = req.lang or user["lang"]
    _, ctx = load_session(user["id"])
    res = rag.explain(
        req.query, cls=user["grade"] or None,
        subj=ctx.get("subject") or None, lang=lang)
    answer_text, source = ragflow.compose(res, lang)
    return RagExplainResponse(answer_text=answer_text, source=source,
                              chunks=res["chunks"])


app.include_router(simulator.router)
app.include_router(whatsapp.router)
app.include_router(dashboard_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)
