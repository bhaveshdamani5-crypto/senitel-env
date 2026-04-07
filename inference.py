#!/usr/bin/env python3
"""
inference.py — Sentinel-Log-Shield v2 Baseline Agent

Demonstrates a multi-phase investigation strategy:
  Phase 1: SCAN visible logs to discover surface-level PII
  Phase 2: INVESTIGATE entities to reveal deeper logs and secrets
  Phase 3: REDACT all discovered PII
  Phase 4: SUBMIT findings

Supports two modes:
  1. PRIMARY: LLM-guided investigation (OpenAI client with HF_TOKEN)
  2. FALLBACK: Heuristic investigation strategy (regex + priority rules)

REQUIRED ENVIRONMENT VARIABLES (Hackathon Setup):
  - HF_TOKEN: Hugging Face token for OpenAI-compatible endpoint
  - API_BASE_URL: OpenAI API endpoint (default: HF inference)
  - MODEL_NAME: Model to use (default: meta-llama/Llama-2-70b-chat-hf)
"""

import os
import sys
import re
import json
from typing import Optional, List, Dict, Set

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

HF_TOKEN = os.getenv("HF_TOKEN", None)
API_BASE_URL = os.getenv("API_BASE_URL", "https://api-inference.huggingface.co/openai/")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-2-70b-chat-hf")

if not HF_TOKEN:
    print("[WARNING] HF_TOKEN not set. Using heuristic fallback strategy.")
    FALLBACK_MODE = True
else:
    FALLBACK_MODE = False

# OpenAI client initialization
client = None
if HF_TOKEN:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=HF_TOKEN, base_url=API_BASE_URL)
        print(f"[INFO] OpenAI Client initialized | Model: {MODEL_NAME}")
    except Exception as e:
        print(f"[WARNING] Failed to initialize OpenAI Client: {e}")
        FALLBACK_MODE = True

# Import environment
sys.path.insert(0, os.path.dirname(__file__))
from env import SentinelEnvironment
from models import AgentAction, ActionType, Difficulty


# ============================================================================
# PII EXTRACTION (Agent's own detection — different from grader)
# ============================================================================

def extract_pii_from_logs(logs: List[str]) -> List[Dict[str, str]]:
    """
    Extract PII items from log text using regex patterns.

    NOTE: These patterns are intentionally DIFFERENT from the grader's
    ground truth. The agent must discover PII through investigation,
    not just regex matching.
    """
    found = []
    seen = set()

    for log in logs:
        # Emails
        for match in re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', log):
            val = match.group()
            if val not in seen:
                found.append({"original": val, "type": "email"})
                seen.add(val)

        # IPv4 addresses
        for match in re.finditer(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', log):
            val = match.group()
            if val not in seen and val != "255.255.255.255":
                found.append({"original": val, "type": "ip"})
                seen.add(val)

        # Usernames in quotes: User 'Name' or user=Name
        for match in re.finditer(r"User\s*['\"]([A-Za-z][A-Za-z0-9_-]*)['\"]", log, re.IGNORECASE):
            val = match.group(1)
            if val not in seen and len(val) > 1:
                found.append({"original": val, "type": "username"})
                seen.add(val)

        # Usernames from user= patterns
        for match in re.finditer(r"user=([A-Za-z][A-Za-z0-9_-]+)", log, re.IGNORECASE):
            val = match.group(1)
            if val not in seen and len(val) > 1:
                found.append({"original": val, "type": "username"})
                seen.add(val)

        # Tokens and secrets: sk_*, ghp_*, hf_*, Bearer, AKIA*, key=, token=
        token_patterns = [
            (r'\bsk_[a-zA-Z0-9_]{10,}\b', "token"),
            (r'\bghp_[a-zA-Z0-9]{10,}\b', "token"),
            (r'\bhf_[a-zA-Z0-9]{10,}\b', "token"),
            (r'\bAKIA[A-Z0-9]{12,}\b', "token"),
            (r'\beyJ[a-zA-Z0-9_-]{20,}\b', "token"),
            (r'(?:key|token|secret|credential|password)\s*=\s*(\S{8,})', "token"),
            (r'Bearer\s+([A-Za-z0-9._-]{10,})', "token"),
            (r'Token\s+([A-Za-z0-9._-]{10,})', "token"),
            (r'api_key_[A-Za-z0-9]{10,}', "token"),
        ]
        for pattern, pii_type in token_patterns:
            for match in re.finditer(pattern, log, re.IGNORECASE):
                val = match.group(1) if match.lastindex else match.group(0)
                if val not in seen and len(val) > 5:
                    found.append({"original": val, "type": pii_type})
                    seen.add(val)

    return found


def prioritize_targets(entities: List[str], investigated: Set[str]) -> List[str]:
    """
    Prioritize investigation targets using heuristic rules.
    Tokens/secrets > usernames > IPs > emails (depth-first strategy).
    """
    def priority(entity: str) -> int:
        if any(prefix in entity.lower() for prefix in ["sk_", "ghp_", "hf_", "akia", "Bearer"]):
            return 0  # Highest priority: potential secrets
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", entity):
            return 2  # IPs often connect multiple users
        if "@" in entity:
            return 3  # Emails
        return 1  # Usernames connect to tokens

    available = [e for e in entities if e not in investigated]
    return sorted(available, key=priority)


# ============================================================================
# LLM-GUIDED INVESTIGATION (Primary mode)
# ============================================================================

def llm_choose_action(observation_summary: str) -> Optional[Dict]:
    """Use LLM to decide the next investigation action."""
    if not client:
        return None

    prompt = f"""You are a security analyst investigating a data breach.
Based on the current investigation state, choose the best next action.

Current State:
{observation_summary}

Available actions:
1. SCAN - Extract PII from visible logs (do this first)
2. INVESTIGATE <entity> - Deep-dive into an entity to reveal connected logs
3. REDACT <items> - Submit found PII for scoring
4. SUBMIT - End investigation

Return JSON: {{"action": "scan|investigate|redact|submit", "target": "entity_name_if_investigate", "reason": "brief reason"}}
Return ONLY valid JSON, no markdown."""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception:
        return None


# ============================================================================
# INVESTIGATION STRATEGY
# ============================================================================

def run_episode(difficulty: str = "medium", seed: Optional[int] = None) -> Dict:
    """
    Run a complete investigation episode.

    Strategy:
      1. SCAN to discover surface PII
      2. INVESTIGATE most promising entities (depth-first)
      3. SCAN again after investigation reveals new logs
      4. REDACT all discovered PII
      5. SUBMIT
    """
    env = SentinelEnvironment()
    reset_result = env.reset(difficulty=difficulty, seed=seed)
    obs = reset_result.observation

    print(f"[START] difficulty={difficulty} budget={obs.steps_remaining} "
          f"total_pii={obs.total_pii_to_find} env=sentinel-log-shield model={MODEL_NAME}")

    all_found_pii: List[Dict[str, str]] = []
    investigated: Set[str] = set()
    episode_rewards = []

    # Phase 1: Initial SCAN
    action = AgentAction(action_type=ActionType.SCAN)
    result = env.step(action)
    obs = result.observation
    episode_rewards.append(result.reward.total_reward)
    print(f"[STEP] step=1 action=SCAN discovered={len(obs.discovered_entities)} "
          f"reward={result.reward.total_reward:.3f} done=false")

    # Collect PII from scan results
    all_found_pii = extract_pii_from_logs(obs.visible_logs)

    step_num = 1

    # Phase 2: INVESTIGATE entities (depth-first)
    while obs.steps_remaining > 2 and obs.investigation_targets:
        step_num += 1
        targets = prioritize_targets(obs.investigation_targets, investigated)
        if not targets:
            break

        target = targets[0]
        investigated.add(target)

        # Try LLM-guided decision
        if client and not FALLBACK_MODE:
            llm_decision = llm_choose_action(
                f"Visible logs: {len(obs.visible_logs)}, "
                f"Discovered: {obs.discovered_entities}, "
                f"Targets: {obs.investigation_targets}, "
                f"Steps remaining: {obs.steps_remaining}, "
                f"PII found so far: {obs.pii_found_count}/{obs.total_pii_to_find}"
            )
            if llm_decision and llm_decision.get("action") == "investigate":
                target = llm_decision.get("target", target)

        action = AgentAction(action_type=ActionType.INVESTIGATE, target_entity=target)
        result = env.step(action)
        obs = result.observation
        episode_rewards.append(result.reward.total_reward)

        # Re-extract PII from updated visible logs
        all_found_pii = extract_pii_from_logs(obs.visible_logs)

        print(f"[STEP] step={step_num} action=INVESTIGATE({target}) "
              f"discovered={len(obs.discovered_entities)} "
              f"reward={result.reward.total_reward:.3f} "
              f"done={'true' if result.terminated or result.truncated else 'false'}")

        if result.terminated or result.truncated:
            break

    # Phase 2b: Re-scan after investigation reveals new logs
    if obs.steps_remaining > 2 and not (result.terminated or result.truncated):
        step_num += 1
        action = AgentAction(action_type=ActionType.SCAN)
        result = env.step(action)
        obs = result.observation
        episode_rewards.append(result.reward.total_reward)
        all_found_pii = extract_pii_from_logs(obs.visible_logs)
        print(f"[STEP] step={step_num} action=SCAN(deep) "
              f"discovered={len(obs.discovered_entities)} "
              f"reward={result.reward.total_reward:.3f} done=false")

    # Phase 3: REDACT all discovered PII
    if obs.steps_remaining > 1 and all_found_pii and not (result.terminated or result.truncated):
        step_num += 1
        # Also include entities from observation that we might have missed with regex
        entity_redactions = [
            {"original": e, "type": _classify(e)}
            for e in obs.discovered_entities
        ]
        # Merge, dedup
        seen_originals = {r["original"] for r in all_found_pii}
        for er in entity_redactions:
            if er["original"] not in seen_originals:
                all_found_pii.append(er)
                seen_originals.add(er["original"])

        action = AgentAction(action_type=ActionType.REDACT, redactions=all_found_pii)
        result = env.step(action)
        obs = result.observation
        episode_rewards.append(result.reward.total_reward)
        print(f"[STEP] step={step_num} action=REDACT({len(all_found_pii)}_items) "
              f"coverage={obs.pii_found_count}/{obs.total_pii_to_find} "
              f"reward={result.reward.total_reward:.3f} done=false")

    # Phase 4: SUBMIT
    if not (result.terminated or result.truncated):
        step_num += 1
        action = AgentAction(action_type=ActionType.SUBMIT)
        result = env.step(action)
        obs = result.observation
        episode_rewards.append(result.reward.total_reward)

    # Final output
    total_score = sum(episode_rewards)
    success = result.reward.metrics.get("f1_score", 0) >= 0.70 if result.reward.metrics else False
    rewards_str = ",".join(f"{r:.3f}" for r in episode_rewards)

    print(f"[END] success={'true' if success else 'false'} steps={step_num} "
          f"score={total_score:.3f} f1={result.reward.metrics.get('f1_score', 0):.3f} "
          f"discovery={result.reward.metrics.get('discovery_rate', 0):.3f} "
          f"rewards={rewards_str}")

    return {
        "difficulty": difficulty,
        "steps": step_num,
        "total_score": total_score,
        "f1_score": result.reward.metrics.get("f1_score", 0),
        "discovery_rate": result.reward.metrics.get("discovery_rate", 0),
        "success": success,
        "rewards": episode_rewards,
        "metrics": result.reward.metrics,
    }


def _classify(entity: str) -> str:
    """Quick entity type classification for redaction."""
    if "@" in entity and "." in entity:
        return "email"
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", entity):
        return "ip"
    if any(prefix in entity.lower() for prefix in ["sk_", "ghp_", "hf_", "akia", "eyj", "api_key", "bearer"]):
        return "token"
    return "username"


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run investigation episodes across all difficulty levels."""
    print("=" * 70)
    print("Sentinel-Log-Shield v2: Interactive Investigation Agent")
    print("=" * 70)
    print(f"Model: {MODEL_NAME}")
    print(f"API Base: {API_BASE_URL}")
    print(f"LLM Mode: {bool(client and not FALLBACK_MODE)}")
    print(f"Fallback Mode: {FALLBACK_MODE}")
    print("=" * 70)
    print()

    difficulties = ["easy", "medium", "hard"]
    results = []

    for i, diff in enumerate(difficulties):
        if i > 0:
            print()
        print(f"{'--' * 30}")
        print(f"  Episode {i + 1}: {diff.upper()} difficulty")
        print(f"{'--' * 30}")
        result = run_episode(difficulty=diff)
        results.append(result)

    # Summary table
    print()
    print("=" * 70)
    print("  INVESTIGATION SUMMARY")
    print("=" * 70)
    print(f"  {'Difficulty':<12} {'Steps':>6} {'F1':>8} {'Discovery':>10} {'Score':>8} {'Result':>8}")
    print(f"  {'--' * 28}")
    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        print(f"  {r['difficulty']:<12} {r['steps']:>6} {r['f1_score']:>8.3f} "
              f"{r['discovery_rate']:>10.3f} {r['total_score']:>8.3f} {status:>8}")

    avg_f1 = sum(r["f1_score"] for r in results) / len(results)
    avg_score = sum(r["total_score"] for r in results) / len(results)
    print(f"  {'--' * 28}")
    print(f"  {'AVERAGE':<12} {'':>6} {avg_f1:>8.3f} {'':>10} {avg_score:>8.3f}")
    print()


if __name__ == "__main__":
    main()
