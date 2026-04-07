#!/usr/bin/env python3
"""
inference.py — Fallback Baseline Agent (No OpenAI API Required)

This script runs the Sentinel-Log-Shield environment WITHOUT OpenAI API calls.
It uses deterministic regex-based redaction instead.

For full LLM-powered baseline, set OPENAI_API_KEY and uncomment OpenAI calls.
"""

import os
import sys
import re
import json
from typing import Optional

# Environment variables
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN = os.getenv("HF_TOKEN", None)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)

# Attempt to import OpenAI client (optional - fallback if not available)
try:
    from openai import OpenAI
    HAS_OPENAI = OPENAI_API_KEY is not None
    if HAS_OPENAI:
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=API_BASE_URL)
    else:
        HAS_OPENAI = False
except ImportError:
    HAS_OPENAI = False

# Import environment
sys.path.insert(0, os.path.dirname(__file__))
from env import LogSanitizerEnvironment, Task
from models import RedactionAction

# ============================================================================
# REGEX-BASED REDACTION FUNCTIONS (Fallback - No API Required)
# ============================================================================

def redact_emails_and_ips(log: str) -> tuple[str, list[dict]]:
    """Regex-based email and IPv4 redaction (Task 1)."""
    redactions = []
    
    # Email pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    for match in re.finditer(email_pattern, log):
        redactions.append({
            'original': match.group(),
            'redacted': '[EMAIL_REDACTED]',
            'type': 'email'
        })
        log = log.replace(match.group(), '[EMAIL_REDACTED]', 1)
    
    # IPv4 pattern
    ipv4_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    for match in re.finditer(ipv4_pattern, log):
        if match.group() not in ['255.255.255.255']:  # Skip broadcast
            redactions.append({
                'original': match.group(),
                'redacted': '[IP_REDACTED]',
                'type': 'ipv4'
            })
            log = log.replace(match.group(), '[IP_REDACTED]', 1)
    
    return log, redactions

def redact_usernames(log: str) -> tuple[str, list[dict]]:
    """Regex-based username redaction (Task 2)."""
    redactions = []
    
    # Patterns for usernames in logs
    patterns = [
        r'user[_=:\s]+([A-Za-z0-9_-]+)',
        r'username[_=:\s]+([A-Za-z0-9_-]+)',
        r'logged in as\s+([A-Za-z0-9_-]+)',
        r'User:\s*([A-Za-z0-9_-]+)'
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, log, re.IGNORECASE):
            username = match.group(1)
            redactions.append({
                'original': username,
                'redacted': '[USER_REDACTED]',
                'type': 'username'
            })
            log = log.replace(username, '[USER_REDACTED]')
    
    return log, redactions

def redact_auth_tokens(log: str) -> tuple[str, list[dict]]:
    """Regex-based auth token redaction (Task 3)."""
    redactions = []
    
    # Patterns for tokens
    patterns = [
        r'(?:token|auth|key)[_=:\s]+([A-Za-z0-9\-_.]{20,})',
        r'(?:Bearer|JWT|Token)\s+([A-Za-z0-9\-_.]+)',
        r'(?:api_key|apikey)[_=:\s]+([A-Za-z0-9\-_.]+)',
        r'(?:sk-[A-Za-z0-9]{20,})',  # OpenAI-like tokens
        r'(?:hf_[A-Za-z0-9]{20,})',  # HF-like tokens
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, log, re.IGNORECASE):
            token = match.group(1) if '(' in pattern else match.group(0)
            if len(token) > 5:  # Only redact substantial tokens
                redactions.append({
                    'original': token[:10] + '...',  # Show partial for context
                    'redacted': '[TOKEN_REDACTED]',
                    'type': 'token'
                })
                log = log.replace(token, '[TOKEN_REDACTED]')
    
    return log, redactions

# ============================================================================
# ENVIRONMENT INTERACTION
# ============================================================================

def run_episode(num_steps: int = 3) -> dict:
    """Run a complete episode with fallback regex-based redaction."""
    
    env = LogSanitizerEnvironment()
    observation = env.reset()
    
    step_num = 0
    done = False
    total_reward = 0.0
    rewards = []
    
    print(f"[START] task={observation.task.value} env=sentinel-log-shield model={MODEL_NAME}")
    
    while not done and step_num < num_steps:
        step_num += 1
        
        # Determine which redaction function to use based on task
        if observation.task == Task.TASK_1:
            redacted_log, redactions = redact_emails_and_ips(observation.raw_log)
        elif observation.task == Task.TASK_2:
            redacted_log, redactions = redact_usernames(observation.raw_log)
        elif observation.task == Task.TASK_3:
            redacted_log, redactions = redact_auth_tokens(observation.raw_log)
        else:
            redacted_log = observation.raw_log
            redactions = []
        
        # Create action
        action = RedactionAction(
            log_id=observation.log_id,
            redactions=[r['original'] for r in redactions],
            redacted_log=redacted_log,
            confidence=0.85 if redactions else 0.7
        )
        
        # Step environment
        observation, reward, done = env.step(action)
        
        total_reward += reward.total_reward
        rewards.append(reward.total_reward)
        
        action_summary = f"redacted_{len(redactions)}_items"
        print(f"[STEP] step={step_num} action={action_summary} reward={reward.total_reward:.2f} done={'true' if done else 'false'} error=null")
    
    # Final result
    final_score = sum(rewards) / len(rewards) if rewards else 0.0
    success = final_score >= 0.70
    rewards_str = ','.join([f"{r:.2f}" for r in rewards])
    
    print(f"[END] success={'true' if success else 'false'} steps={step_num} score={final_score:.2f} rewards={rewards_str}")
    
    return {
        'task': observation.task.value,
        'steps': step_num,
        'score': final_score,
        'success': success,
        'rewards': rewards
    }

def main():
    """Main entry point - run multiple episodes."""
    print(f"Sentinel-Log-Shield Inference (Fallback Mode)")
    print(f"Model: {MODEL_NAME}")
    print(f"OpenAI Available: {HAS_OPENAI}")
    print("")
    
    try:
        # Run 3 episodes (one per task)
        for i in range(3):
            if i > 0:
                print("")  # Blank line between episodes
            result = run_episode(num_steps=3)
            
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
