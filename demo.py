"""
demo.py — Standalone demonstration of the Sentinel-Log-Shield v2 environment.

Runs a complete investigation episode and displays step-by-step results.
Can be used to validate the environment works correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from env import SentinelEnvironment
from models import AgentAction, ActionType, Difficulty
from grader import InvestigationGrader
import re
import base64


def _safe_text(s: str) -> str:
    # Windows consoles may be non-UTF8; avoid crashing on emojis in feedback strings.
    try:
        return s.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
    except Exception:
        return s.encode("ascii", errors="replace").decode("ascii")


def extract_pii_from_text(logs):
    """Simple PII extraction for demo purposes."""
    found = []
    seen = set()
    for log in logs:
        # Email pattern
        for m in re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', log):
            if m.group() not in seen:
                found.append({"original": m.group(), "type": "email"})
                seen.add(m.group())
        
        # IP addresses (basic check to avoid false positives from example IPs)
        for m in re.finditer(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', log):
            ip = m.group()
            if ip not in seen and ip not in ["255.255.255.255", "0.0.0.0", "127.0.0.1"]:
                found.append({"original": ip, "type": "ip"})
                seen.add(ip)
        
        # Usernames in structured text
        for m in re.finditer(r"User\s*['\"]([A-Za-z][A-Za-z0-9_-]*)['\"]", log, re.IGNORECASE):
            if m.group(1) not in seen:
                found.append({"original": m.group(1), "type": "username"})
                seen.add(m.group(1))
        
        for m in re.finditer(r"user=([A-Za-z][A-Za-z0-9_-]+)", log, re.IGNORECASE):
            if m.group(1) not in seen:
                found.append({"original": m.group(1), "type": "username"})
                seen.add(m.group(1))
        
        # Phone numbers: multiple patterns
        # Pattern 1: +1-XXX-XXX-XXXX
        for m in re.finditer(r"\+1-\d{3}-\d{3}-\d{4}", log):
            if m.group() not in seen:
                found.append({"original": m.group(), "type": "phone"})
                seen.add(m.group())
        
        # Pattern 2: +91-XXXXX-XXXXX (India)
        for m in re.finditer(r"\+91-\d{5}-\d{5}", log):
            if m.group() not in seen:
                found.append({"original": m.group(), "type": "phone"})
                seen.add(m.group())
        
        # Pattern 3: +44-20-XXXX-XXXX (UK)
        for m in re.finditer(r"\+44-20-\d{4}-\d{4}", log):
            if m.group() not in seen:
                found.append({"original": m.group(), "type": "phone"})
                seen.add(m.group())
        
        # Pattern 4: +1-555-XXXX-XXX
        for m in re.finditer(r"\+1-555-\d{4}-\d{3}", log):
            if m.group() not in seen:
                found.append({"original": m.group(), "type": "phone"})
                seen.add(m.group())
        
        # Base64-encoded secrets
        for m in re.finditer(r"\bb64=([A-Za-z0-9+/=]{16,})\b", log):
            b64txt = m.group(1)
            try:
                decoded = base64.b64decode(b64txt).decode("utf-8", errors="ignore")
            except Exception:
                decoded = ""
            for sm in re.finditer(r"(?:token|key|secret|credential)\s*=\s*([^\s\"']{8,})", decoded, re.IGNORECASE):
                v = sm.group(1)
                if v not in seen and len(v) > 5:
                    found.append({"original": v, "type": "token"})
                    seen.add(v)
        
        # Token patterns (High-difficulty tokens)
        for pattern in [
            r'\bsk_(?:live|test)_[a-zA-Z0-9]{24,}\b', # Stripe
            r'\bghp_[a-zA-Z0-9]{36,}\b',              # GitHub
            r'\bhf_[a-zA-Z0-9]{34,}\b',              # HuggingFace
            r'\bAKIA[A-Z0-9]{16}\b',                  # AWS Access Key
            r'\bASIA[A-Z0-9]{16}\b',                  # AWS Session Key
            r'\beyJ[a-zA-Z0-9_-]{30,}\.eyJ[a-zA-Z0-9_-]{30,}\.[a-zA-Z0-9_-]{30,}\b', # JWT
            r'\bapi[_-]?key[_-]?[a-zA-Z0-9]{20,}\b', # Generic API key
            r'xox[pb]-[0-9A-Za-z-]{10,}',             # Slack
            r'(?:key|token|secret|credential|password|pwd|auth)\s*[:=]\s*["\']?([a-zA-Z0-9._%+-]{12,})["\']?', # Assignment-based
            r'\b[A-Za-f0-9]{32}\b',                  # MD5/Entropy
            r'\b[A-Za-f0-9]{40}\b',                  # SHA1/Entropy
        ]:
            for m in re.finditer(pattern, log, re.IGNORECASE):
                v = m.group(1) if m.lastindex else m.group(0)
                if v not in seen and len(v) > 5:
                    found.append({"original": v, "type": "token"})
                    seen.add(v)
    
    return found


def run_demo(difficulty="medium"):
    """Run a demonstration episode showing the investigation flow."""
    print(f"\n{'=' * 60}")
    print(f"  SENTINEL-LOG-SHIELD v2 DEMO - {difficulty.upper()}")
    print(f"{'=' * 60}\n")

    env = SentinelEnvironment()
    reset = env.reset(difficulty=difficulty)
    obs = reset.observation

    print(f"Scenario: {obs.total_pii_to_find} PII items hidden across investigation layers")
    print(f"Budget: {obs.steps_remaining} steps")
    print(f"Initial visible logs ({len(obs.visible_logs)}):")
    for log in obs.visible_logs:
        print(f"   {log}")
    print()

    # Step 1: SCAN
    print("--- Step 1: SCAN ---")
    result = env.step(AgentAction(action_type=ActionType.SCAN))
    obs = result.observation
    print(f"  Discovered {len(obs.discovered_entities)} entities: {obs.discovered_entities}")
    print(f"  Investigation targets: {obs.investigation_targets}")
    print(f"  Reward: {result.reward.total_reward:.3f}")
    print(f"  Steps remaining: {obs.steps_remaining}")
    print()

    # Step 2+: INVESTIGATE
    step = 2
    investigated = set()
    while obs.steps_remaining > 2 and obs.investigation_targets:
        target = obs.investigation_targets[0]
        if target in investigated:
            break
        investigated.add(target)
        print(f"--- Step {step}: INVESTIGATE '{target}' ---")
        result = env.step(AgentAction(action_type=ActionType.INVESTIGATE, target_entity=target))
        obs = result.observation
        print(f"  Discovered entities: {len(obs.discovered_entities)}")
        print(f"  New visible logs: {len(obs.visible_logs)} total")
        print(f"  Reward: {result.reward.total_reward:.3f} | {result.reward.feedback}")
        print(f"  Steps remaining: {obs.steps_remaining}")
        print()
        step += 1

    # REDACT
    if obs.steps_remaining > 1:
        pii_items = extract_pii_from_text(obs.visible_logs)
        # Also add from discovered entities
        seen = {p["original"] for p in pii_items}
        for e in obs.discovered_entities:
            if e not in seen:
                pii_items.append({"original": e, "type": "unknown"})
                seen.add(e)

        print(f"--- Step {step}: REDACT {len(pii_items)} items ---")
        result = env.step(AgentAction(action_type=ActionType.REDACT, redactions=pii_items))
        obs = result.observation
        print(f"  Coverage: {obs.pii_found_count}/{obs.total_pii_to_find}")
        print(f"  Reward: {result.reward.total_reward:.3f} | {result.reward.feedback}")
        print(f"  Steps remaining: {obs.steps_remaining}")
        print()
        step += 1

    # SUBMIT
    print(f"--- Step {step}: SUBMIT ---")
    result = env.step(AgentAction(action_type=ActionType.SUBMIT))
    obs = result.observation
    print("  FINAL RESULTS:")
    for k, v in result.reward.metrics.items():
        print(f"     {k}: {v}")
    print(f"  Total Reward: {result.reward.total_reward:.3f}")
    print(f"  Feedback: {_safe_text(result.reward.feedback)}")
    print()

    return result


if __name__ == "__main__":
    for diff in ["easy", "medium", "hard"]:
        run_demo(diff)
