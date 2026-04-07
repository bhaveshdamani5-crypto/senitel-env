"""
Sentinel-Log-Shield FastAPI server with premium custom docs UI.
Provides POST /reset, POST /step, GET /state endpoints.
"""

from fastapi import FastAPI, HTTPException, Body
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import gradio as gr
import logging
import os
import subprocess
from html import escape
from env import LogSanitizerEnvironment
from models import RedactionAction, ResetResponse, StepResponse, EnvironmentState
from demo import create_demo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Sentinel-Log-Shield",
    description="SST-compliant OpenEnv for PII redaction in system logs",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

# CORS middleware for Hugging Face compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global environment instance
env = LogSanitizerEnvironment()
logger.info("Environment initialized: Sentinel-Log-Shield")


@app.get("/")
async def root():
    """Landing page with premium visual design for demos/judges."""
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sentinel-Log-Shield API</title>
  <style>
    :root {
      --bg-1: #08090d;
      --bg-2: #151a2e;
      --glass: rgba(255, 255, 255, 0.08);
      --glass-border: rgba(255, 255, 255, 0.22);
      --text: #f4f7ff;
      --muted: #b6bfd8;
      --accent: #7c9cff;
      --accent-2: #72e4d2;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, Segoe UI, system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 20% 20%, #3f4a8c 0%, transparent 30%),
        radial-gradient(circle at 80% 25%, #1d6e7c 0%, transparent 25%),
        linear-gradient(135deg, var(--bg-1), var(--bg-2));
      min-height: 100vh;
      overflow: hidden;
    }
    .orbs::before, .orbs::after {
      content: "";
      position: fixed;
      width: 34rem;
      height: 34rem;
      border-radius: 50%;
      filter: blur(40px);
      opacity: 0.55;
      pointer-events: none;
      animation: float 10s ease-in-out infinite;
    }
    .orbs::before { background: #7c9cff; top: -12rem; right: -10rem; }
    .orbs::after { background: #72e4d2; left: -10rem; bottom: -12rem; animation-delay: -4s; }
    .wrap {
      max-width: 1024px;
      margin: 0 auto;
      padding: 3rem 1.2rem 2rem;
      position: relative;
      z-index: 2;
      animation: fadeUp .8s ease forwards;
    }
    .card {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 24px;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.35);
      padding: 2rem;
    }
    h1 {
      font-size: clamp(1.8rem, 5vw, 3rem);
      margin: 0 0 .8rem;
      line-height: 1.1;
      letter-spacing: -.02em;
    }
    p { color: var(--muted); line-height: 1.6; margin: 0; }
    .tag {
      display: inline-block;
      margin-bottom: 1rem;
      padding: .45rem .9rem;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,.28);
      background: rgba(255,255,255,.09);
      font-size: .82rem;
      letter-spacing: .05em;
      text-transform: uppercase;
    }
    .grid {
      margin-top: 1.3rem;
      display: grid;
      gap: 1rem;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }
    .kpi {
      background: rgba(255,255,255,.05);
      border: 1px solid rgba(255,255,255,.16);
      border-radius: 16px;
      padding: .9rem 1rem;
      transition: transform .25s ease, border-color .25s ease;
    }
    .kpi:hover { transform: translateY(-4px); border-color: rgba(124,156,255,.65); }
    .kpi b { display:block; font-size:1.05rem; margin-bottom:.25rem; }
    .actions { margin-top: 1.4rem; display: flex; gap: .8rem; flex-wrap: wrap; }
    a.btn {
      text-decoration: none;
      color: #0a0f20;
      font-weight: 700;
      padding: .75rem 1.1rem;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      transition: transform .2s ease, box-shadow .2s ease;
      box-shadow: 0 8px 22px rgba(114, 228, 210, .28);
    }
    a.btn:hover { transform: translateY(-2px); }
    a.ghost {
      background: transparent;
      color: var(--text);
      border: 1px solid rgba(255,255,255,.28);
      box-shadow: none;
    }
    footer { margin-top: 1rem; color: #cfd6eb; opacity: .85; font-size: .9rem; }
    @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(16px); } }
    @keyframes fadeUp { from { opacity: 0; transform: translateY(16px);} to {opacity:1; transform:none;} }
  </style>
</head>
<body>
  <div class="orbs"></div>
  <main class="wrap">
    <section class="card">
      <span class="tag">Sentinel-Log-Shield • v1.0.0</span>
      <h1>Enterprise Log Redaction API</h1>
      <p>
        Production-ready OpenEnv environment for security-focused PII and secret redaction.
        Explore the interactive docs and inspect live environment state in one click.
      </p>
      <div class="grid">
        <article class="kpi"><b>Task Coverage</b>Email, IPv4, usernames, and high-risk secrets.</article>
        <article class="kpi"><b>Scoring Model</b>Precision/Recall/F1 with over-redaction penalties.</article>
        <article class="kpi"><b>Deployment Ready</b>Hugging Face Spaces + Docker-first architecture.</article>
      </div>
      <div class="actions">
        <button class="btn ghost" onclick="goTo('/demo')">🎮 Open Demo UI</button>
        <button class="btn" onclick="goTo('/docs')">📘 Open Docs</button>
        <button class="btn ghost" onclick="goTo('/redoc')">📚 Open Technical Reference</button>
        <button class="btn ghost" onclick="runHealth()">💚 Health Check</button>
        <button class="btn ghost" onclick="runTests()">🧪 Run Test Suite</button>
      </div>
      <div id="action-result" style="margin-top:12px; padding:10px; border:1px solid rgba(255,255,255,.14); border-radius:10px; background:rgba(0,0,0,.18); color:#dbe6ff; white-space:pre-wrap;">Ready.</div>
      <script>
        function goTo(path) {
          window.location.href = path;
        }
        async function runHealth() {
          const box = document.getElementById('action-result');
          box.textContent = 'Running health check...';
          try {
            const res = await fetch('/health');
            const data = await res.json();
            box.textContent = 'Health: ' + JSON.stringify(data, null, 2);
          } catch (e) {
            box.textContent = 'Health check failed: ' + String(e);
          }
        }
        async function runTests() {
          const box = document.getElementById('action-result');
          box.textContent = 'Running test suite... this may take up to 2-3 minutes.';
          try {
            const res = await fetch('/run-tests?format=json');
            const data = await res.json();
            box.textContent = 'Runner: ' + data.runner + '\\nStatus: ' + data.status + '\\nExit: ' + data.exit_code + '\\n\\n' + data.output;
          } catch (e) {
            box.textContent = 'Test suite failed to run: ' + String(e);
          }
        }
      </script>
      </div>
    </section>
    <footer>Built for high-stakes log privacy and compliance reviews.</footer>
  </main>
</body>
</html>
        """
    )


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Custom premium Swagger UI with motion and glassmorphism."""
    custom_css = """
    :root {
      --glass: rgba(20, 24, 44, 0.65);
      --glass-border: rgba(255,255,255,0.22);
      --text: #f4f7ff;
      --muted: #aeb8d5;
      --accent: #8aa1ff;
      --accent-2: #72e4d2;
      --bg-0: #090b12;
      --bg-1: #12172b;
    }
    body {
      background:
        radial-gradient(circle at 12% 18%, #3f4a8c 0%, transparent 28%),
        radial-gradient(circle at 88% 28%, #1b7e87 0%, transparent 24%),
        linear-gradient(135deg, var(--bg-0), var(--bg-1)) !important;
      color: var(--text) !important;
      font-family: Inter, Segoe UI, system-ui, sans-serif !important;
      overflow-x: hidden;
    }
    body::before, body::after {
      content: "";
      position: fixed;
      width: 30rem;
      height: 30rem;
      border-radius: 50%;
      filter: blur(34px);
      opacity: .4;
      z-index: 0;
      animation: float 10s ease-in-out infinite;
      pointer-events: none;
    }
    body::before { top: -12rem; right: -10rem; background: #7c9cff; }
    body::after { bottom: -12rem; left: -8rem; background: #72e4d2; animation-delay: -4s; }
    .swagger-ui { position: relative; z-index: 1; }
    .swagger-ui .topbar {
      background: rgba(8,10,20,.7) !important;
      backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(255,255,255,.15);
      animation: fadeDown .6s ease forwards;
    }
    .swagger-ui .topbar .download-url-wrapper { display: none; }
    .swagger-ui .info {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 20px;
      backdrop-filter: blur(14px);
      padding: 1.2rem 1.4rem !important;
      box-shadow: 0 12px 32px rgba(0,0,0,.3);
      animation: fadeUp .7s ease forwards;
    }
    .swagger-ui .info hgroup.main h2,
    .swagger-ui .info p,
    .swagger-ui .opblock-tag,
    .swagger-ui .opblock-summary,
    .swagger-ui .response-col_status,
    .swagger-ui .response-col_description {
      color: var(--text) !important;
    }
    .swagger-ui .opblock-tag {
      border-color: rgba(255,255,255,.18) !important;
      margin-top: 1rem;
      background: rgba(255,255,255,.05);
      border-radius: 14px;
      transition: transform .2s ease, border-color .2s ease;
    }
    .swagger-ui .opblock-tag:hover { transform: translateY(-1px); border-color: rgba(138,161,255,.65) !important; }
    .swagger-ui .opblock {
      border: 1px solid var(--glass-border) !important;
      border-radius: 16px !important;
      background: rgba(255,255,255,.04) !important;
      backdrop-filter: blur(10px);
      margin: .8rem 0 !important;
      animation: fadeUp .6s ease both;
    }
    .swagger-ui .opblock .opblock-summary { border-color: rgba(255,255,255,.13) !important; }
    .swagger-ui .btn.execute {
      background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
      color: #0b1023 !important;
      border: 0 !important;
      font-weight: 700 !important;
      transition: transform .2s ease, box-shadow .2s ease !important;
    }
    .swagger-ui .btn.execute:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 20px rgba(114,228,210,.35);
    }
    .swagger-ui input, .swagger-ui textarea, .swagger-ui select {
      background: rgba(255,255,255,.08) !important;
      color: var(--text) !important;
      border: 1px solid rgba(255,255,255,.26) !important;
      border-radius: 10px !important;
    }
    .swagger-ui .scheme-container, .swagger-ui .responses-table, .swagger-ui table thead tr th {
      background: rgba(255,255,255,.04) !important;
      color: var(--text) !important;
      border-color: rgba(255,255,255,.16) !important;
    }
    @keyframes fadeUp { from {opacity: 0; transform: translateY(10px);} to {opacity: 1; transform: none;} }
    @keyframes fadeDown { from {opacity: 0; transform: translateY(-8px);} to {opacity: 1; transform: none;} }
    @keyframes float { 0%, 100% {transform: translateY(0);} 50% {transform: translateY(14px);} }
    """
    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - API Docs",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        swagger_ui_parameters={
            "docExpansion": "list",
            "deepLinking": True,
            "defaultModelsExpandDepth": -1,
            "displayRequestDuration": True,
            "filter": True,
            "persistAuthorization": True,
            "tryItOutEnabled": True,
        },
        init_oauth=None,
    )
    response.body = response.body.replace(
        b"</head>",
        (f"<style>{custom_css}</style>\n</head>").encode("utf-8"),
    )
    response.headers["content-length"] = str(len(response.body))
    return response


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """Redoc endpoint for clean technical reference."""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
    )


@app.post("/reset", response_model=ResetResponse)
async def reset():
    """
    Reset the environment and start a new episode.
    
    Returns:
        ResetResponse with initial observation and info.
    """
    logger.info("[START] Reset called - new episode beginning")
    try:
        response = env.reset()
        logger.info(f"[RESET] Task: {response.observation.task}, Log ID: {response.observation.log_id}")
        return response
    except Exception as e:
        logger.error(f"Error in reset: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@app.post("/step", response_model=StepResponse)
async def step(
    action: RedactionAction = Body(
        ...,
        examples={
            "task_1_email_ipv4": {
                "summary": "Task 1 - Email and IPv4 redaction",
                "description": "Sample payload for easy pattern redaction test.",
                "value": {
                    "log_id": "abc12345",
                    "redactions": [
                        {
                            "type": "email",
                            "original": "alice.smith@company.com",
                            "redacted": "[REDACTED_EMAIL]"
                        },
                        {
                            "type": "ipv4",
                            "original": "10.0.0.5",
                            "redacted": "[REDACTED_IP]"
                        }
                    ],
                    "redacted_log": "User [REDACTED_EMAIL] logged in from [REDACTED_IP] at 14:30 UTC",
                    "confidence": 0.95
                },
            },
            "task_2_username": {
                "summary": "Task 2 - Username extraction",
                "description": "Sample payload for contextual username redaction.",
                "value": {
                    "log_id": "def67890",
                    "redactions": [
                        {
                            "type": "username",
                            "original": "Bhavesh",
                            "redacted": "[REDACTED_USER]"
                        }
                    ],
                    "redacted_log": "Error: User '[REDACTED_USER]' failed login attempt after 3 tries",
                    "confidence": 0.9
                },
            },
            "task_3_secrets": {
                "summary": "Task 3 - Secret/token redaction",
                "description": "Sample payload for high-risk token/secret redaction.",
                "value": {
                    "log_id": "ghi24680",
                    "redactions": [
                        {
                            "type": "token",
                            "original": "sk_live_51234567890abcdef",
                            "redacted": "[REDACTED_TOKEN]"
                        }
                    ],
                    "redacted_log": "Traceback (most recent call last): [REDACTED_TOKEN] in auth.py line 42",
                    "confidence": 0.92
                },
            },
        },
    )
):
    """
    Execute one step: process redaction action and return reward.
    
    Args:
        action: RedactionAction with redactions and redacted log.
    
    Returns:
        StepResponse with observation, reward, done flag.
    """
    logger.info(f"[STEP] Processing action for log: {action.log_id}")
    try:
        response = env.step(action)
        logger.info(
            f"[STEP] Reward: {response.reward.total_reward:.2f}, "
            f"Done: {response.done}, F1: {response.reward.metrics.get('f1_score', 0):.2f}"
        )
        return response
    except ValueError as e:
        logger.error(f"Validation error in step: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in step: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Step failed: {str(e)}")


@app.get("/state", response_model=EnvironmentState)
async def get_state():
    """
    Get current environment state.
    
    Returns:
        EnvironmentState with current observation, metrics, and history.
    """
    logger.info("[END] State query")
    try:
        return env.state()
    except Exception as e:
        logger.error(f"Error in state: {str(e)}")
        raise HTTPException(status_code=500, detail=f"State query failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Sentinel-Log-Shield",
        "is_running": env.is_running,
        "cumulative_reward": env.cumulative_reward
    }

def _execute_tests() -> dict:
    """Run test suite with pytest first, then unittest fallback."""
    commands = [
        ("pytest", ["python", "-m", "pytest", "-q", "tests", "--disable-warnings"]),
        ("unittest", ["python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]),
    ]
    last_error = None
    for runner, cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                env={**os.environ, "PYTHONWARNINGS": "ignore"},
            )
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            if len(output) > 20000:
                output = output[:20000] + "\n... [truncated]"
            return {
                "runner": runner,
                "status": "passed" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "output": output.strip(),
            }
        except subprocess.TimeoutExpired:
            return {
                "runner": runner,
                "status": "failed",
                "exit_code": 124,
                "output": "Test run timed out after 180 seconds",
            }
        except Exception as exc:
            last_error = str(exc)

    return {
        "runner": "none",
        "status": "failed",
        "exit_code": 1,
        "output": f"Unable to execute tests: {last_error or 'unknown error'}",
    }


@app.get("/run-tests")
async def run_tests(format: str = "html"):
    """Run test suite and return HTML report (or JSON with ?format=json)."""
    result = _execute_tests()
    if format == "json":
        return result

    ok = result["status"] == "passed"
    color = "#22c55e" if ok else "#ef4444"
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sentinel Test Suite</title>
  <style>
    body {{ font-family: Inter, Segoe UI, system-ui, sans-serif; margin: 0; background:#0f1117; color:#eef2ff; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 20px; }}
    .card {{ border: 1px solid rgba(255,255,255,.14); border-radius: 12px; padding: 16px; background:#151a24; }}
    pre {{ background:#0b0f17; border:1px solid rgba(255,255,255,.12); border-radius:10px; padding:12px; overflow:auto; white-space:pre-wrap; }}
    .status {{ color:{color}; font-weight:700; }}
    a {{ color:#93c5fd; }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h2 style="margin:0 0 8px 0;">Space Test Suite</h2>
      <p style="margin:0 0 10px 0;">Runner: <strong>{escape(result["runner"])}</strong> | Exit: <strong>{result["exit_code"]}</strong> | Status: <span class="status">{escape(result["status"])}</span></p>
      <p style="margin:0 0 14px 0;"><a href="/run-tests?format=json">View JSON output</a></p>
      <pre>{escape(result["output"])}</pre>
    </section>
  </main>
</body>
</html>
        """
    )


# Mount Gradio demo under /demo while keeping FastAPI docs at /docs
gradio_app, gradio_css, gradio_theme = create_demo()
gradio_app.css = gradio_css
gradio_app.theme = gradio_theme
app = gr.mount_gradio_app(
    app,
    gradio_app,
    path="/demo",
)


def main():
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860,
        log_level="info"
    )


if __name__ == "__main__":
    main()
