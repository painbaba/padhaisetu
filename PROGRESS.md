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

## Verification
- pytest: **53/53 passed** (9.3s)
- Fresh boot: `bash run.sh` → :8831 /health {"ok":true}
- Live Hindi journey verified externally: हैलो → हिंदी → कक्षा 10 → गणित → 5 diagnostic questions answered → बोर्ड-पैटर्न practice set of 23 served with (N अंक) labels; attempts+mastery rows written
- Question banks: **698 items** (323 parametric maths classes 8-10 incl. 87 board-pattern class-10 items, 288 curated science), every item asserted for unique options, correct_idx bounds, bilingual text/hint/solution fields

## Board-pattern alignment (M7/M8)
- Ground truth: `data/pyqs/paper2026_10th_Maths_{standard,basic}.txt` + `_Science.txt` — official MPBSE 2026 sample papers (23 questions, 75 marks, objective Q1–5, structured Q6–23 with internal choices)
- Generator emits the same shape per set; serving picks weakest-first inside each marks bucket and never serves both members of an OR pair in one session
- Hindi phrasing mimics the papers' instruction verbs (सही विकल्प चुनकर लिखिए / रिक्त स्थानों की पूर्ति कीजिए / सत्य/असत्य लिखिए / मान ज्ञात कीजिए / ज्ञात कीजिए) — parametric numbers, never verbatim paper questions

## Data corpus (real board material)
- `data/pyqs/mpbse_papers_2026.zip` — 9 official MPBSE 2026 sample papers (class 10 Maths std/basic, Science, Social Science; class 12 Physics/Chem/Bio/Maths) + `_index.json` extraction summary
- `data/ncert/*.txt` — 135 NCERT chapters, classes 8–10, Maths+Science, English+Hindi (~4.3M chars); PDFs deleted after text extraction
- Class-10 maths/science question phrasing aligned to MPBSE sample-paper section pattern

## Demo-time TODO (not blocking)
- Set OPENAI_API_KEY env to activate /explain GPT hint endpoint (graceful fallback already wired)
- Record 3-min video, Devpost submit before Fri Aug 28 2026 8PM IST (no grace)

## Known gaps (pre-approved cut order from brief)
- Science banks at 4/skill floor; heat-grid shows top skills; GPT hint dormant until keyed
