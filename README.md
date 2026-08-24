# PadhaiSetu (पढ़ाई सेतु) — Adaptive Vernacular Tutor for MP Board

A WhatsApp-style adaptive practice tutor for **MP Board class 8–10 Maths & Science**, in
**Hindi (default) and English**. A student chats: gets a short diagnostic quiz, then daily
practice sets of 5 MCQs that target their weakest sub-skills using a knowledge-graph mastery
model. Wrong answers trigger prerequisite remediation — the engine walks down the topic graph
and rebuilds fundamentals before climbing back. Parents get a weekly Hindi progress report.

**No LLM in the critical path** — the adaptive engine is deterministic and fully unit-tested.
An optional GPT hint-explainer sits behind `OPENAI_API_KEY` and falls back gracefully.

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
python -m pytest tests/ -q     # 45 tests: engine math, walker, flows, channels, dashboard
```

## Regenerate / extend the question banks

```bash
python data/gen_math.py --seed 42   # parametric generator -> data/qbank/maths_*.json
```

30 templates × 12 variants across classes 8–10 (rationals ops, linear/quadratic equations,
squares/cubes, percentages, mensuration, exponents, direct/inverse proportion, factorisation,
polynomials, AP, trigonometry, coordinate geometry, statistics, probability). Science banks are
curated static bilingual MCQs (`science_{8,9,10}.json`). Every question carries a hint and a
2-line solution in **both** languages.

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
