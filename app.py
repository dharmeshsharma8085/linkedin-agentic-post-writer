import json
import os

import requests
from flask import Flask, Response, request, stream_with_context

# ============================================================
# CONFIG
# ============================================================

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

app = Flask(__name__)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ============================================================
# API PROXY (browser -> Flask -> FastAPI)
# Keeps the browser off the backend URL, so no CORS headaches.
# ============================================================

@app.post("/api/stream")
def proxy_stream():
    payload = request.get_json(silent=True) or {}

    def generate():
        try:
            r = requests.post(
                f"{BACKEND_URL}/generate/stream",
                json=payload,
                stream=True,
                timeout=(5, 300),
            )
            if r.status_code != 200:
                yield sse("error", {"detail": f"Backend returned {r.status_code}: {r.text[:300]}"})
                return
            for chunk in r.iter_content(chunk_size=None):
                if chunk:
                    yield chunk
        except requests.exceptions.ConnectionError:
            yield sse("error", {"detail": "Can't reach the backend. Is `uvicorn backend:api` running?"})
        except Exception as e:
            yield sse("error", {"detail": str(e)})

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# UI
# ============================================================

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PostForge · LinkedIn posts that don't sound like AI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0b0b12;
    --card: rgba(255,255,255,0.05);
    --border: rgba(255,255,255,0.10);
    --text: #f3f3f8;
    --muted: #9a9ab0;
    --a: #7c5cff;
    --b: #00d4ff;
    --c: #ff5ca8;
    --ok: #3ddc97;
    --bad: #ff6b6b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    overflow-x: hidden;
  }
  /* floating gradient blobs */
  .blob { position: fixed; border-radius: 50%; filter: blur(90px); opacity: .35; z-index: 0; animation: float 14s ease-in-out infinite; }
  .b1 { width: 420px; height: 420px; background: var(--a); top: -120px; left: -100px; }
  .b2 { width: 380px; height: 380px; background: var(--b); bottom: -120px; right: -80px; animation-delay: -5s; }
  .b3 { width: 300px; height: 300px; background: var(--c); top: 40%; left: 60%; opacity: .18; animation-delay: -9s; }
  @keyframes float { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(40px,-30px) scale(1.1); } }

  .wrap { position: relative; z-index: 1; max-width: 760px; margin: 0 auto; padding: 56px 20px 80px; }

  header { text-align: center; margin-bottom: 36px; }
  .logo { font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 44px; letter-spacing: -1.5px;
          background: linear-gradient(90deg, var(--a), var(--b), var(--c)); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .tag { color: var(--muted); margin-top: 8px; font-size: 16px; }

  .panel { background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 22px;
           backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); }

  label { font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 14px; color: var(--muted); display: block; margin-bottom: 10px; }
  textarea {
    width: 100%; min-height: 110px; resize: vertical; padding: 14px 16px; font: inherit; font-size: 16px;
    color: var(--text); background: rgba(0,0,0,.35); border: 1px solid var(--border); border-radius: 14px; outline: none;
    transition: border-color .2s, box-shadow .2s;
  }
  textarea:focus { border-color: var(--a); box-shadow: 0 0 0 4px rgba(124,92,255,.18); }

  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 18px; }
  .chip { font-size: 13px; padding: 7px 12px; border-radius: 999px; border: 1px solid var(--border); background: rgba(255,255,255,.04);
          color: var(--muted); cursor: pointer; transition: all .2s; }
  .chip:hover { color: var(--text); border-color: var(--b); transform: translateY(-2px); }

  .go {
    width: 100%; padding: 15px; border: 0; border-radius: 14px; cursor: pointer; font-family: 'Space Grotesk', sans-serif;
    font-size: 17px; font-weight: 700; color: #fff; background: linear-gradient(90deg, var(--a), var(--c));
    transition: transform .15s, box-shadow .2s, opacity .2s; box-shadow: 0 8px 30px rgba(124,92,255,.35);
  }
  .go:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 12px 38px rgba(255,92,168,.4); }
  .go:disabled { opacity: .6; cursor: wait; }

  /* progress */
  #progress { display: none; margin-top: 26px; }
  .steps { display: flex; gap: 10px; }
  .step { flex: 1; padding: 12px; border-radius: 14px; border: 1px solid var(--border); background: rgba(255,255,255,.03);
          text-align: center; font-size: 13px; color: var(--muted); transition: all .3s; position: relative; overflow: hidden; }
  .step .ico { font-size: 22px; display: block; margin-bottom: 4px; }
  .step.active { color: var(--text); border-color: var(--b); background: rgba(0,212,255,.08); }
  .step.active::after { content: ''; position: absolute; left: 0; bottom: 0; height: 3px; width: 40%;
          background: linear-gradient(90deg, var(--b), var(--a)); animation: slide 1.1s ease-in-out infinite; }
  .step.done { color: var(--ok); border-color: rgba(61,220,151,.5); background: rgba(61,220,151,.07); }
  .step.fail { color: var(--bad); border-color: rgba(255,107,107,.5); background: rgba(255,107,107,.07); }
  @keyframes slide { 0% { left: -40%; } 100% { left: 100%; } }
  #status { text-align: center; color: var(--muted); font-size: 14px; margin-top: 14px; min-height: 20px; }

  /* result */
  #result { display: none; margin-top: 26px; animation: pop .45s ease; }
  @keyframes pop { from { opacity: 0; transform: translateY(14px) scale(.98); } to { opacity: 1; transform: none; } }
  .li { background: #fff; color: #1d2226; border-radius: 16px; padding: 18px 20px; box-shadow: 0 20px 60px rgba(0,0,0,.45); }
  .li-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
  .avatar { width: 48px; height: 48px; border-radius: 50%; background: linear-gradient(135deg, var(--a), var(--b)); display: grid; place-items: center; color: #fff; font-weight: 700; }
  .who b { display: block; font-size: 15px; }
  .who span { font-size: 12px; color: #666; }
  #post { white-space: pre-wrap; font-size: 15px; line-height: 1.55; word-wrap: break-word; }
  .li-foot { display: flex; gap: 22px; margin-top: 16px; padding-top: 12px; border-top: 1px solid #e6e6e6; font-size: 13px; color: #666; }

  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 16px; }
  .badge { padding: 6px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; }
  .badge.ok { background: rgba(61,220,151,.15); color: var(--ok); }
  .badge.no { background: rgba(255,107,107,.15); color: var(--bad); }
  .badge.info { background: rgba(255,255,255,.08); color: var(--muted); }
  .spacer { flex: 1; }
  .btn { padding: 9px 16px; border-radius: 12px; border: 1px solid var(--border); background: rgba(255,255,255,.06); color: var(--text);
         font: inherit; font-size: 14px; cursor: pointer; transition: all .2s; }
  .btn:hover { border-color: var(--b); transform: translateY(-1px); }

  details { margin-top: 14px; background: rgba(0,0,0,.3); border: 1px solid var(--border); border-radius: 14px; padding: 12px 16px; }
  summary { cursor: pointer; color: var(--muted); font-size: 14px; }
  #feedback { margin-top: 10px; font-size: 14px; line-height: 1.55; color: #cfcfe0; white-space: pre-wrap; }

  .error { display: none; margin-top: 20px; padding: 14px 16px; border-radius: 14px; background: rgba(255,107,107,.1);
           border: 1px solid rgba(255,107,107,.4); color: #ffb3b3; font-size: 14px; }

  footer { text-align: center; color: var(--muted); font-size: 12px; margin-top: 40px; }
  @media (max-width: 520px) { .logo { font-size: 34px; } .steps { flex-direction: column; } }
</style>
</head>
<body>
<div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>

<div class="wrap">
  <header>
    <div class="logo">PostForge</div>
    <p class="tag">Drop a topic. A writer drafts it, a reviewer roasts it, you get the good version.</p>
  </header>

  <div class="panel">
    <label for="topic">What did you build, learn, or break this week?</label>
    <textarea id="topic" placeholder="e.g. I built a writer + reviewer loop with LangGraph that rewrites posts until they stop sounding like AI"></textarea>

    <div class="chips">
      <span class="chip">🧠 My RAG project journey</span>
      <span class="chip">🤖 Building an AI agent with LangGraph</span>
      <span class="chip">🛠️ Lessons from tool calling</span>
      <span class="chip">🎓 Finished my AI internship</span>
    </div>

    <button class="go" id="go">✨ Forge my post</button>

    <div id="progress">
      <div class="steps">
        <div class="step" id="s1"><span class="ico">✍️</span>Writer</div>
        <div class="step" id="s2"><span class="ico">🔍</span>Reviewer</div>
        <div class="step" id="s3"><span class="ico">🏁</span>Verdict</div>
      </div>
      <div id="status"></div>
    </div>

    <div class="error" id="error"></div>
  </div>

  <div id="result">
    <div class="li">
      <div class="li-head">
        <div class="avatar">You</div>
        <div class="who"><b>Your Name</b><span>AI Engineer · just now 🌐</span></div>
      </div>
      <div id="post"></div>
      <div class="li-foot"><span>👍 Like</span><span>💬 Comment</span><span>🔁 Repost</span><span>✈️ Send</span></div>
    </div>

    <div class="meta">
      <span class="badge" id="verdict"></span>
      <span class="badge info" id="attempts"></span>
      <span class="spacer"></span>
      <button class="btn" id="copy">📋 Copy</button>
      <button class="btn" id="again">🔄 Try again</button>
    </div>

    <details>
      <summary>Reviewer feedback</summary>
      <div id="feedback"></div>
    </details>
  </div>

  <footer>Powered by LangGraph · FastAPI · Flask</footer>
</div>

<script>
const $ = (id) => document.getElementById(id);
const goBtn = $('go'), topicEl = $('topic');

document.querySelectorAll('.chip').forEach(c => {
  c.onclick = () => { topicEl.value = c.textContent.replace(/^\S+\s/, ''); topicEl.focus(); };
});

function setStep(active) {
  const order = ['s1', 's2', 's3'];
  order.forEach((id, i) => {
    const el = $(id);
    el.className = 'step';
    if (i < active) el.classList.add('done');
    else if (i === active) el.classList.add('active');
  });
}

function showError(msg) {
  const e = $('error');
  e.textContent = '⚠️ ' + msg;
  e.style.display = 'block';
  $('progress').style.display = 'none';
}

function handleEvent(event, data) {
  if (event === 'writer') {
    setStep(0);
    $('status').textContent = data.attempt > 1
      ? `Rewriting with feedback (attempt ${data.attempt})…`
      : 'Writer is drafting your post…';
  } else if (event === 'tools') {
    $('status').textContent = '🔎 Searching the web for fresh info…';
  } else if (event === 'draft') {
    setStep(1);
    $('status').textContent = 'Reviewer is reading it critically…';
    $('post').textContent = data.post;
    $('result').style.display = 'block';
  } else if (event === 'review') {
    $('feedback').textContent = data.feedback || '';
    if (data.is_approved) {
      setStep(3);
      $('s3').className = 'step done';
      $('status').textContent = 'Approved 🎉';
    } else {
      $('status').textContent = 'Rejected. Sending it back to the writer…';
      $('s3').className = 'step fail';
    }
  } else if (event === 'done') {
    $('post').textContent = data.post;
    const v = $('verdict');
    v.textContent = data.is_approved ? '✅ Approved' : '⚠️ Best attempt (not approved)';
    v.className = 'badge ' + (data.is_approved ? 'ok' : 'no');
    $('attempts').textContent = `${data.attempts} attempt${data.attempts === 1 ? '' : 's'}`;
    $('feedback').textContent = data.review_feedback || '';
    $('result').style.display = 'block';
    $('progress').style.display = 'none';
  } else if (event === 'error') {
    showError(data.detail || 'Something went wrong.');
  }
}

async function generate() {
  const topic = topicEl.value.trim();
  if (topic.length < 3) { topicEl.focus(); return; }

  $('error').style.display = 'none';
  $('result').style.display = 'none';
  $('progress').style.display = 'block';
  $('post').textContent = '';
  setStep(0);
  $('status').textContent = 'Warming up the agents…';
  goBtn.disabled = true;
  goBtn.textContent = '⏳ Forging…';

  try {
    const res = await fetch('/api/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        let event = 'message', dataStr = '';
        raw.split('\n').forEach(line => {
          if (line.startsWith('event:')) event = line.slice(6).trim();
          else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
        });
        if (dataStr) {
          try { handleEvent(event, JSON.parse(dataStr)); } catch (e) { console.error(e); }
        }
      }
    }
  } catch (err) {
    showError(err.message);
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = '✨ Forge my post';
  }
}

goBtn.onclick = generate;
$('again').onclick = generate;
topicEl.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) generate(); });

$('copy').onclick = async () => {
  await navigator.clipboard.writeText($('post').textContent);
  const b = $('copy'); const old = b.textContent;
  b.textContent = '✅ Copied!';
  setTimeout(() => b.textContent = old, 1500);
};
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


# ============================================================
# RUN
# ============================================================
# pip install flask requests
# 1) uvicorn backend:api --port 8000
# 2) python app.py   ->  http://127.0.0.1:5000

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)