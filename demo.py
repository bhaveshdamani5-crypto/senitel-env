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
    output_lines = []

    # Reset environment
    reset_resp = env.reset()
    observation = reset_resp.observation

    output_lines.append(
        format_output(
            f"╔════════════════════════════════════════════════════════╗",
            BLUE,
        )
    )
    output_lines.append(
        format_output(f"║  Sentinel-Log-Shield: Real-Time Demo                 ║", BLUE)
    )
    output_lines.append(
        format_output(
            f"╚════════════════════════════════════════════════════════╝",
            BLUE,
        )
    )
    output_lines.append("")

    # Show task info
    output_lines.append(
        format_output(f"📋 Task: {observation.task.value}", BLUE)
    )
    output_lines.append(
        format_output(f"🔍 Expected PII Types: {', '.join(observation.pii_types_expected)}", BLUE)
    )
    output_lines.append(format_output(f"📝 Raw Log:\n{observation.raw_log}", BLUE))
    output_lines.append("")

    # Run 3 steps
    step_num = 0
    done = False
    rewards = []
    total_steps = 3

    while not done and step_num < total_steps:
        step_num += 1
        output_lines.append(
            format_output(f"{'─' * 60}", YELLOW)
        )
        output_lines.append(
            format_output(f"🔄 STEP {step_num}/{total_steps}", YELLOW)
        )

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

        # Show redactions found
        output_lines.append(
            format_output(f"✓ Found {len(redactions)} redactions: {', '.join([r['type'] for r in redactions])}", GREEN)
        )

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

        # Show step result
        output_lines.append(
            format_output(
                f"💰 Reward: {reward.total_reward:.2f} | "
                f"F1: {reward.metrics['f1_score']:.2f} | "
                f"Precision: {reward.metrics['precision']:.2f} | "
                f"Recall: {reward.metrics['recall']:.2f}",
                GREEN if reward.total_reward > 0 else RED,
            )
        )
        output_lines.append(
            format_output(f"💬 Feedback: {reward.feedback}", BLUE)
        )

        rewards.append(reward.total_reward)

    # Final result
    output_lines.append("")
    output_lines.append(format_output(f"{'═' * 60}", BLUE))

    final_score = sum(rewards) / len(rewards) if rewards else 0.0
    success = final_score >= 0.70

    status_emoji = "✅" if success else "⚠️"
    status_color = GREEN if success else YELLOW

    output_lines.append(
        format_output(
            f"{status_emoji} EPISODE COMPLETE",
            status_color,
        )
    )
    output_lines.append(
        format_output(
            f"   Steps: {step_num} | Score: {final_score:.2f} | Success: {'YES' if success else 'NO'}",
            status_color,
        )
    )
    output_lines.append(
        format_output(f"   Rewards: {', '.join([f'{r:.2f}' for r in rewards])}", status_color)
    )
    output_lines.append(format_output(f"{'═' * 60}", BLUE))

    # Create status message
    status_msg = (
        f"<h2 style='color:{GREEN if success else RED}'>{'✅ SUCCESS' if success else '⚠️ NEEDS IMPROVEMENT'}</h2>"
        f"<p><strong>Final Score:</strong> {final_score:.2f}/1.00</p>"
        f"<p><strong>Episodes Run:</strong> {len(rewards)}</p>"
        f"<p><strong>Average Reward:</strong> {final_score:.2f}</p>"
    )

    return "\n".join(output_lines), status_msg, final_score


def create_demo():
    """Create Gradio interface."""
    premium_css = """
    :root {
      --background-deep: #020203;
      --background-base: #050506;
      --background-elevated: #0a0a0c;
      --surface: rgba(255,255,255,0.05);
      --surface-hover: rgba(255,255,255,0.08);
      --foreground: #EDEDEF;
      --foreground-muted: #8A8F98;
      --foreground-subtle: rgba(255,255,255,0.60);
      --accent: #5E6AD2;
      --accent-bright: #6872D9;
      --accent-glow: rgba(94,106,210,0.3);
      --border-default: rgba(255,255,255,0.06);
      --border-hover: rgba(255,255,255,0.10);
    }

    .gradio-container {
      position: relative;
      background:
        radial-gradient(ellipse at top, #0a0a0f 0%, #050506 50%, #020203 100%),
        linear-gradient(180deg, #050506, #020203) !important;
      color: var(--foreground) !important;
      font-family: Inter, "Geist Sans", system-ui, sans-serif !important;
      overflow-x: hidden;
    }

    .gradio-container::before,
    .gradio-container::after {
      content: "";
      position: fixed;
      z-index: 0;
      width: 1000px;
      height: 1400px;
      filter: blur(150px);
      pointer-events: none;
      opacity: 0.22;
      animation: floatAmbient 10s ease-in-out infinite;
    }
    .gradio-container::before {
      top: -45%;
      left: 35%;
      background: radial-gradient(circle, rgba(94,106,210,0.95) 0%, rgba(94,106,210,0.0) 70%);
    }
    .gradio-container::after {
      top: -30%;
      left: -30%;
      background: radial-gradient(circle, rgba(126,90,255,0.45) 0%, rgba(126,90,255,0) 70%);
      animation-delay: -4s;
    }

    .gradio-container .main,
    .gradio-container .wrap {
      position: relative;
      z-index: 1;
    }

    .gradio-container .block,
    .gradio-container .panel,
    .gradio-container .form {
      border: 1px solid var(--border-default) !important;
      background: linear-gradient(to bottom, rgba(255,255,255,0.08), rgba(255,255,255,0.02)) !important;
      border-radius: 16px !important;
      backdrop-filter: blur(12px);
      box-shadow:
        0 0 0 1px rgba(255,255,255,0.06),
        0 2px 20px rgba(0,0,0,0.4),
        0 0 40px rgba(0,0,0,0.2);
      transition: border-color .24s cubic-bezier(.16,1,.3,1), transform .24s cubic-bezier(.16,1,.3,1), box-shadow .24s cubic-bezier(.16,1,.3,1);
    }
    .spotlight-card {
      position: relative;
      overflow: hidden;
    }
    .spotlight-card::before {
      content: "";
      position: absolute;
      inset: -1px;
      pointer-events: none;
      opacity: 0;
      background: radial-gradient(
        300px circle at var(--spot-x, 50%) var(--spot-y, 50%),
        rgba(94,106,210,0.15),
        rgba(94,106,210,0.0) 60%
      );
      transition: opacity .24s cubic-bezier(.16,1,.3,1);
    }
    .spotlight-card:hover::before {
      opacity: 1;
    }

    .gradio-container .block:hover,
    .gradio-container .panel:hover {
      border-color: var(--border-hover) !important;
      transform: translateY(-4px);
      box-shadow:
        0 0 0 1px rgba(255,255,255,0.10),
        0 8px 40px rgba(0,0,0,0.5),
        0 0 80px rgba(94,106,210,0.10);
    }

    .gradio-container .prose,
    .gradio-container .prose p,
    .gradio-container label {
      color: var(--foreground-muted) !important;
    }

    .gradio-container .prose h1,
    .gradio-container .prose h2,
    .gradio-container .prose h3 {
      color: var(--foreground) !important;
    }

    .gradio-container button.primary {
      background: var(--accent) !important;
      color: #fff !important;
      border: 0 !important;
      border-radius: 10px !important;
      font-weight: 600 !important;
      box-shadow:
        0 0 0 1px rgba(94,106,210,0.5),
        0 4px 12px rgba(94,106,210,0.3),
        inset 0 1px 0 0 rgba(255,255,255,0.2) !important;
      transition: all .22s cubic-bezier(.16,1,.3,1) !important;
    }
    .gradio-container button.primary:hover {
      background: var(--accent-bright) !important;
      transform: translateY(-2px) !important;
      box-shadow:
        0 0 0 1px rgba(94,106,210,0.62),
        0 8px 18px rgba(94,106,210,0.35),
        0 0 34px rgba(94,106,210,0.25),
        inset 0 1px 0 0 rgba(255,255,255,0.25) !important;
    }
    .gradio-container button.primary:active {
      transform: scale(0.98) !important;
    }

    .gradio-container input,
    .gradio-container textarea,
    .gradio-container select {
      background: #0f1014 !important;
      color: var(--foreground) !important;
      border: 1px solid rgba(255,255,255,0.10) !important;
      border-radius: 10px !important;
    }
    .gradio-container input:focus,
    .gradio-container textarea:focus,
    .gradio-container select:focus {
      border-color: rgba(94,106,210,0.65) !important;
      box-shadow: 0 0 0 2px rgba(94,106,210,0.28) !important;
    }

    .hero {
      padding: 1.2rem 0.2rem 0.8rem;
      transform: translateY(var(--hero-y, 0px)) scale(var(--hero-scale, 1));
      opacity: var(--hero-opacity, 1);
      transition: transform .1s linear, opacity .1s linear;
    }
    .hero-kicker {
      font-size: .72rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--foreground-subtle);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      margin-bottom: .8rem;
    }
    .hero-title {
      font-size: clamp(2rem, 5vw, 4.2rem);
      margin: 0 0 .6rem;
      line-height: 1.05;
      font-weight: 600;
      letter-spacing: -0.03em;
      background: linear-gradient(to bottom, #fff 0%, rgba(255,255,255,0.94) 50%, rgba(255,255,255,0.70) 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }
    .hero-title-accent {
      background: linear-gradient(90deg, #5E6AD2, #95a0ff, #5E6AD2);
      background-size: 200% 100%;
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      animation: shimmer 6s linear infinite;
    }
    .hero-sub {
      max-width: 840px;
      line-height: 1.7;
      color: var(--foreground-muted);
      margin: 0 0 1rem;
      font-size: clamp(0.95rem, 2vw, 1.1rem);
    }
    .pill {
      display: inline-block;
      margin-right: .5rem;
      margin-bottom: .5rem;
      padding: .36rem .8rem;
      border-radius: 999px;
      border: 1px solid rgba(94,106,210,0.30);
      color: #cfd5ff;
      background: rgba(94,106,210,0.10);
      font-size: .72rem;
      letter-spacing: .08em;
      text-transform: uppercase;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }

    .mini-metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(120px, 1fr));
      gap: .75rem;
      margin-top: 1rem;
    }
    .metric-card {
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      padding: .72rem .8rem;
    }
    .metric-card b {
      display: block;
      color: var(--foreground);
      font-size: .95rem;
      margin-bottom: .2rem;
    }
    .metric-card span {
      color: var(--foreground-muted);
      font-size: .78rem;
      letter-spacing: .03em;
      text-transform: uppercase;
    }
    .section-divider {
      height: 1px;
      margin: 1rem 0 1.2rem;
      background: linear-gradient(to right, transparent, rgba(255,255,255,0.12), transparent);
    }

    @keyframes shimmer {
      0% { background-position: 0% 50%; }
      100% { background-position: 200% 50%; }
    }
    @keyframes floatAmbient {
      0%, 100% { transform: translateY(0) rotate(0deg); }
      50% { transform: translateY(-20px) rotate(1deg); }
    }

    @media (max-width: 768px) {
      .hero-title { font-size: 2.1rem; }
      .hero-sub { font-size: .95rem; }
      .mini-metrics { grid-template-columns: 1fr; }
    }

    @media (prefers-reduced-motion: reduce) {
      .gradio-container::before,
      .gradio-container::after,
      .hero-title-accent {
        animation: none !important;
      }
      .gradio-container .block,
      .gradio-container .panel,
      .gradio-container button.primary {
        transition: none !important;
      }
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
            <div class="hero">
              <div class="hero-kicker">Sentinel Log Shield / OpenEnv</div>
              <h1 class="hero-title">
                Redact logs with
                <span class="hero-title-accent">precision-grade intelligence</span>
              </h1>
              <p class="hero-sub">
                A premium OpenEnv demonstration for enterprise PII protection.
                Evaluate contextual redaction quality across increasing task difficulty with explainable reward metrics.
              </p>
              <span class="pill">Risk-aware</span>
              <span class="pill">Motion-tuned UI</span>
              <span class="pill">Judge-ready demo</span>
              <div class="mini-metrics">
                <div class="metric-card"><b>3 Tasks</b><span>Progressive benchmark</span></div>
                <div class="metric-card"><b>F1 Scored</b><span>Precision + recall tracked</span></div>
                <div class="metric-card"><b>Space Ready</b><span>Docker + HF deployment</span></div>
              </div>
            </div>
            """
        )

        gr.HTML('<div class="section-divider"></div>')

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
                    elem_classes=["spotlight-card"],
                )
                run_button = gr.Button(
                    "▶ Run Demo",
                    variant="primary",
                    size="lg",
                    elem_classes=["spotlight-card"],
                )

        # Output area
        with gr.Row():
            with gr.Column():
                output_display = gr.HTML(
                    value=format_output(
                        "Click 'Run Demo' to start...",
                        BLUE,
                    ),
                    elem_classes=["spotlight-card"],
                )

        # Status and score
        with gr.Row():
            with gr.Column():
                status_display = gr.HTML(
                    value="<p>Ready to run...</p>",
                    elem_classes=["spotlight-card"],
                )
            with gr.Column():
                score_display = gr.Number(
                    label="📈 Episode Score",
                    value=0.0,
                    interactive=False,
                    elem_classes=["spotlight-card"],
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
            ,
            elem_classes=["spotlight-card"]
        )

        gr.HTML(
            """
            <script>
              (() => {
                const applySpotlight = () => {
                  document.querySelectorAll('.spotlight-card').forEach((el) => {
                    if (el.dataset.spotlightBound === '1') return;
                    el.dataset.spotlightBound = '1';
                    el.addEventListener('mousemove', (e) => {
                      const rect = el.getBoundingClientRect();
                      el.style.setProperty('--spot-x', `${e.clientX - rect.left}px`);
                      el.style.setProperty('--spot-y', `${e.clientY - rect.top}px`);
                    });
                  });
                };
                const applyParallax = () => {
                  const hero = document.querySelector('.hero');
                  if (!hero) return;
                  const progress = Math.min(window.scrollY / 500, 1);
                  hero.style.setProperty('--hero-opacity', String(1 - (progress * 0.35)));
                  hero.style.setProperty('--hero-scale', String(1 - (progress * 0.05)));
                  hero.style.setProperty('--hero-y', `${progress * 44}px`);
                };
                applySpotlight();
                applyParallax();
                document.addEventListener('scroll', applyParallax, { passive: true });
                setInterval(applySpotlight, 1200);
              })();
            </script>
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
