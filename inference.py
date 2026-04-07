#!/usr/bin/env python3
"""
inference.py — Sentinel-Log-Shield Baseline Agent (OpenAI Client + Fallback)

COMPLIANCE REQUIREMENT: Participants must use OpenAI Client for all LLM calls.

This script implements the primary inference approach:
1. PRIMARY: OpenAI Client (gpt-4o-mini) for LLM-based PII redaction
2. FALLBACK: Regex-based patterns if OpenAI API unavailable

REQUIRED ENVIRONMENT VARIABLES:
  - OPENAI_API_KEY: Your OpenAI API key (sk-...)
  - API_BASE_URL: OpenAI API endpoint (default: https://api.openai.com/v1)
  - MODEL_NAME: Model to use (default: gpt-4o-mini)
  - HF_TOKEN: HuggingFace token (optional)

DEPLOYMENT: Set these in HF Space Settings → Repository Secrets
"""

import os
import sys
import re
import json
from typing import Optional

# ============================================================================
# ENVIRONMENT VARIABLES (Required for OpenAI Client)
# ============================================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN = os.getenv("HF_TOKEN", None)

# Validate critical variable
if not OPENAI_API_KEY:
    print("[WARNING] OPENAI_API_KEY not set. Install via: export OPENAI_API_KEY='sk-...'")
    print("[WARNING] Falling back to regex-based redaction (reduced accuracy)")
    FALLBACK_MODE = True
else:
    FALLBACK_MODE = False

# ============================================================================
# OPENAI CLIENT INITIALIZATION (Primary Approach)
# ============================================================================

client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=API_BASE_URL)
        print(f"[INFO] OpenAI Client initialized: {MODEL_NAME}")
    except Exception as e:
        print(f"[WARNING] Failed to initialize OpenAI Client: {e}")
        print(f"[WARNING] Falling back to regex-based redaction")
        FALLBACK_MODE = True

# Import environment
sys.path.insert(0, os.path.dirname(__file__))
from env import LogSanitizerEnvironment, Task
from models import RedactionAction

# ============================================================================
# PRIMARY: LLM-BASED REDACTION (OpenAI Client)
# ============================================================================

def llm_redact_emails_and_ips(log: str) -> tuple[str, list[dict]]:
    """LLM-based email and IPv4 redaction using OpenAI Client."""
    if not client:
        raise ValueError("OpenAI Client not available")
    
    prompt = f"""Analyze this log and identify ALL email addresses and IPv4 addresses.

Log:
{log}

Return a JSON object with:
{{
  "redactions": [
    {{"original": "email@domain.com", "type": "email"}},
    {{"original": "192.168.1.1", "type": "ipv4"}}
  ],
  "redacted_log": "User [EMAIL_REDACTED] from [IP_REDACTED] logged in"
}}

IMPORTANT:
- Redact with exact placeholder: [EMAIL_REDACTED] for emails, [IP_REDACTED] for IPs
- Do NOT redact usernames or other PII in Task 1
- Extract EXACTLY as they appear in the original log
- Return valid JSON only, no markdown or extra text"""

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    result_text = response.content[0].text
    try:
        result = json.loads(result_text)
        return result.get('redacted_log', log), result.get('redactions', [])
    except json.JSONDecodeError:
        # Fallback to regex if LLM response invalid
        return regex_redact_emails_and_ips(log)

def llm_redact_usernames(log: str) -> tuple[str, list[dict]]:
    """LLM-based username extraction using OpenAI Client."""
    if not client:
        raise ValueError("OpenAI Client not available")
    
    prompt = f"""Analyze this log and extract usernames mentioned in natural language context.

Log:
{log}

Return a JSON object with:
{{
  "redactions": [
    {{"original": "username", "type": "username"}}
  ],
  "redacted_log": "User [USER_REDACTED] failed login"
}}

IMPORTANT:
- Find usernames in conversational context like "User 'Alice' failed login"
- Redact with: [USER_REDACTED]
- Do NOT redact system variables or command names
- Extract EXACTLY as they appear
- Return valid JSON only"""

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    result_text = response.content[0].text
    try:
        result = json.loads(result_text)
        return result.get('redacted_log', log), result.get('redactions', [])
    except json.JSONDecodeError:
        return regex_redact_usernames(log)

def llm_redact_auth_tokens(log: str) -> tuple[str, list[dict]]:
    """LLM-based high-entropy secret detection using OpenAI Client."""
    if not client:
        raise ValueError("OpenAI Client not available")
    
    prompt = f"""Analyze this log for high-entropy secrets (API keys, tokens, credentials).

Log:
{log}

Return a JSON object with:
{{
  "redactions": [
    {{"original": "secret_partial", "type": "token"}}
  ],
  "redacted_log": "Auth token [TOKEN_REDACTED] sent to server"
}}

IMPORTANT:
- Find: API keys (sk-*, hf_*), JWT tokens, auth tokens, credentials
- Find: Private keys, session tokens, Bearer tokens
- Redact with: [TOKEN_REDACTED]
- CRITICAL: Do NOT miss secrets - this is high-risk data
- Extract EXACTLY as they appear (show first 10 chars only for security)
- Return valid JSON only"""

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    result_text = response.content[0].text
    try:
        result = json.loads(result_text)
        return result.get('redacted_log', log), result.get('redactions', [])
    except json.JSONDecodeError:
        return regex_redact_auth_tokens(log)

# ============================================================================
# FALLBACK: REGEX-BASED REDACTION (No API Required)
# ============================================================================

def regex_redact_emails_and_ips(log: str) -> tuple[str, list[dict]]:
    """Regex-based email and IPv4 redaction (fallback only)."""
    redactions = []
    
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    for match in re.finditer(email_pattern, log):
        redactions.append({
            'original': match.group(),
            'type': 'email'
        })
        log = log.replace(match.group(), '[EMAIL_REDACTED]', 1)
    
    ipv4_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    for match in re.finditer(ipv4_pattern, log):
        if match.group() not in ['255.255.255.255']:
            redactions.append({
                'original': match.group(),
                'type': 'ipv4'
            })
            log = log.replace(match.group(), '[IP_REDACTED]', 1)
    
    return log, redactions

def regex_redact_usernames(log: str) -> tuple[str, list[dict]]:
    """Regex-based username redaction (fallback only)."""
    redactions = []
    
    patterns = [
        r'user[_=:\s]+([A-Za-z0-9_-]+)',
        r'username[_=:\s]+([A-Za-z0-9_-]+)',
        r'logged in as\s+([A-Za-z0-9_-]+)',
        r"User\s*['\"]([A-Za-z0-9_-]+)['\"]",
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, log, re.IGNORECASE):
            username = match.group(1)
            if username:
                redactions.append({
                    'original': username,
                    'type': 'username'
                })
                log = log.replace(username, '[USER_REDACTED]')
    
    return log, redactions

def regex_redact_auth_tokens(log: str) -> tuple[str, list[dict]]:
    """Regex-based auth token redaction (fallback only)."""
    redactions = []
    
    patterns = [
        r'(?:token|auth|secret|key)[_=:\s]+([A-Za-z0-9\-_.]{20,})',
        r'(?:Bearer|JWT|Token)\s+([A-Za-z0-9\-_.]+)',
        r'sk-[A-Za-z0-9]{20,}',
        r'hf_[A-Za-z0-9]{20,}',
        r'ghp_[A-Za-z0-9]{20,}',
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, log, re.IGNORECASE):
            token = match.group(1) if '(' in pattern else match.group(0)
            if len(token) > 5:
                redactions.append({
                    'original': token[:10] + '...',
                    'type': 'token'
                })
                log = log.replace(token, '[TOKEN_REDACTED]')
    
    return log, redactions

# ============================================================================
# TASK ROUTING: LLM first, then fallback
# ============================================================================

def redact_task_1(log: str) -> tuple[str, list[dict]]:
    """Task 1: Email & IPv4 redaction."""
    if client and not FALLBACK_MODE:
        try:
            return llm_redact_emails_and_ips(log)
        except Exception as e:
            print(f"[WARNING] LLM Task 1 failed: {e}, using regex fallback")
            return regex_redact_emails_and_ips(log)
    return regex_redact_emails_and_ips(log)

def redact_task_2(log: str) -> tuple[str, list[dict]]:
    """Task 2: Username extraction."""
    if client and not FALLBACK_MODE:
        try:
            return llm_redact_usernames(log)
        except Exception as e:
            print(f"[WARNING] LLM Task 2 failed: {e}, using regex fallback")
            return regex_redact_usernames(log)
    return regex_redact_usernames(log)

def redact_task_3(log: str) -> tuple[str, list[dict]]:
    """Task 3: Auth token detection."""
    if client and not FALLBACK_MODE:
        try:
            return llm_redact_auth_tokens(log)
        except Exception as e:
            print(f"[WARNING] LLM Task 3 failed: {e}, using regex fallback")
            return regex_redact_auth_tokens(log)
    return regex_redact_auth_tokens(log)

# ============================================================================
# ENVIRONMENT INTERACTION
# ============================================================================

def run_episode(num_steps: int = 3) -> dict:
    """Run a complete episode with OpenAI Client (primary) + fallback."""
    
    env = LogSanitizerEnvironment()
    observation = env.reset()
    
    step_num = 0
    done = False
    total_reward = 0.0
    rewards = []
    
    # Emit START in exact format
    print(f"[START] task={observation.task.value} env=sentinel-log-shield model={MODEL_NAME}")
    
    while not done and step_num < num_steps:
        step_num += 1
        
        # Task-specific redaction
        if observation.task == Task.TASK_1:
            redacted_log, redactions = redact_task_1(observation.raw_log)
        elif observation.task == Task.TASK_2:
            redacted_log, redactions = redact_task_2(observation.raw_log)
        elif observation.task == Task.TASK_3:
            redacted_log, redactions = redact_task_3(observation.raw_log)
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
    
    # Final result - emit END in exact format
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
    """Main entry point - run 3 episodes (one per task)."""
    print("=" * 70)
    print("Sentinel-Log-Shield: OpenEnv Baseline Agent")
    print("=" * 70)
    print(f"Model: {MODEL_NAME}")
    print(f"API Base: {API_BASE_URL}")
    print(f"OpenAI Client Ready: {bool(client and not FALLBACK_MODE)}")
    print(f"Fallback Mode: {FALLBACK_MODE}")
    print("=" * 70)
    print()
    
    try:
        # Run 3 episodes (one per task)
        for i in range(3):
            if i > 0:
                print()  # Blank line between episodes
            result = run_episode(num_steps=3)
            
    except Exception as e:
        print(f"[ERROR] Inference failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

    
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
