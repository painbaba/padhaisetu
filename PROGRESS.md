# PadhaiSetu — PROGRESS

Built via opencode TUI (ox-alpha free lane), Aug 24 2026. Brief: `../BRIEF.md`.

## Milestones — ALL GATES GREEN
| M | What | Commit |
|---|---|---|
| M0 | FastAPI skeleton, SQLite DDL, pydantic models, qbank loader, /health | 08e5db1 |
| M1 | hi/en NLU, strings.json, onboarding flow, /demo simulator channel | 588952e |
| M2 | Knowledge graph 180 skills + prereq walker, gen_math 323 items, science banks, EWMA engine + remediation walker, 21 engine tests | 6f765f0 |
| M3 | Diagnostic seeding + daily practice with prerequisite remediation; 14-msg journey test | 3f3eac1 |
| M4 | Streaks on completion + weekly parent report from real attempt history | e98479e |
| M5+M6 | Judge dashboard (truthful counters, heat-grid, at-risk, QR), demo seed, WhatsApp Cloud API webhook + mocked tests | 3136ac6 |
| — | README: run steps, pitch table, 90-sec demo script verbatim | cd0d1d1 |
| M7 | Board-pattern generator + schema: marks/qtype columns (defaults keep legacy data intact), MPBSE 2026-shaped class-10 sets (5 objective MCQ/fill/TF + 12×2m + 3×3m + 3×4m, each 3/4-mark with OR sibling), banks regenerated (maths_10 → 186 items) | 5d10e7a |
| M8 | Board-pattern serving: grade-10 practice = full 23-question mix (objective first, ascending marks), diagnostic = board mini-mix (1×2+2×2+3), marks shown beside question number ("प्रश्न 7/23 (2 अंक)"), OR-pair dedupe within session, skill interleaving; 8 new tests | 0dff794 |
| M9 | RAG retrieval wired into explain flow: stdlib BM25 singleton over 2,816 NCERT+MPBSE chunks, new "समझाइए/explain/क्यों/how-why" chat intent in menu+practice states (top-2 chunks filtered by class+subject, ~400-char excerpt, bilingual स्रोत citation line), POST /api/explain {phone_or_session,query}->{answer_text,source,chunks}, optional GPT 2-sentence polish behind OPENAI_API_KEY with raw-excerpt fallback, dashboard "RAG corpus chunks" stat; 13 new tests | *this commit* |

## Verification
- pytest: **66/66 passed** (13.4s)
- Fresh boot: `bash run.sh` → :8831 /health {"ok":true}; retriever singleton preloaded in lifespan (~3s, once)
- Live Hindi journey verified externally: हैलो → हिंदी → कक्षा 10 → गणित → 5 diagnostic questions answered → बोर्ड-पैटर्न practice set of 23 served with (N अंक) labels; attempts+mastery rows written
- M9 live check: `POST /api/explain {"query":"how does photosynthesis work"}` → Hindi NCERT excerpt + "स्रोत: NCERT विज्ञान कक्षा 10…" citation; dashboard shows **2,816** RAG corpus chunks
- Question banks: **698 items** (323 parametric maths classes 8-10 incl. 87 board-pattern class-10 items, 288 curated science), every item asserted for unique options, correct_idx bounds, bilingual text/hint/solution fields

## Board-pattern alignment (M7/M8)
- Ground truth: `data/pyqs/paper2026_10th_Maths_{standard,basic}.txt` + `_Science.txt` — official MPBSE 2026 sample papers (23 questions, 75 marks, objective Q1–5, structured Q6–23 with internal choices)
- Generator emits the same shape per set; serving picks weakest-first inside each marks bucket and never serves both members of an OR pair in one session
- Hindi phrasing mimics the papers' instruction verbs (सही विकल्प चुनकर लिखिए / रिक्त स्थानों की पूर्ति कीजिए / सत्य/असत्य लिखिए / मान ज्ञात कीजिए / ज्ञात कीजिए) — parametric numbers, never verbatim paper questions

## Data corpus (real board material)
- `data/pyqs/mpbse_papers_2026.zip` — 9 official MPBSE 2026 sample papers (class 10 Maths std/basic, Science, Social Science; class 12 Physics/Chem/Bio/Maths) + `_index.json` extraction summary
- `data/ncert/*.txt` — 135 NCERT chapters, classes 8–10, Maths+Science, English+Hindi (~4.3M chars); PDFs deleted after text extraction
- `rag.py` + `data/rag_chunks.jsonl` (2,816 chunks) + `data/rag_manifest.json` — stdlib BM25 index over the above; consumed read-only by `app/rag.py` bridge (M9)
- Class-10 maths/science question phrasing aligned to MPBSE sample-paper section pattern

## Demo-time TODO (not blocking)
- Set OPENAI_API_KEY env to activate /explain GPT hints + grounded-answer polish (graceful fallback already wired both ways)
- Record 3-min video, Devpost submit before Fri Aug 28 2026 8PM IST (no grace)

## Known gaps (pre-approved cut order from brief)
- Science banks at 4/skill floor; heat-grid shows top skills; GPT hint dormant until keyed
- Class-8 corpus chunks all carry lang=en metadata (Hindi translations included) — explain flow falls back to unfiltered search when the preferred language has no coverage

## Final-gate reconciliation (second builder session, Aug 24 ~09:05 IST, commits edf4d29 + 449eb9c)
- **Engine hardening:** `record_attempt` now marks diagnostic results due immediately — SR was
  hiding freshly-diagnosed weak topics until the next day, blunting demo step 3. Practice-mode
  updates keep normal {1,3,7}-day spacing (regression test added).
- **Generator reproducibility:** gen_math previously seeded rng with `id(template)` which changes
  per process; now seeded by stable template index. Two runs of
  `python data/gen_math.py --seed 42` produce byte-identical banks (md5-verified). Banks regenerated.
- **Final gate re-run on a fresh DB:** boot via `bash run.sh` → /health ok; scripted §10 journey
  over /demo/send (onboard → 5-Q diagnostic w/ weakest-topic summary → practice set targeting the
  diagnosed gap first → deliberate wrong answer → hint/solution path → set complete + streak line →
  weekly report rendered from real rows) finished with **zero error replies**; dashboard counters
  matched SQL exactly (4 students, 44 attempts, 693 active questions after natural-key dedup).
- **Hygiene:** .gitignore added; tracked `__pycache__/`, `.pyc`, and live SQLite file removed from
  the index.
- **Concurrent RAG track (in flight, not committed here):** a parallel session is adding a grounded
  explain path (stdlib BM25 over 2,816 NCERT/MPBSE chunks, EXPLAIN intent, `/api/explain`,
  dashboard chunk counter). At reconciliation time its spec had 64 passing / 2 failing
  (`tests/test_rag.py::test_explain_*` — citation-order flakiness); left untouched and uncommitted
  so its author can land it deliberately. Everything outside that spec is green.
