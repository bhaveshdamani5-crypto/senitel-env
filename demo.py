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

    with gr.Blocks(
        title="Sentinel-Log-Shield: OpenEnv Demo",
        theme=gr.themes.Soft(),
    ) as demo:

        # Header
        gr.Markdown(
            """
# 🔐 Sentinel-Log-Shield: Enterprise PII Redaction

**OpenEnv Framework Implementation for Intelligent Log Sanitization**

---

## 🎯 What is this?

An AI agent that automatically detects and redacts sensitive information (PII) from system logs:
- **Task 1 (Easy)**: Email addresses & IPv4 addresses  
- **Task 2 (Medium)**: Usernames in conversational logs
- **Task 3 (Hard)**: API keys, tokens, and secrets in stack traces

The agent learns to preserve log utility while removing sensitive data.

---

## 🚀 Quick Demo

Select a task and watch the agent work in real-time:
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
                    label="📊 Episode Output",
                    value=format_output(
                        "Click 'Run Demo' to start...",
                        BLUE,
                    ),
                )

        # Status and score
        with gr.Row():
            with gr.Column():
                status_display = gr.HTML(
                    label="🎯 Result",
                    value="<p>Ready to run...</p>",
                )
            with gr.Column():
                score_display = gr.Number(
                    label="📈 Episode Score",
                    value=0.0,
                    interactive=False,
                )

        # Examples
        gr.Markdown(
            """
---

## 📚 Examples

### Task 1 Input (Email & IPv4)
```
User alice@company.com logged in from 192.168.1.1 at 14:30
```

### Task 2 Input (Username)
```
Error: User 'Bob' failed login attempt after 3 tries
```

### Task 3 Input (Secrets)
```
Traceback: sk_live_1234567890abcdef in auth.py line 42
```

---

## 🏆 Scoring Explained

| Score | Meaning |
|-------|---------|
| **1.0** | Perfect redaction (100% accuracy) |
| **0.8** | Excellent (90%+ recall, 80%+ precision) |
| **0.5** | Good (60%+ F1-score) |
| **0.2** | Partial (some redactions found) |
| **-1.0** | Critical failure (missed secrets in Task 3) |

---

## 🔧 How It Works

1️⃣ **Environment Reset** → Randomly selects task and log  
2️⃣ **Agent Infers** → Uses regex patterns (no API needed)  
3️⃣ **Action Taken** → Detects and redacts PII  
4️⃣ **Step Evaluates** → Computes F1-score and reward  
5️⃣ **Episode Ends** → Shows final score

---

## 🎓 More Information

- **GitHub Repository**: https://github.com/bhaveshdamani5-crypto/senitel-env
- **README**: Complete documentation with architecture diagrams
- **OpenEnv Framework**: https://github.com/openai/openenv

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

    return demo


if __name__ == "__main__":
    demo = create_demo()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        share=False,
    )
