# PadhaiSetu (पढ़ाई सेतु) — Adaptive Vernacular Tutor for MP Board

A WhatsApp-style adaptive practice tutor for **MP Board class 8–10 Maths & Science**, in
**Hindi (default) and English**, aligned with the **official MPBSE 2026 sample papers**
(class-10 sets follow the real board shape: objective section first, then 2/3/4-mark
questions with OR alternatives). A student chats: gets a short diagnostic quiz, then daily
practice that targets their weakest sub-skills using a knowledge-graph mastery model.
Wrong answers trigger prerequisite remediation — the engine walks down the topic graph
and rebuilds fundamentals before climbing back. Parents get a weekly Hindi progress report.
Students can also sit a **full mock board exam** ("mock" / "मॉक" / "पेपर" or menu option 4):
a 23-question MPBSE-pattern paper with no hints or remediation, skip allowed, a bilingual
section-wise scorecard, and a one-tap handoff into practice targeting the weakest mock skills.

**No LLM in the critical path** — the adaptive engine is deterministic and fully unit-tested.
An optional GPT hint-explainer sits behind `OPENAI_API_KEY` and falls back gracefully.
Free-text **"why/how" questions get grounded answers**: a stdlib BM25 retriever fetches the
top-matching passages from a **2,816-chunk corpus grounded in 135 NCERT chapters + official
MPBSE 2026 sample papers**, replies with an excerpt + bilingual citation ("स्रोत: NCERT विज्ञान
कक्षा 10, अध्याय 9"), and only polishes the wording via GPT when a key is present.

---

## Run it

```bash
# fresh clone
bash run.sh                 # uvicorn app.main:app --port 8831
# in another tab (makes the dashboard look alive)
python data/seed.py
```

- Chat simulator (primary demo channel): http://localhost:8831/demo
- Judge dashboard: http://localhost:8831/dashboard
- Health: http://localhost:8831/health

### Environment variables (all optional)

| Var | Default | Purpose |
|---|---|---|
| `PORT` | 8831 | HTTP port |
| `PADHAISETU_DB` | `data/padhaisetu.db` | SQLite file |
| `TZ` | Asia/Kolkata | timezone everywhere |
| `OPENAI_API_KEY` | *(unset)* | enables `/explain` GPT hints; unset = stored bilingual solutions |
| `WHATSAPP_VERIFY_TOKEN` | padhaisetu-verify | Meta webhook handshake |
| `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_ID` | *(unset)* | Cloud API send; unset = webhook parses but drops |

## Tests

```bash
python -m pytest tests/ -q     # 80 tests: engine math, walker, flows, channels, dashboard, board pattern, RAG explain, mock exam
```

## Regenerate / extend the question banks

```bash
python data/gen_math.py --seed 42   # parametric generator -> data/qbank/maths_*.json
```

30 templates × 12 variants across classes 8–10 (rationals ops, linear/quadratic equations,
squares/cubes, percentages, mensuration, exponents, direct/inverse proportion, factorisation,
polynomials, AP, trigonometry, coordinate geometry, statistics, probability), **plus class-10
board-pattern sets shaped like the official MPBSE 2026 sample papers** (`data/pyqs/paper2026_*`):
per set — 5 objective items (MCQ / fill-in-blank / true-false), then 12×2-mark, 3×3-mark and
3×4-mark questions, every 3/4-mark slot carrying an अथवा/OR alternative sibling. Bilingual
phrasing mirrors the papers (सही विकल्प चुनकर लिखिए / रिक्त स्थानों की पूर्ति कीजिए /
मान ज्ञात कीजिए …) with fully parametric numbers. Science banks are curated static bilingual
MCQs (`science_{8,9,10}.json`). Every question carries a hint and a 2-line solution in
**both** languages.

## How the engine works

- **Mastery EWMA:** `score <- clamp(0.75*score + 0.25*(correct?1:0) * speed_bonus)`,
  speed_bonus = 1.15 if answered under 20 s; `seen += 1`.
- **Spaced repetition:** due_after = now + {1, 3, 7} days by band (<0.45, <0.7, else).
- **Weakness ranking:** daily set prefers skills where due_after passed AND score×weight lowest.
- **Diagnostic:** 5-question span quiz, one representative skill per major chapter, seeds mastery.
- **Remediation:** on a wrong answer, DFS down prerequisites to the first skill below 0.45,
  serve an easier question there behind a bridge note ("पहले आधार मजबूत करते हैं"), max 2 per turn.
- **Knowledge graph:** ≥72 maths skills (3 classes) + ≥60 science skills, cross-class prereq
  edges (a class-10 quadratic slip can drop you to class-8 factorisation).

## Endpoints

| Route | Purpose |
|---|---|
| `GET /health` | liveness, returns `{"ok": true}` |
| `GET /demo` | phone-mockup chat UI (WhatsApp-style) |
| `POST /demo/send` | `{phone, text}` -> bot replies |
| `GET /demo/poll?phone&after` | incremental message poll |
| `POST /explain` | optional GPT hint w/ stored fallback |
| `POST /api/explain` | grounded explain: `{phone_or_session, query}` -> `{answer_text, source, chunks[]}` (BM25 top-2, class+subject filtered, bilingual citation) |
| `GET /dashboard` | judge dashboard (truthful counters, heat-grid, at-risk, QR placeholder) |
| `GET/POST /whatsapp/webhook` | Meta Cloud API verify + receive |

---

## Why now (pitch numbers)

| Fact | Number | Source |
|---|---|---|
| Squirrel AI cumulative students | 43M | dossier 05_logistics-education-civic.md |
| Yuanfudao users / AI devices | 400M users; 1M learning devices sold in 16 months post-ban | same |
| BYJU'S status | insolvency proceedings (SC-restored) | news, Aug 2026 |
| DIKSHA reality | 22.5M users, CONTENT REPO — zero adaptivity | digitalindia |
| MP Board angle | Hindi-medium board exams decide tier-3 futures; no consumer adaptive product exists (no live evidence found, med-high confidence) | fleet research |

## 90-second demo script

1. "China's Squirrel AI diagnosed 43 MILLION students sub-skill by sub-skill. India's biggest
   edtech is bankrupt, and DIKSHA is a PDF library. The method works — nobody built it for the
   MP Board kid in Satna."
2. Phone out: scan QR → /demo → Hindi chat → diagnostic quiz in 5 taps → engine shows weakest topics.
3. Answer one WRONG deliberately → watch it drop to the prerequisite skill, rebuild, climb back.
4. Dashboard: mastery heat-grid fills live; streak counter ticks; parent-report preview renders.
5. Close: "We didn't put a teacher in a phone. We put a diagnosis."

---

Scope fence honoured: chat simulator channel (+ wired-but-untested WhatsApp Cloud API), NLU
router, knowledge graph + mastery engine, question banks, diagnostic/daily-practice/remediation
flows, streaks, weekly parent report, judge dashboard. Out of scope: payments, real LLM
dependency, voice notes, multi-board support, admin auth, mobile app.
