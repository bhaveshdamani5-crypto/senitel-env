"""
Sentinel-Log-Shield v2 FastAPI Server with Interactive Demo.

Provides:
  - Interactive Demo UI at / (judges see this first)
  - POST /reset, POST /step, GET /state (OpenEnv API)
  - GET /health
  - GET /docs, GET /redoc (API docs)
  - GET /demo/run?difficulty=easy (runs a full episode and returns trace)
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import re
from typing import Optional, List, Dict, Set
from env import SentinelEnvironment
from models import (
    AgentAction, ActionType, StepResult, ResetResult,
    EnvironmentState, Difficulty,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sentinel-Log-Shield",
    description="Interactive Security Investigation RL Environment for OpenEnv",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Global environment for API usage
env = SentinelEnvironment()
logger.info("Sentinel-Log-Shield v2 environment initialized")


# ───────────── Internal agent for demo runs ─────────────

def _extract_pii(logs: List[str]) -> List[Dict[str, str]]:
    """Extract PII from logs using regex (agent's own patterns)."""
    found = []
    seen: Set[str] = set()
    for log in logs:
        for m in re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', log):
            if m.group() not in seen: found.append({"original": m.group(), "type": "email"}); seen.add(m.group())
        for m in re.finditer(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', log):
            if m.group() not in seen and m.group() != "255.255.255.255": found.append({"original": m.group(), "type": "ip"}); seen.add(m.group())
        for m in re.finditer(r"User\s*['\"]([A-Za-z][A-Za-z0-9_-]*)['\"]", log, re.IGNORECASE):
            if m.group(1) not in seen: found.append({"original": m.group(1), "type": "username"}); seen.add(m.group(1))
        for m in re.finditer(r"user=([A-Za-z][A-Za-z0-9_-]+)", log, re.IGNORECASE):
            if m.group(1) not in seen: found.append({"original": m.group(1), "type": "username"}); seen.add(m.group(1))
        for pat in [r'\bsk_[a-zA-Z0-9_]{10,}\b', r'\bghp_[a-zA-Z0-9]{10,}\b', r'\bhf_[a-zA-Z0-9]{10,}\b',
                    r'\bAKIA[A-Z0-9]{12,}\b', r'\beyJ[a-zA-Z0-9_-]{20,}\b', r'api_key_[A-Za-z0-9]{10,}',
                    r'(?:key|token|secret|credential)\s*=\s*(\S{8,})']:
            for m in re.finditer(pat, log, re.IGNORECASE):
                v = m.group(1) if m.lastindex else m.group(0)
                if v not in seen and len(v) > 5: found.append({"original": v, "type": "token"}); seen.add(v)
    return found


def run_demo_episode(difficulty: str = "medium") -> Dict:
    """Run a complete episode internally and return full trace."""
    demo_env = SentinelEnvironment()
    reset = demo_env.reset(difficulty=difficulty)
    obs = reset.observation
    trace = {
        "difficulty": difficulty,
        "budget": obs.steps_remaining,
        "total_pii": obs.total_pii_to_find,
        "initial_logs": obs.visible_logs,
        "steps": [],
        "final_metrics": {},
    }

    # Phase 1: SCAN
    result = demo_env.step(AgentAction(action_type=ActionType.SCAN))
    obs = result.observation
    trace["steps"].append({
        "action": "SCAN",
        "target": None,
        "logs_visible": len(obs.visible_logs),
        "entities_found": list(obs.discovered_entities),
        "reward": round(result.reward.total_reward, 3),
        "feedback": result.reward.feedback,
        "steps_remaining": obs.steps_remaining,
    })

    # Phase 2: INVESTIGATE entities
    investigated = set()
    while obs.steps_remaining > 2 and obs.investigation_targets:
        targets = [t for t in obs.investigation_targets if t not in investigated]
        if not targets:
            break
        target = targets[0]
        investigated.add(target)
        result = demo_env.step(AgentAction(action_type=ActionType.INVESTIGATE, target_entity=target))
        obs = result.observation
        trace["steps"].append({
            "action": "INVESTIGATE",
            "target": target,
            "logs_visible": len(obs.visible_logs),
            "entities_found": list(obs.discovered_entities),
            "reward": round(result.reward.total_reward, 3),
            "feedback": result.reward.feedback,
            "steps_remaining": obs.steps_remaining,
        })
        if result.terminated or result.truncated:
            break

    # Phase 3: REDACT
    if obs.steps_remaining > 1 and not (result.terminated or result.truncated):
        pii_items = _extract_pii(obs.visible_logs)
        seen = {p["original"] for p in pii_items}
        for e in obs.discovered_entities:
            if e not in seen:
                etype = "email" if "@" in e else ("ip" if re.match(r"^\d+\.\d+\.\d+\.\d+$", e) else ("token" if len(e) > 15 else "username"))
                pii_items.append({"original": e, "type": etype})
                seen.add(e)
        result = demo_env.step(AgentAction(action_type=ActionType.REDACT, redactions=pii_items))
        obs = result.observation
        trace["steps"].append({
            "action": "REDACT",
            "target": f"{len(pii_items)} items",
            "logs_visible": len(obs.visible_logs),
            "entities_found": list(obs.discovered_entities),
            "reward": round(result.reward.total_reward, 3),
            "feedback": result.reward.feedback,
            "coverage": f"{obs.pii_found_count}/{obs.total_pii_to_find}",
            "steps_remaining": obs.steps_remaining,
        })

    # Phase 4: SUBMIT
    if not (result.terminated or result.truncated):
        result = demo_env.step(AgentAction(action_type=ActionType.SUBMIT))
        obs = result.observation
        trace["steps"].append({
            "action": "SUBMIT",
            "target": None,
            "reward": round(result.reward.total_reward, 3),
            "feedback": result.reward.feedback,
            "steps_remaining": obs.steps_remaining,
        })

    trace["final_metrics"] = {k: round(v, 4) if isinstance(v, float) else v for k, v in result.reward.metrics.items()}
    trace["total_reward"] = round(sum(s["reward"] for s in trace["steps"]), 3)
    trace["final_score"] = trace["final_metrics"].get("total_score", 0)
    trace["f1_score"] = trace["final_metrics"].get("f1_score", 0)
    trace["discovery_rate"] = trace["final_metrics"].get("discovery_rate", 0)
    trace["grade"] = trace["final_metrics"].get("grade", "?")
    return trace


# ───────────── Demo endpoint ─────────────

@app.get("/demo/run")
async def demo_run(difficulty: str = Query("medium", description="easy, medium, hard")):
    """Run a complete demo episode and return the full trace."""
    try:
        return run_demo_episode(difficulty)
    except Exception as e:
        logger.error(f"Demo error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ───────────── Landing Page (Interactive Demo UI) ─────────────

@app.get("/")
async def root():
    """Premium interactive demo page — what judges see first."""
    return HTMLResponse(DEMO_HTML)

DEMO_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sentinel-Log-Shield — Interactive Security Investigation</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#07080d;--bg2:#0f1219;--surface:#151a27;--surface2:#1a2030;
  --border:rgba(255,255,255,.08);--border2:rgba(255,255,255,.14);
  --text:#eaf0ff;--muted:#8a95b0;--dim:#5a6480;
  --accent:#6e8eff;--accent2:#5bf0d8;--accent3:#a78bfa;
  --green:#34d399;--red:#f87171;--yellow:#fbbf24;--orange:#fb923c;
  --glow:0 0 40px rgba(110,142,255,.15);
  --glass:rgba(255,255,255,.04);
}
html{scroll-behavior:smooth}
body{
  font-family:'Inter',system-ui,-apple-system,sans-serif;
  background:var(--bg);color:var(--text);
  min-height:100vh;overflow-x:hidden;
}
/* Ambient background */
body::before,body::after{
  content:'';position:fixed;border-radius:50%;filter:blur(80px);opacity:.35;
  pointer-events:none;z-index:0;
}
body::before{width:600px;height:600px;top:-200px;right:-100px;background:var(--accent)}
body::after{width:500px;height:500px;bottom:-200px;left:-100px;background:var(--accent2)}
.wrap{max-width:1120px;margin:0 auto;padding:2rem 1.25rem 4rem;position:relative;z-index:1}

/* Header */
.hero{text-align:center;padding:3rem 0 2.5rem;animation:fadeUp .7s ease}
.hero .pill{
  display:inline-flex;align-items:center;gap:.5rem;
  padding:.4rem .9rem;border-radius:999px;font-size:.75rem;font-weight:600;
  border:1px solid var(--border2);background:var(--glass);color:var(--accent2);
  letter-spacing:.06em;text-transform:uppercase;margin-bottom:1rem;
}
.hero h1{
  font-size:clamp(2rem,5vw,3.2rem);font-weight:800;
  letter-spacing:-.03em;line-height:1.1;
  background:linear-gradient(135deg,var(--text) 0%,var(--accent) 50%,var(--accent2) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}
.hero p{color:var(--muted);font-size:1.05rem;max-width:700px;margin:.8rem auto 0;line-height:1.6}
.hero-actions{display:flex;gap:.6rem;justify-content:center;margin-top:1.5rem;flex-wrap:wrap}
.btn{
  padding:.65rem 1.2rem;border-radius:10px;font-size:.88rem;font-weight:600;
  text-decoration:none;transition:all .2s ease;cursor:pointer;border:none;
  font-family:inherit;
}
.btn-primary{
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#0a0f1a;box-shadow:0 4px 20px rgba(91,240,216,.2);
}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 30px rgba(91,240,216,.3)}
.btn-ghost{
  background:var(--glass);color:var(--text);border:1px solid var(--border2);
}
.btn-ghost:hover{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.22)}

/* KPI Row */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.75rem;margin:1.5rem 0}
.kpi{
  background:var(--surface);border:1px solid var(--border);border-radius:14px;
  padding:.9rem 1rem;text-align:center;
  transition:transform .2s ease,border-color .2s ease;
}
.kpi:hover{transform:translateY(-3px);border-color:var(--accent)}
.kpi .val{font-size:1.5rem;font-weight:700;color:var(--accent2)}
.kpi .label{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:.25rem}

/* Difficulty tabs */
.tabs{display:flex;gap:.5rem;justify-content:center;margin:2rem 0 1rem;flex-wrap:wrap}
.tab{
  padding:.55rem 1.3rem;border-radius:10px;font-size:.85rem;font-weight:600;
  cursor:pointer;border:1px solid var(--border);background:var(--surface);
  color:var(--muted);transition:all .2s ease;font-family:inherit;
}
.tab:hover{border-color:var(--accent);color:var(--text)}
.tab.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#0a0f1a;border-color:transparent}
.tab .diff-badge{font-size:.65rem;opacity:.8;margin-left:.3rem}

/* Results panels */
.results-container{margin-top:1rem}
.panel{
  background:var(--surface);border:1px solid var(--border);border-radius:18px;
  padding:1.5rem;margin-bottom:1rem;
  animation:fadeUp .5s ease;display:none;
}
.panel.active{display:block}
.panel-header{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:1rem;flex-wrap:wrap;gap:.5rem;
}
.panel-title{font-size:1.1rem;font-weight:700}
.grade-badge{
  padding:.35rem .8rem;border-radius:8px;font-size:.85rem;font-weight:700;
  letter-spacing:.04em;
}
.grade-S{background:rgba(52,211,153,.15);color:var(--green);border:1px solid rgba(52,211,153,.3)}
.grade-A{background:rgba(110,142,255,.15);color:var(--accent);border:1px solid rgba(110,142,255,.3)}
.grade-B{background:rgba(167,139,250,.15);color:var(--accent3);border:1px solid rgba(167,139,250,.3)}
.grade-C{background:rgba(251,191,36,.15);color:var(--yellow);border:1px solid rgba(251,191,36,.3)}
.grade-D{background:rgba(251,146,60,.15);color:var(--orange);border:1px solid rgba(251,146,60,.3)}
.grade-F{background:rgba(248,113,113,.15);color:var(--red);border:1px solid rgba(248,113,113,.3)}

/* Metrics bar */
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:.6rem;margin-bottom:1.2rem}
.metric{background:var(--bg2);border-radius:10px;padding:.7rem .8rem}
.metric .m-val{font-size:1.15rem;font-weight:700;color:var(--text)}
.metric .m-label{font-size:.68rem;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin-top:.15rem}

/* Progress bar */
.progress-track{
  height:6px;background:var(--bg);border-radius:99px;overflow:hidden;margin-top:.3rem;
}
.progress-fill{
  height:100%;border-radius:99px;transition:width .8s cubic-bezier(.34,1.56,.64,1);
}
.fill-green{background:linear-gradient(90deg,var(--green),var(--accent2))}
.fill-blue{background:linear-gradient(90deg,var(--accent),var(--accent3))}

/* Steps timeline */
.timeline{margin-top:1rem}
.timeline-title{font-size:.8rem;font-weight:600;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;margin-bottom:.6rem}
.step{
  display:flex;gap:.75rem;padding:.65rem .85rem;
  background:var(--bg2);border-radius:12px;margin-bottom:.4rem;
  border-left:3px solid var(--border);
  transition:border-color .3s ease;animation:slideIn .4s ease both;
}
.step:nth-child(1){animation-delay:.1s}.step:nth-child(2){animation-delay:.2s}
.step:nth-child(3){animation-delay:.3s}.step:nth-child(4){animation-delay:.4s}
.step:nth-child(5){animation-delay:.5s}.step:nth-child(6){animation-delay:.6s}
.step.scan{border-left-color:var(--accent)}
.step.investigate{border-left-color:var(--accent2)}
.step.redact{border-left-color:var(--accent3)}
.step.submit{border-left-color:var(--green)}
.step-badge{
  flex-shrink:0;padding:.2rem .55rem;border-radius:6px;font-size:.7rem;
  font-weight:700;letter-spacing:.04em;font-family:'JetBrains Mono',monospace;
  min-width:90px;text-align:center;
}
.badge-scan{background:rgba(110,142,255,.12);color:var(--accent)}
.badge-investigate{background:rgba(91,240,216,.12);color:var(--accent2)}
.badge-redact{background:rgba(167,139,250,.12);color:var(--accent3)}
.badge-submit{background:rgba(52,211,153,.12);color:var(--green)}
.step-body{flex:1;min-width:0}
.step-target{font-size:.82rem;font-weight:600;color:var(--text)}
.step-detail{font-size:.75rem;color:var(--muted);margin-top:.15rem;line-height:1.4}
.step-reward{
  flex-shrink:0;font-family:'JetBrains Mono',monospace;font-size:.82rem;
  font-weight:600;padding:.2rem .5rem;border-radius:6px;
}
.reward-positive{color:var(--green);background:rgba(52,211,153,.08)}
.reward-negative{color:var(--red);background:rgba(248,113,113,.08)}
.reward-zero{color:var(--dim);background:var(--glass)}

/* Loading */
.loading{text-align:center;padding:3rem;color:var(--muted)}
.spinner{
  display:inline-block;width:28px;height:28px;border:3px solid var(--border);
  border-top-color:var(--accent2);border-radius:50%;
  animation:spin .8s linear infinite;margin-bottom:.5rem;
}

/* Nav links */
.nav-links{
  display:flex;gap:.5rem;justify-content:center;margin-top:2rem;flex-wrap:wrap;
}
.nav-links a{
  color:var(--muted);font-size:.8rem;text-decoration:none;
  padding:.4rem .8rem;border:1px solid var(--border);border-radius:8px;
  transition:all .2s ease;
}
.nav-links a:hover{color:var(--text);border-color:var(--accent);background:var(--glass)}

/* Animations */
@keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes slideIn{from{opacity:0;transform:translateX(-12px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

@media(max-width:600px){
  .wrap{padding:1rem .75rem 3rem}
  .hero h1{font-size:1.8rem}
  .step{flex-wrap:wrap}
}
</style>
</head>
<body>

<div class="wrap">
  <!-- Hero -->
  <header class="hero">
    <div class="pill">OpenEnv RL Environment &bull; v2.0</div>
    <h1>Sentinel-Log-Shield</h1>
    <p>Interactive security investigation where AI agents explore procedurally-generated
       breach scenarios, discover hidden secrets through entity graphs, and redact PII
       under a step budget.</p>
    <div class="hero-actions">
      <button class="btn btn-primary" onclick="runAll()">Run All 3 Levels</button>
      <a class="btn btn-ghost" href="/docs">API Docs</a>
      <a class="btn btn-ghost" href="/redoc">Technical Ref</a>
    </div>
  </header>

  <!-- KPI summary (updates after runs) -->
  <div class="kpi-row" id="kpi-row">
    <div class="kpi"><div class="val" id="kpi-f1">--</div><div class="label">Avg F1 Score</div></div>
    <div class="kpi"><div class="val" id="kpi-disc">--</div><div class="label">Avg Discovery</div></div>
    <div class="kpi"><div class="val" id="kpi-grade">--</div><div class="label">Best Grade</div></div>
    <div class="kpi"><div class="val" id="kpi-pii">--</div><div class="label">Total PII Found</div></div>
    <div class="kpi"><div class="val" id="kpi-steps">--</div><div class="label">Steps Used</div></div>
  </div>

  <!-- Difficulty tabs -->
  <div class="tabs">
    <button class="tab active" data-diff="easy" onclick="showPanel('easy',this)">
      Easy <span class="diff-badge">(12 steps)</span>
    </button>
    <button class="tab" data-diff="medium" onclick="showPanel('medium',this)">
      Medium <span class="diff-badge">(10 steps)</span>
    </button>
    <button class="tab" data-diff="hard" onclick="showPanel('hard',this)">
      Hard <span class="diff-badge">(8 steps)</span>
    </button>
  </div>

  <!-- Results -->
  <div class="results-container">
    <div class="panel active" id="panel-easy"><div class="loading"><div class="spinner"></div><br>Click "Run All 3 Levels" to begin...</div></div>
    <div class="panel" id="panel-medium"><div class="loading"><div class="spinner"></div><br>Waiting...</div></div>
    <div class="panel" id="panel-hard"><div class="loading"><div class="spinner"></div><br>Waiting...</div></div>
  </div>

  <!-- Nav -->
  <div class="nav-links">
    <a href="/docs">Swagger UI</a>
    <a href="/redoc">ReDoc</a>
    <a href="/health">Health Check</a>
    <a href="/state">Environment State</a>
    <a href="https://github.com/bhaveshdamani5-crypto/senitel-env" target="_blank">GitHub</a>
  </div>
</div>

<script>
const results = {};

async function fetchEpisode(difficulty) {
  const r = await fetch(`/demo/run?difficulty=${difficulty}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function showPanel(diff, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(`panel-${diff}`).classList.add('active');
}

function renderPanel(diff, data) {
  const panel = document.getElementById(`panel-${diff}`);
  const diffLabel = {easy:'Easy',medium:'Medium',hard:'Hard'}[diff];
  const grade = data.grade || '?';
  const f1 = (data.f1_score*100).toFixed(1);
  const disc = (data.discovery_rate*100).toFixed(1);
  const fm = data.final_metrics || {};
  const tp = fm.true_positives || 0;
  const total = fm.total_pii || 0;
  const missed = fm.secrets_missed || 0;
  const stepsUsed = fm.steps_used || data.steps?.length || 0;
  const budget = fm.steps_budget || data.budget || 0;

  let html = `
    <div class="panel-header">
      <div class="panel-title">${diffLabel} Investigation</div>
      <div class="grade-badge grade-${grade}">Grade: ${grade}</div>
    </div>
    <div class="metrics-grid">
      <div class="metric">
        <div class="m-val">${f1}%</div>
        <div class="m-label">F1 Score</div>
        <div class="progress-track"><div class="progress-fill fill-blue" style="width:${f1}%"></div></div>
      </div>
      <div class="metric">
        <div class="m-val">${disc}%</div>
        <div class="m-label">Discovery Rate</div>
        <div class="progress-track"><div class="progress-fill fill-green" style="width:${disc}%"></div></div>
      </div>
      <div class="metric">
        <div class="m-val">${tp}/${total}</div>
        <div class="m-label">PII Redacted</div>
        <div class="progress-track"><div class="progress-fill fill-green" style="width:${total?tp/total*100:0}%"></div></div>
      </div>
      <div class="metric">
        <div class="m-val">${stepsUsed}/${budget}</div>
        <div class="m-label">Steps Used</div>
        <div class="progress-track"><div class="progress-fill fill-blue" style="width:${budget?stepsUsed/budget*100:0}%"></div></div>
      </div>
      <div class="metric">
        <div class="m-val">${missed}</div>
        <div class="m-label">Secrets Missed</div>
      </div>
      <div class="metric">
        <div class="m-val">${data.total_reward?.toFixed(3)||'0'}</div>
        <div class="m-label">Total Reward</div>
      </div>
    </div>
    <div class="timeline">
      <div class="timeline-title">Investigation Timeline</div>
  `;

  (data.steps || []).forEach((s, i) => {
    const act = s.action.toLowerCase();
    const targetText = s.target ? `: ${s.target}` : '';
    const rewardClass = s.reward > 0 ? 'reward-positive' : (s.reward < 0 ? 'reward-negative' : 'reward-zero');
    const detail = s.feedback || '';
    const coverage = s.coverage ? ` | Coverage: ${s.coverage}` : '';
    const logsInfo = s.logs_visible !== undefined ? `${s.logs_visible} logs visible` : '';
    const entCount = s.entities_found ? s.entities_found.length : 0;

    html += `
      <div class="step ${act}">
        <div class="step-badge badge-${act}">${s.action}</div>
        <div class="step-body">
          <div class="step-target">Step ${i+1}${targetText}</div>
          <div class="step-detail">${logsInfo}${logsInfo && entCount ? ' | ':''} ${entCount ? entCount + ' entities' : ''} ${coverage} ${detail ? '| ' + detail : ''}</div>
        </div>
        <div class="step-reward ${rewardClass}">${s.reward >= 0 ? '+' : ''}${s.reward.toFixed(3)}</div>
      </div>
    `;
  });

  html += '</div>';
  panel.innerHTML = html;
}

function updateKPIs() {
  const diffs = ['easy','medium','hard'];
  const loaded = diffs.filter(d => results[d]);
  if (!loaded.length) return;

  const avgF1 = loaded.reduce((s,d) => s + (results[d].f1_score||0), 0) / loaded.length;
  const avgDisc = loaded.reduce((s,d) => s + (results[d].discovery_rate||0), 0) / loaded.length;
  const grades = loaded.map(d => results[d].grade || 'F');
  const gradeOrder = 'SABCDF';
  const best = grades.sort((a,b) => gradeOrder.indexOf(a) - gradeOrder.indexOf(b))[0];
  const totalPii = loaded.reduce((s,d) => s + (results[d].final_metrics?.true_positives||0), 0);
  const totalSteps = loaded.reduce((s,d) => s + (results[d].final_metrics?.steps_used || results[d].steps?.length || 0), 0);

  document.getElementById('kpi-f1').textContent = (avgF1*100).toFixed(1)+'%';
  document.getElementById('kpi-disc').textContent = (avgDisc*100).toFixed(1)+'%';
  document.getElementById('kpi-grade').textContent = best;
  document.getElementById('kpi-pii').textContent = totalPii;
  document.getElementById('kpi-steps').textContent = totalSteps;
}

async function runAll() {
  const diffs = ['easy','medium','hard'];
  for (const d of diffs) {
    const panel = document.getElementById(`panel-${d}`);
    panel.innerHTML = '<div class="loading"><div class="spinner"></div><br>Running '+d+' investigation...</div>';
    panel.style.display = 'block';
    try {
      const data = await fetchEpisode(d);
      results[d] = data;
      renderPanel(d, data);
      updateKPIs();
    } catch(e) {
      panel.innerHTML = '<div class="loading" style="color:var(--red)">Error: '+e.message+'</div>';
    }
  }
  // Show easy tab
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelector('[data-diff="easy"]').classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-easy').classList.add('active');
}

// Auto-run on page load
window.addEventListener('load', () => setTimeout(runAll, 500));
</script>

</body>
</html>
"""


# ───────────── Custom API Docs ─────────────

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    css = """
    body{background:linear-gradient(135deg,#090b12,#12172b)!important;color:#f4f7ff!important;font-family:Inter,system-ui,sans-serif!important}
    .swagger-ui .topbar{background:rgba(8,10,20,.8)!important;backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,.15)}
    .swagger-ui .topbar .download-url-wrapper{display:none}
    .swagger-ui .info{background:rgba(20,24,44,.65);border:1px solid rgba(255,255,255,.22);border-radius:20px;backdrop-filter:blur(14px);padding:1.2rem 1.4rem!important;box-shadow:0 12px 32px rgba(0,0,0,.3)}
    .swagger-ui .info hgroup.main h2,.swagger-ui .info p,.swagger-ui .opblock-tag,.swagger-ui .opblock-summary,.swagger-ui .response-col_status,.swagger-ui .response-col_description{color:#f4f7ff!important}
    .swagger-ui .opblock{border:1px solid rgba(255,255,255,.22)!important;border-radius:16px!important;background:rgba(255,255,255,.04)!important;margin:.8rem 0!important}
    .swagger-ui .btn.execute{background:linear-gradient(135deg,#7c9cff,#72e4d2)!important;color:#0b1023!important;border:0!important;font-weight:700!important}
    .swagger-ui input,.swagger-ui textarea,.swagger-ui select{background:rgba(255,255,255,.08)!important;color:#f4f7ff!important;border:1px solid rgba(255,255,255,.26)!important;border-radius:10px!important}
    .swagger-ui .scheme-container,.swagger-ui .responses-table,.swagger-ui table thead tr th{background:rgba(255,255,255,.04)!important;color:#f4f7ff!important}
    """
    resp = get_swagger_ui_html(
        openapi_url=app.openapi_url, title=f"{app.title} - API Docs",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        swagger_ui_parameters={"docExpansion":"list","deepLinking":True,"tryItOutEnabled":True,"displayRequestDuration":True},
    )
    resp.body = resp.body.replace(b"</head>", f"<style>{css}</style>\n</head>".encode())
    resp.headers["content-length"] = str(len(resp.body))
    return resp

@app.get("/redoc", include_in_schema=False)
async def redoc():
    return get_redoc_html(openapi_url=app.openapi_url, title=f"{app.title} - ReDoc")


# ───────────── OpenEnv API Endpoints ─────────────

@app.post("/reset", response_model=ResetResult)
async def reset(
    difficulty: str = Query("medium", description="Difficulty: easy, medium, hard"),
    seed: Optional[int] = Query(None, description="Random seed for reproducibility"),
):
    """Reset environment and start a new investigation episode."""
    logger.info(f"[RESET] difficulty={difficulty} seed={seed}")
    try:
        return env.reset(difficulty=difficulty, seed=seed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/step", response_model=StepResult)
async def step(action: AgentAction):
    """Execute one investigation step (SCAN / INVESTIGATE / REDACT / SUBMIT)."""
    logger.info(f"[STEP] action={action.action_type.value} target={action.target_entity}")
    try:
        return env.step(action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state", response_model=EnvironmentState)
async def get_state():
    """Get current environment state."""
    try:
        return env.state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Health check."""
    return {"status":"healthy","service":"Sentinel-Log-Shield","version":"2.0.0",
            "is_running":env.is_running,"steps_used":env.steps_used}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")
