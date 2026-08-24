"""PRIMARY demo channel: WhatsApp-style phone chat at /demo + /demo/send + /demo/poll."""
import threading
from itertools import count

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import flows

router = APIRouter()

_LOCK = threading.Lock()
_STORE: dict[str, list[dict]] = {}
_SEQ = count(1)


def _push(phone: str, role: str, text: str) -> int:
    with _LOCK:
        mid = next(_SEQ)
        _STORE.setdefault(phone, []).append(
            {"id": mid, "role": role, "text": text})
    return mid


def reset_store() -> None:
    """Test isolation helper."""
    global _SEQ
    with _LOCK:
        _STORE.clear()
        _SEQ = count(1)


class SendBody(BaseModel):
    phone: str
    text: str


@router.get("/demo", response_class=HTMLResponse)
def demo_page():
    return HTMLResponse(_PAGE)


@router.post("/demo/send")
def demo_send(body: SendBody):
    phone = body.phone.strip()[:24]
    if not phone or not body.text.strip():
        return {"ok": False, "error": "phone and text required"}
    _push(phone, "me", body.text)
    replies = flows.handle_message(phone, body.text)
    for r in replies:
        _push(phone, "bot", r)
    return {"ok": True, "replies": replies}


@router.get("/demo/poll")
def demo_poll(phone: str, after: int = 0):
    with _LOCK:
        msgs = list(_STORE.get(phone, []))
    out = [m for m in msgs if m["id"] > after]
    last = msgs[-1]["id"] if msgs else after
    return {"messages": out, "last": last}


_PAGE = """<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PadhaiSetu Demo</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; font-family:'Segoe UI',system-ui,sans-serif; }
  body { background:#0b141a; display:flex; align-items:center; justify-content:center;
         min-height:100vh; padding:16px; }
  .wrap { display:flex; gap:28px; align-items:flex-start; flex-wrap:wrap; justify-content:center; }
  .side { color:#9db4bd; max-width:340px; padding-top:40px; }
  .side h1 { color:#25D366; font-size:26px; margin-bottom:10px; }
  .side p { line-height:1.55; font-size:14px; margin-bottom:8px; }
  .side b { color:#e9edef; }
  .phone { width:390px; height:760px; background:#111b21; border-radius:34px;
           border:10px solid #2a3942; box-shadow:0 30px 80px rgba(0,0,0,.6);
           overflow:hidden; display:flex; flex-direction:column; position:relative; }
  .header { background:#075E54; color:#fff; padding:12px 16px; display:flex;
            align-items:center; gap:12px; flex:0 0 auto; }
  .avatar { width:38px; height:38px; border-radius:50%; background:#128C7E;
            display:flex; align-items:center; justify-content:center; font-weight:700;
            font-size:18px; color:#fff; }
  .header .t { font-size:17px; font-weight:600; }
  .header .s { font-size:12px; opacity:.85; }
  .chat { flex:1; overflow-y:auto; background:#0b141a;
          background-image:radial-gradient(rgba(255,255,255,.03) 1px, transparent 1px);
          background-size:22px 22px; padding:14px 12px; display:flex;
          flex-direction:column; gap:8px; }
  .bubble { max-width:78%; padding:8px 11px; border-radius:9px; font-size:14px;
            line-height:1.45; white-space:pre-wrap; word-wrap:break-word;
            box-shadow:0 1px 1px rgba(0,0,0,.35); }
  .bot { align-self:flex-start; background:#202c33; color:#e9edef;
         border-top-left-radius:2px; }
  .me { align-self:flex-end; background:#005c4b; color:#e9edef;
        border-top-right-radius:2px; }
  .inputbar { flex:0 0 auto; background:#111b21; padding:9px 10px; display:flex; gap:9px; }
  .msg { flex:1; background:#2a3942; border:none; outline:none; color:#e9edef;
         border-radius:20px; padding:11px 15px; font-size:15px; }
  .sendbtn { width:44px; height:44px; border-radius:50%; border:none; cursor:pointer;
             background:#25D366; display:flex; align-items:center; justify-content:center; }
  .login { position:absolute; inset:0; background:#111b21; z-index:5; display:flex;
           flex-direction:column; align-items:center; justify-content:center; gap:14px; }
  .login h2 { color:#25D366; }
  .login input { background:#2a3942; border:none; outline:none; color:#e9edef;
                 text-align:center; border-radius:20px; padding:11px 16px;
                 width:240px; font-size:15px; }
  .login button { background:#25D366; color:#06231a; border:none; border-radius:20px;
                  padding:11px 30px; font-size:15px; font-weight:700; cursor:pointer; }
</style>
</head>
<body>
<div class="wrap">
 <div class="phone" id="phone">
   <div class="header">
     <div class="avatar">प</div>
     <div><div class="t">PadhaiSetu</div><div class="s">MP Board abhyas saathi · online</div></div>
   </div>
   <div class="chat" id="chat"></div>
   <div class="inputbar">
     <input class="msg" id="msg" placeholder="Type a message" autocomplete="off">
     <button class="sendbtn" onclick="sendMsg()" aria-label="Send">
       <svg width="22" height="22" viewBox="0 0 24 24" fill="#06231a">
         <path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
     </button>
   </div>
   <div class="login" id="login">
     <h2>PadhaiSetu</h2>
     <p style="color:#8696a0;font-size:13px">Demo phone number likhiye</p>
     <input id="phoneIn" placeholder="+91 90000 00001" value="+91 90000 00001">
     <button onclick="startChat()">Chat shuru karein</button>
   </div>
 </div>
 <div class="side">
   <h1>PadhaiSetu</h1>
   <p><b>Adaptive vernacular tutor</b> for MP Board class 8-10 Maths &amp; Science.</p>
   <p>Diagnostic quiz &rarr; daily 5-question sets targeting weakest sub-skills &rarr;
      prerequisite remediation when you slip &rarr; weekly parent report.</p>
   <p>No LLM in the loop - the mastery engine is deterministic and fully tested.</p>
 </div>
</div>
<script>
let PHONE = localStorage.getItem("ps_phone") || "";
let AFTER = 0;

async function poll() {
  try {
    const r = await fetch("/demo/poll?phone=" + encodeURIComponent(PHONE) + "&after=" + AFTER);
    const d = await r.json();
    for (const m of d.messages) { addBubble(m.role, m.text); AFTER = m.id; }
  } catch (e) {}
}

function addBubble(role, text) {
  const c = document.getElementById("chat");
  const b = document.createElement("div");
  b.className = "bubble " + role;
  b.textContent = text;
  c.appendChild(b);
  c.scrollTop = c.scrollHeight;
}

function startChat() {
  PHONE = document.getElementById("phoneIn").value.trim();
  if (!PHONE) return;
  localStorage.setItem("ps_phone", PHONE);
  document.getElementById("login").style.display = "none";
  sendText("namaste");
}

async function sendText(t) {
  if (!t.trim()) return;
  try {
    const r = await fetch("/demo/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: PHONE, text: t })
    });
    const d = await r.json();
    if (d.replies) { for (const m of d.replies) { addBubble("bot", m); } }
  } catch (e) { addBubble("bot", "Network error, dobara koshish kijiye."); }
  poll();
}

function sendMsg() {
  const inp = document.getElementById("msg");
  const t = inp.value;
  inp.value = "";
  if (t.trim()) addBubble("me", t);
  sendText(t);
}

document.getElementById("msg").addEventListener("keydown", function(e) {
  if (e.key === "Enter") sendMsg();
});

setInterval(poll, 1500);
window.addEventListener("load", () => { if (PHONE) { startChatResume(); } });

function startChatResume() {
  document.getElementById("login").style.display = "none";
}
</script>
</body>
</html>"""
