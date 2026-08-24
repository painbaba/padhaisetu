#!/usr/bin/env python3
"""Build a fully static, GitHub-Pages-deployable mirror of PadhaiSetu.

Everything runs client-side: chat UI, onboarding, diagnostic, practice,
remediation, board-pattern sets, mock exam, and BM25 search over the RAG
corpus. No server needed. Output: docs/ (GitHub Pages root).
"""
import json, os, sqlite3, re, html

ROOT = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else r"C:\Users\HP\hackathon-research\padhaisetu"
REPO = os.path.join(ROOT, "repo")
os.chdir(REPO)

db = sqlite3.connect("data/padhaisetu.db")
db.row_factory = sqlite3.Row
qs = [dict(r) for r in db.execute("SELECT * FROM questions WHERE active=1")]
strings = json.load(open("app/flows/strings.json", encoding="utf-8"))
graphs = {}
for subj in ("maths", "science"):
    d = json.load(open(f"data/graph_{subj}.json", encoding="utf-8"))
    graphs[subj] = d["classes"] if isinstance(d, dict) else d

os.makedirs("docs", exist_ok=True)

# ---------- data payload ----------
payload = {
    "strings": strings,
    "graphs": graphs,
    "questions": [
        {
            "id": q["id"], "subject": q["subject"], "grade": q["grade"],
            "skill_id": q["skill_id"], "difficulty": q["difficulty"],
            "text_hi": q["text_hi"], "text_en": q["text_en"],
            "options": (q["options_json"] or "").split("|"),
            "correct_idx": q["correct_idx"],
            "hint_hi": q["hint_hi"], "hint_en": q["hint_en"],
            "solution_hi": q["solution_hi"], "solution_en": q["solution_en"],
            "marks": q["marks"] or 1, "qtype": q["qtype"] or "mcq",
        }
        for q in qs
    ],
}
with open("docs/data.js", "w", encoding="utf-8") as f:
    f.write("window.PS_DATA=")
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

# ---------- RAG corpus for client-side search (top slices per class/subject/lang) ----------
chunks = []
for line in open("data/rag_chunks.jsonl", encoding="utf-8"):
    c = json.loads(line)
    chunks.append({"t": c["text"], "src": c["source"], "cls": c["class"], "sub": c["subject"], "lang": c["lang"]})
with open("docs/rag.js", "w", encoding="utf-8") as f:
    f.write("window.PS_RAG=")
    json.dump(chunks, f, ensure_ascii=False, separators=(",", ":"))

print("questions:", len(qs), "| chunks:", len(chunks))
print("docs/data.js:", os.path.getsize("docs/data.js") // 1024, "KB | docs/rag.js:",
      os.path.getsize("docs/rag.js") // 1024, "KB")

# ---------- index.html ----------
INDEX = r"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PadhaiSetu — अपना AI शिक्षक (MP Board)</title>
<style>
:root{--g:#16a34a;--gd:#15803d;--bg:#f6faf7;--ink:#0f172a;--mut:#64748b;--card:#fff}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--ink)}
header{background:linear-gradient(135deg,#166534,#16a34a);color:#fff;padding:18px 20px;display:flex;align-items:center;gap:12px}
header h1{font-size:1.25rem;font-weight:700}
header .tag{margin-inline-start:auto;font-size:.75rem;background:#ffffff22;padding:4px 10px;border-radius:99px}
#phone{max-width:430px;margin:20px auto;background:var(--card);border-radius:24px;box-shadow:0 12px 40px #0002;overflow:hidden;border:1px solid #e2e8f0}
#bar{background:#111b21;color:#fff;padding:10px 16px;display:flex;align-items:center;gap:10px;font-size:.9rem}
.dot{width:36px;height:36px;border-radius:50%;background:var(--g);display:flex;align-items:center;justify-content:center;font-weight:800}
#chat{height:520px;overflow-y:auto;padding:14px;background:#efeae2;display:flex;flex-direction:column;gap:8px}
.msg{max-width:82%;padding:8px 12px;border-radius:12px;font-size:.92rem;line-height:1.45;white-space:pre-wrap}
.bot{background:#fff;align-self:flex-start;border-top-left-radius:4px;box-shadow:0 1px 2px #0001}
.me{background:#d9fdd3;align-self:flex-end;border-top-right-radius:4px}
.time{font-size:.65rem;color:var(--mut);text-align:right;margin-top:2px}
form{display:flex;gap:8px;padding:10px;background:#f0f2f5}
input{flex:1;border:none;border-radius:99px;padding:11px 16px;font-size:.95rem;outline:none}
button{border:none;background:var(--g);color:#fff;width:44px;height:44px;border-radius:50%;cursor:pointer;font-size:1.1rem}
button:hover{background:var(--gd)}
#stats{display:flex;gap:8px;flex-wrap:wrap;padding:10px 14px;background:#fff;border-bottom:1px solid #e2e8f0;font-size:.72rem;color:var(--mut)}
.pill{background:#f1f5f9;border-radius:99px;padding:3px 10px}
a.repo{color:#fff;font-size:.75rem;text-decoration:none;background:#ffffff22;padding:4px 10px;border-radius:99px}
</style>
</head>
<body>
<header>
  <h1>पढ़ाई सेतु <span style="font-weight:400">PadhaiSetu</span></h1>
  <span class="tag">MP Board · कक्षा 8–10 · हिंदी/English</span>
  <a class="repo" href="https://github.com/painbaba/padhaisetu" target="_blank">source ↗</a>
</header>
<div id="phone">
  <div id="bar"><div class="dot">प</div><div><b>PadhaiSetu Tutor</b><br><span style="font-size:.68rem;color:#86efac">online — full demo, no server</span></div></div>
  <div id="stats"></div>
  <div id="chat" aria-live="polite"></div>
  <form id="f"><input id="i" placeholder="उत्तर भेजिए… (help = मदद)" autocomplete="off"><button>➤</button></form>
</div>
<script src="rag.js"></script>
<script src="data.js"></script>
<script src="app.js"></script>
</body></html>"""
# ---------- SINGLE-FILE build: everything inline so Pages can never race ----------
data_js = open("docs/data.js", encoding="utf-8").read()
rag_js = open("docs/rag.js", encoding="utf-8").read()
app_js = open("docs/app.js", encoding="utf-8").read()
INDEX = INDEX.replace('<script src="rag.js"></script>\n<script src="data.js"></script>\n<script src="app.js"></script>',
                      "<script>\n" + rag_js + "\n</script>\n<script>\n" + data_js + "\n</script>\n<script>\n" + app_js + "\n</script>")
open("docs/index.html", "w", encoding="utf-8").write(INDEX)
print("docs/index.html written:", os.path.getsize("docs/index.html") // 1024, "KB total")
