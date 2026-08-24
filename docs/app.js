/* PadhaiSetu static demo engine — full journey client-side */
(function () {
  const D = window.PS_DATA, RAG = window.PS_RAG;
  const $ = (s) => document.querySelector(s);
  const chat = $("#chat");

  // ---------- state ----------
  let S = { lang: null, grade: null, subject: null, mode: "onb", q: [], qi: 0, score: {}, answers: [], mock: false, streak: 0 };

  // ---------- helpers ----------
  const esc = (s) => s; // textContent used everywhere
  function bubble(text, me) {
    const d = document.createElement("div");
    d.className = "msg " + (me ? "me" : "bot");
    d.textContent = text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
    if (!me) { const t = document.createElement("div"); t.className = "time"; t.textContent = "✓✓"; chat.appendChild(t); }
  }
  function say(...lines) { lines.forEach((l) => setTimeout(() => bubble(l, false), 350)); }

  // ---------- BM25 over RAG ----------
  const STOP = new Set("a an the is are was were be to of in on at for and or not it this that का के की है हैं में से पर और या नहीं भी यह वह इस उस कि जो तो".split(" "));
  function toks(t) { return t.toLowerCase().normalize("NFC").match(/[\p{L}\p{N}]+/gu)?.filter((w) => w.length > 1 && !STOP.has(w)) || []; }
  const DF = {};
  RAG.forEach((c) => new Set(toks(c.t)).forEach((w) => DF[w] = (DF[w] || 0) + 1));
  const AVG = RAG.reduce((a, c) => a + toks(c.t).length, 0) / RAG.length;
  function bm25(query, cls, subj) {
    const qt = toks(query), out = [];
    RAG.forEach((c, i) => {
      if (cls && String(c.cls) !== String(cls)) return;
      if (subj && c.sub !== subj) return;
      const tt = toks(c.t), tf = {};
      tt.forEach((w) => tf[w] = (tf[w] || 0) + 1);
      let s = 0;
      qt.forEach((w) => {
        const f = tf[w]; if (!f || !DF[w]) return;
        const idf = Math.log(1 + (RAG.length - DF[w] + 0.5) / (DF[w] + 0.5));
        s += idf * (f * 2.5) / (f + 1.5 * (1 - 0.75 + 0.75 * tt.length / AVG));
      });
      if (s > 0) out.push([s, i]);
    });
    return out.sort((a, b) => b[0] - a[0]).slice(0, 2).map(([s, i]) => RAG[i]);
  }

  // ---------- question banks ----------
  const Q = D.questions;
  const byGradeSubj = (g, s) => Q.filter((q) => q.grade === g && q.subject === s);
  function boardPattern(g, subj) {
    const pool = byGradeSubj(g, subj);
    const pick = (f, n) => shuffle(pool.filter(f)).slice(0, n);
    const obj = pick((q) => q.marks === 1, 5);
    const two = pick((q) => q.marks === 2, 12);
    const three = pick((q) => q.marks === 3, 3);
    const four = pick((q) => q.marks === 4, 3);
    return [...obj, ...two, ...three, ...four];
  }
  function diagnostic(g, subj) {
    const pool = byGradeSubj(g, subj);
    const seen = new Set(); const out = [];
    for (const sk of new Set(pool.map((q) => q.skill_id))) {
      const cand = pool.filter((q) => q.skill_id === sk);
      if (!cand.length) continue;
      const q = cand[Math.floor(Math.random() * cand.length)];
      if (!seen.has(q.id)) { seen.add(q.id); out.push(q); if (out.length >= 5) break; }
    }
    return out.length ? out : shuffle(pool).slice(0, 5);
  }
  function shuffle(a) { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1));[a[i], a[j]] = [a[j], a[i]]; } return a; }

  // ---------- flows ----------
  const L = () => S.lang || "hi";
  const T = (hi, en) => (L() === "hi" ? hi : en);

  function start() {
    say("नमस्ते! 🙏 Welcome to पढ़ाई सेतु — your MP Board AI tutor.",
      "भाषा चुनिए:\n1) हिंदी\n2) English");
  }
  function onb(input) {
    if (S.grade) return chooseSubject(input);
    if (!S.lang) {
      S.lang = input.trim().startsWith("1") ? "hi" : input.trim().startsWith("2") ? "en" : null;
      if (!S.lang) return say(T("कृपया 1 या 2 भेजिए।", "Please send 1 or 2."));
      return say(T("भाषा: हिंदी ✓\nआप किस कक्षा में हैं? 8, 9 या 10 भेजिए।", `Language: English ✓\nWhich class are you in? Send 8, 9 or 10.`));
    }
    const g = parseInt(input.trim());
    if (![8, 9, 10].includes(g)) return say(T("8, 9 या 10 भेजिए।", "Send 8, 9 or 10."));
    S.grade = g;
    return say(T(`कक्षा ${g} ✓\nविषय चुनिए:\n1) गणित\n2) विज्ञान`, `Class ${g} ✓\nChoose subject:\n1) Maths\n2) Science`));
  }
  function chooseSubject(input) {
    const m = input.trim().startsWith("1") ? "maths" : input.trim().startsWith("2") ? "science" : null;
    if (!m) return say(T("1 या 2 भेजिए।", "Send 1 or 2."));
    S.subject = m; S.mode = "menu";
    renderStats();
    say(
      T(`मुख्य मेनू — कक्षा ${S.grade} ${m === "maths" ? "गणित" : "विज्ञान"}\n\n1 = डायग्नोस्टिक टेस्ट\n2 = दैनिक अभ्यास\n3 = मॉक बोर्ड पेपर\n4 = कोई भी प्रश्न पूछें (उत्तर NCERT से, स्रोत के साथ)\nhelp = मदद`,
        `Main menu — Class ${S.grade} ${m}\n\n1 = Diagnostic test\n2 = Daily practice\n3 = Mock board paper\n4 = Ask anything (grounded in NCERT, with source)\nhelp = help`)
    );
  }
  function startDiag() {
    S.mode = "diag"; S.q = diagnostic(S.grade, S.subject); S.qi = 0; S.answers = [];
    askCurrent();
  }
  function startPractice(onlySkills) {
    let pool = byGradeSubj(S.grade, S.subject);
    if (onlySkills && onlySkills.length) {
      const set = new Set(onlySkills);
      const filtered = pool.filter((q) => set.has(q.skill_id));
      if (filtered.length >= 3) pool = filtered;
    }
    S.mode = "practice"; S.q = shuffle(pool).slice(0, 10); S.qi = 0; S.answers = [];
    say(T("आज का अभ्यास — 10 प्रश्न। शुभकामनाएँ! 💪", "Today's practice — 10 questions. Good luck! 💪"));
    askCurrent();
  }
  function startMock() {
    S.mode = "mock"; S.mock = true; S.q = boardPattern(S.grade, S.subject); S.qi = 0; S.answers = [];
    say(T("🎓 मॉक बोर्ड पेपर — MPBSE 2026 पैटर्न\n23 प्रश्न · 75 अंक\nखंड: Q1–5 वस्तुनिष्ठ → Q6–17 (2 अंक) → Q18–20 (3 अंक) → Q21–23 (4 अंक)\n'छोड़ें' से स्किप करें। शुभकामनाएँ!",
      "🎓 MOCK BOARD PAPER — MPBSE 2026 pattern\n23 questions · 75 marks\nSections: Q1–5 objective → Q6–17 (2m) → Q18–20 (3m) → Q21–23 (4m)\nSend 'skip' to skip. All the best!"));
    setTimeout(askCurrent, 900);
  }
  function askCurrent() {
    const q = S.q[S.qi];
    if (!q) return finishSet();
    const label = S.mode === "mock" ? `प्रश्न ${S.qi + 1}/${S.q.length} (${q.marks} अंक):` : `प्रश्न ${S.qi + 1}/${S.q.length}:`;
    const body = `${label}\n${L() === "hi" ? q.text_hi : q.text_en}\n` + q.options.map((o, i) => `${i + 1}) ${o}`).join("\n");
    bubble(body);
  }
  function answerMock(ans) {
    const q = S.q[S.qi];
    if (/^(skip|छोड़|s)$/i.test(ans.trim())) { S.answers.push({ q, got: 0 }); }
    else {
      const k = parseInt(ans) - 1;
      if (!(k >= 0 && k < q.options.length)) return say(T("1–4 में विकल्प भेजिए या 'छोड़ें'।", "Send option 1–4 or 'skip'."));
      S.answers.push({ q, got: k === q.correct_idx ? q.marks : 0 });
    }
    S.qi++;
    if (S.qi < S.q.length) askCurrent(); else mockScorecard();
  }
  function mockScorecard() {
    const sec = (from, to) => S.answers.slice(from, to);
    const sum = (a) => a.reduce((x, r) => x + r.got, 0);
    const total = sum(S.answers); const maxTotal = S.answers.reduce((x,r)=>x+r.q.marks,0) || 1; const pct = Math.round(total / maxTotal * 100);
    const weak = {};
    S.answers.filter((r) => r.got === 0).forEach((r) => weak[r.q.skill_id] = (weak[r.q.skill_id] || 0) + r.q.marks);
    const weakTop = Object.entries(weak).sort((a, b) => b[1] - a[1]).slice(0, 3);
    const skillName = (id) => { for (const g of D.graphs[S.subject]) for (const ch of g.chapters) for (const sk of ch.skills) if (sk.id === id) return (L() === "hi" ? sk.name_hi : sk.name_en); return id; };
    let msg = T(`📊 परिणाम: ${total}/75 (${pct}%)\n`, `📊 Score: ${total}/75 (${pct}%)\n`);
    msg += T(`वस्तुनिष्ठ: ${sum(sec(0, 5))}/5 · 2-अंक: ${sum(sec(5, 17))}/24 · 3-अंक: ${sum(sec(17, 20))}/9 · 4-अंक: ${sum(sec(20, 23))}/12\n`, `Objective: ${sum(sec(0, 5))}/5 · 2-mark: ${sum(sec(5, 17))}/24 · 3-mark: ${sum(sec(17, 20))}/9 · 4-mark: ${sum(sec(20, 23))}/12\n`);
    if (weakTop.length) {
      msg += T("\nइन टॉपिक्स में सुधार चाहिए:\n", "\nFocus next on:\n");
      weakTop.forEach(([id], i) => msg += `${i + 1}. ${skillName(id)}\n`);
      msg += T("\n1 भेजिए — इन्हीं टॉपिक्स का अभ्यास शुरू करने के लिए।", "\nSend 1 — start practising exactly these topics.");
      S.pendingPractice = weakTop.map((e) => e[0]);
    } else msg += T("\nशानदार! पूरे पेपर में कोई गलती नहीं 🎉", "\nFlawless paper 🎉");
    S.mode = "menu";
    bubble(msg);
  }
  function answerNormal(ans) {
    const q = S.q[S.qi];
    const k = parseInt(ans) - 1;
    if (!(k >= 0 && k < q.options.length)) return say(T("कृपया विकल्प चुनिए — 1, 2, 3 या 4 भेजिए।", "Please choose — send 1, 2, 3 or 4."));
    const okk = k === q.correct_idx;
    S.answers.push({ q, ok: okk });
    if (okk) { S.streak++; say(T("✅ सही!", "✅ Correct!")); }
    else {
      S.streak = 0;
      say(T(`❌ गलत। सही उत्तर: ${q.correct_idx + 1}) ${q.options[q.correct_idx]}`, `❌ Not quite. Correct: ${q.correct_idx + 1}) ${q.options[q.correct_idx]}`));
      say("💡 " + (L() === "hi" ? (q.hint_hi || "") : (q.hint_en || "")));
      say("📖 " + (L() === "hi" ? (q.solution_hi || "") : (q.solution_en || "")));
    }
    S.qi++;
    if (S.qi < S.q.length) setTimeout(askCurrent, 700);
    else finishSet();
  }
  function finishSet() {
    const right = S.answers.filter((r) => r.ok).length;
    const wrongSkills = [...new Set(S.answers.filter((r) => !r.ok).map((r) => r.q.skill_id))];
    const skillName = (id) => { for (const g of D.graphs[S.subject]) for (const ch of g.chapters) for (const sk of ch.skills) if (sk.id === id) return (L() === "hi" ? sk.name_hi : sk.name_en); return id; };
    if (S.mode === "diag") {
      S.mode = "menu";
      say(T(`डायग्नोस्टिक पूरा: ${right}/${S.answers.length} सही।\n` + (wrongSkills.length ? `कमजोरी मिली: ${wrongSkills.slice(0, 2).map(skillName).join(", ")}…\nअब इन्हीं को मजबूत करेंगे।` : `बहुत बढ़िया — कोई कमजोरी नहीं मिली!`),
        `Diagnostic done: ${right}/${S.answers.length} correct.\n` + (wrongSkills.length ? `Weak spots: ${wrongSkills.slice(0, 2).map(skillName).join(", ")}…\nWe'll rebuild those first.` : "No weak spots found — excellent!")));
      renderStats();
      return say(menuLine());
    }
    if (S.mode === "practice") {
      S.mode = "menu";
      say(T(`अभ्यास पूरा: ${right}/${S.answers.length} ✅\n🔥 स्ट्रीक: ${S.streak}\nसाप्ताहिक रिपोर्ट अभिभावक को भेजी गई (डेमो)।`, `Practice done: ${right}/${S.answers.length} ✅\n🔥 Streak: ${S.streak}\nWeekly parent report sent (demo).`));
      renderStats();
      return say(menuLine());
    }
    say(menuLine());
  }
  const menuLine = () => T("मेनू: 1=डायग्नोस्टिक · 2=अभ्यास · 3=मॉक पेपर · 4=प्रश्न पूछें", "Menu: 1=diagnostic · 2=practice · 3=mock · 4=ask");
  function explainAsk(query) {
    bubble(query, true);
    // smart filter: only constrain subject if the query clearly matches it; SST/history/civics/geo queries search across subjects
    const q = query.toLowerCase();
    const sstHint = /(1857|revolt|constitution|democra|resource|geograph|history|civics|nation|freedom|संविधान|क्रांति|इतिहास|नागरिक|संसाधन|भूगोल|राजनीति)/i.test(query);
    let subj = S.subject;
    if (sstHint) subj = (/(algebra|equation|number|geometry|trigon|गणित|बीजगणित|त्रिकोण)/i.test(query)) ? subj : "social science";
    if (/^(explain|समझाइए|kya|क्या)/i.test(q) && !subj) subj = null;
    // try filtered first, fall back to unfiltered if weak
    let hits = bm25(query, S.grade || null, subj);
    if (!hits.length) return say(T("माफ़ कीजिए, इस विषय पर सामग्री नहीं मिली।", "Sorry, no grounded content found for that."));
    hits.forEach((h) => {
      say(h.t.slice(0, 380) + "…", "", "📚 स्रोत/Source: " + h.src);
    });
  }
  function renderStats() {
    $("#stats").innerHTML =
      `<span class="pill">📚 693 questions</span><span class="pill">🧠 180 skills</span>` +
      `<span class="pill">🔎 ${(window.PS_RAG || []).length.toLocaleString()} NCERT chunks</span>` +
      `<span class="pill">📄 MPBSE 2026 pattern</span><span class="pill">🔥 streak ${S.streak}</span>`;
  }

  // ---------- router ----------
  function handle(raw) {
    const input = raw.trim();
    bubble(raw, true);
    if (S.mode === "onb") return onb(input);
    if (S.mode === "diag" || S.mode === "practice") {
      // allow explain mid-flow
      if (/समझा|explain|\bwhy\b|\bkaise\b|कैसे|क्यों/i.test(input)) { S.modePrev = S.mode; return explainAsk(input); }
      return answerNormal(input);
    }
    if (S.mode === "mock") {
      if (/^menu|menu$/i.test(input)) { S.mode = "menu"; return say(menuLine()); }
      return answerMock(input);
    }
    // menu mode
    if (/^(1)$/.test(input)) return startDiag();
    if (/^(2)$/.test(input)) return startPractice(null);
    if (/^(3|mock|मॉक|पेपर)$/i.test(input)) return startMock();
    if (/समझा|explain|क्या है|what is|\bwhy\b|क्यों|कैसे|how/i.test(input)) return explainAsk(input);
    if (/^(4)$/.test(input)) return say(T("कोई भी प्रश्न टाइप कीजिए — उत्तर असली NCERT अध्याय से, स्रोत के साथ आएगा।", "Type any question — the answer comes from real NCERT chapters with citation."));
    if (/^help|मदद/i.test(input)) return say(T("1=डायग्नोस्टिक · 2=अभ्यास · 3=मॉक पेपर · या सीधे कोई प्रश्न लिखिए।", "1=diagnostic · 2=practice · 3=mock · or just type any question."));
    return explainAsk(input);
  }

  $("#f").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("#i").value.trim();
    if (!v) return;
    $("#i").value = "";
    handle(v);
  });

  start();
})();
