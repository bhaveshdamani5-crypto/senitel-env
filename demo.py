"""
demo.py — Interactive Gradio Demo for Sentinel-Log-Shield

Provides a web interface for Hugging Face Spaces with:
- Real-time task execution
- Step-by-step output display
- Visual success/failure indicators
- Custom log input option
"""

import gradio as gr
import sys
import os
from env import LogSanitizerEnvironment, TaskEnum
from models import RedactionAction

# Color codes for terminal-style output
GREEN = "#4CAF50"
RED = "#f44336"
BLUE = "#2196F3"
YELLOW = "#FFC107"


def format_output(text: str, color: str = "white") -> str:
    """Format output with color for display."""
    return f"<span style='color:{color}; font-family:monospace'>{text}</span>"


def run_demo_episode(task_choice: str) -> tuple[str, str, float]:
    """
    Run a complete demo episode.

    Args:
        task_choice: Selected task ("Task 1: Email & IPv4", etc.)

    Returns:
        Tuple of (output_log, status_message, score)
    """
    # Map choice to TaskEnum
    task_map = {
        "Task 1: Email & IPv4 Detection (Easy)": TaskEnum.TASK_1,
        "Task 2: Username Extraction (Medium)": TaskEnum.TASK_2,
        "Task 3: Secret Detection (Hard)": TaskEnum.TASK_3,
    }

    task = task_map.get(task_choice, TaskEnum.TASK_1)

    # Initialize environment
    env = LogSanitizerEnvironment()
    step_summaries = []

    # Reset environment
    reset_resp = env.reset()
    observation = reset_resp.observation

    # Run 3 steps
    step_num = 0
    done = False
    rewards = []
    total_steps = 3

    while not done and step_num < total_steps:
        step_num += 1
        # Simulate agent redaction (regex fallback mode)
        if task == TaskEnum.TASK_1:
            # Email & IPv4
            import re
            
            log = observation.raw_log
            redactions = []

            email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            for match in re.finditer(email_pattern, log):
                redactions.append({
                    "type": "email",
                    "original": match.group(),
                    "redacted": "[EMAIL_REDACTED]"
                })
                log = log.replace(match.group(), "[EMAIL_REDACTED]", 1)

            ipv4_pattern = (
                r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
            )
            for match in re.finditer(ipv4_pattern, log):
                if match.group() != "255.255.255.255":
                    redactions.append({
                        "type": "ipv4",
                        "original": match.group(),
                        "redacted": "[IP_REDACTED]"
                    })
                    log = log.replace(match.group(), "[IP_REDACTED]", 1)

            redacted_log = log

        elif task == TaskEnum.TASK_2:
            # Username extraction
            import re
            
            log = observation.raw_log
            redactions = []
            pattern = r"User\s+'([A-Za-z]+)'"
            
            for match in re.finditer(pattern, log, re.IGNORECASE):
                username = match.group(1)
                redactions.append({
                    "type": "username",
                    "original": username,
                    "redacted": "[USER_REDACTED]"
                })
                log = log.replace(username, "[USER_REDACTED]")
            
            redacted_log = log

        else:  # TASK_3
            # Secret detection
            import re
            
            log = observation.raw_log
            redactions = []
            patterns = [
                r"\bsk_[a-z0-9_]{20,}\b",
                r"\b[A-Z0-9]{20}\b",
                r"(?:secret|key|password|api_key|token)\s*=\s*(\S+)",
            ]

            for pattern in patterns:
                for match in re.finditer(pattern, log, re.IGNORECASE):
                    token = match.group(1) if "(" in pattern else match.group(0)
                    if len(token) > 5:
                        redactions.append({
                            "type": "token",
                            "original": token[:10] + "...",
                            "redacted": "[TOKEN_REDACTED]"
                        })
                        log = log.replace(token, "[TOKEN_REDACTED]")
            
            redacted_log = log

        # Create action and step
        action = RedactionAction(
            log_id=observation.log_id,
            redactions=redactions,
            redacted_log=redacted_log,
            confidence=0.95 if redactions else 0.5,
        )

        # Step environment
        step_resp = env.step(action)
        observation = step_resp.observation
        reward = step_resp.reward
        done = step_resp.done

        # Save neat per-step summary for table rendering
        step_summaries.append(
            {
                "step": step_num,
                "found": len(redactions),
                "types": ", ".join([r["type"] for r in redactions]) if redactions else "-",
                "reward": reward.total_reward,
                "f1": reward.metrics["f1_score"],
                "precision": reward.metrics["precision"],
                "recall": reward.metrics["recall"],
                "feedback": reward.feedback,
            }
        )

        rewards.append(reward.total_reward)

    final_score = sum(rewards) / len(rewards) if rewards else 0.0
    success = final_score >= 0.70
    rows = []
    for item in step_summaries:
        rows.append(
            "<tr>"
            f"<td>{item['step']}</td>"
            f"<td>{item['found']}</td>"
            f"<td>{item['types']}</td>"
            f"<td>{item['reward']:.2f}</td>"
            f"<td>{item['f1']:.2f}</td>"
            f"<td>{item['precision']:.2f}</td>"
            f"<td>{item['recall']:.2f}</td>"
            "</tr>"
        )
    output_html = f"""
    <div style="padding:10px 12px;">
      <h3 style="margin:0 0 8px 0; color:#ffffff;">Episode Results</h3>
      <p style="margin:0 0 10px 0; color:#d8deea;">
        <strong>Task:</strong> {observation.task.value} &nbsp;|&nbsp;
        <strong>Expected:</strong> {", ".join(observation.pii_types_expected)}
      </p>
      <p style="margin:0 0 10px 0; color:#d8deea;"><strong>Raw Log:</strong> {observation.raw_log}</p>
      <div style="overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead>
            <tr style="background:#111827; color:#f5f7ff;">
              <th style="padding:8px; border:1px solid rgba(255,255,255,0.16);">Step</th>
              <th style="padding:8px; border:1px solid rgba(255,255,255,0.16);">Found</th>
              <th style="padding:8px; border:1px solid rgba(255,255,255,0.16);">Types</th>
              <th style="padding:8px; border:1px solid rgba(255,255,255,0.16);">Reward</th>
              <th style="padding:8px; border:1px solid rgba(255,255,255,0.16);">F1</th>
              <th style="padding:8px; border:1px solid rgba(255,255,255,0.16);">Precision</th>
              <th style="padding:8px; border:1px solid rgba(255,255,255,0.16);">Recall</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
      </div>
    </div>
    """

    # Create status message
    status_msg = (
        f"<h3 style='margin:0; color:{GREEN if success else RED};'>"
        f"{'Success' if success else 'Needs Improvement'}</h3>"
        f"<p style='margin:.4rem 0; color:#eef2ff;'>Final Score: <strong>{final_score:.2f}</strong>/1.00</p>"
        f"<p style='margin:.2rem 0; color:#d8deea;'>Steps: {step_num}</p>"
    )

    return output_html, status_msg, final_score


def create_demo():
    """Create Gradio interface with simple, clean styling."""
    premium_css = """
    .gradio-container {
      font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif !important;
      background: #0f1117 !important;
      color: #e6e8ee !important;
    }
    .gradio-container .block,
    .gradio-container .panel,
    .gradio-container .form {
      border: 1px solid rgba(255,255,255,0.10) !important;
      border-radius: 12px !important;
      background: #161b22 !important;
      box-shadow: none !important;
    }
    .gradio-container .prose,
    .gradio-container .prose p,
    .gradio-container label {
      color: #d0d7e2 !important;
    }
    .gradio-container .prose h1,
    .gradio-container .prose h2,
    .gradio-container .prose h3 {
      color: #ffffff !important;
    }
    .gradio-container button.primary {
      background: #5E6AD2 !important;
      color: #fff !important;
      border: none !important;
      border-radius: 10px !important;
      font-weight: 600 !important;
    }
    .gradio-container button.primary:hover {
      background: #6872D9 !important;
    }
    .gradio-container input,
    .gradio-container textarea,
    .gradio-container select {
      background: #0f141c !important;
      color: #f2f6ff !important;
      border: 1px solid rgba(255,255,255,0.12) !important;
      border-radius: 10px !important;
    }
    .gradio-container .prose table,
    .gradio-container .prose th,
    .gradio-container .prose td {
      color: #f2f6ff !important;
      border-color: rgba(255,255,255,0.16) !important;
    }
    .gradio-container .prose th {
      background: #111827 !important;
      font-weight: 700 !important;
    }
    .gradio-container .prose td {
      background: #161b22 !important;
    }
    .gradio-container input[type="number"] {
      color: #ffffff !important;
      font-weight: 700 !important;
      opacity: 1 !important;
    }
    .hero-title {
      margin: 0;
      font-size: clamp(1.8rem, 3vw, 2.4rem);
      font-weight: 700;
      letter-spacing: -0.02em;
      color: #f3f5f8;
    }
    .hero-sub {
      margin-top: .55rem;
      color: #b8c0cc;
      line-height: 1.6;
      max-width: 760px;
    }
    """
    theme = gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="cyan",
        neutral_hue="slate",
    )

    with gr.Blocks(
        title="Sentinel-Log-Shield: OpenEnv Demo",
    ) as demo:

        gr.HTML(
            """
            <div style="padding: 0.3rem 0 0.9rem;">
              <h1 class="hero-title">Sentinel-Log-Shield Demo</h1>
              <p class="hero-sub">
                Clean evaluation interface for running all tasks and presenting results clearly to judges.
              </p>
            </div>
            """
        )

        # Controls
        with gr.Row():
            with gr.Column(scale=1):
                task_choice = gr.Radio(
                    choices=[
                        "Task 1: Email & IPv4 Detection (Easy)",
                        "Task 2: Username Extraction (Medium)",
                        "Task 3: Secret Detection (Hard)",
                    ],
                    value="Task 1: Email & IPv4 Detection (Easy)",
                    label="📋 Select Task",
                )
                run_button = gr.Button(
                    "▶ Run Demo",
                    variant="primary",
                    size="lg",
                )

        # Output area
        with gr.Row():
            with gr.Column():
                output_display = gr.HTML(
                    value=format_output(
                        "Click 'Run Demo' to start...",
                        BLUE,
                    ),
                )

        # Status and score
        with gr.Row():
            with gr.Column():
                status_display = gr.HTML(
                    value="<p>Ready to run...</p>",
                )
            with gr.Column():
                score_display = gr.Number(
                    label="📈 Episode Score",
                    value=0.0,
                    interactive=False,
                )

        gr.Markdown(
            """
            ### How to evaluate this demo
            - Pick a task and run the full episode.
            - Inspect extracted entities, reward feedback, and final score.
            - Use score bands to judge redaction reliability:
              - **1.00**: ideal extraction with utility preserved
              - **0.80+**: high confidence behavior
              - **0.50+**: partial correctness
              - **<0.50**: substantial misses

            Repository: https://github.com/bhaveshdamani5-crypto/senitel-env
            """
        )

        # Connect button to function
        run_button.click(
            fn=run_demo_episode,
            inputs=[task_choice],
            outputs=[output_display, status_display, score_display],
        )

        # Auto-run on startup (optional)
        demo.load(
            fn=run_demo_episode,
            inputs=[task_choice],
            outputs=[output_display, status_display, score_display],
        )

    return demo, premium_css, theme


if __name__ == "__main__":
    demo, premium_css, theme = create_demo()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        share=False,
        css=premium_css,
        theme=theme,
    )
