#!/usr/bin/env python3
"""
inference.py — Sentinel-Log-Shield v2 Baseline Agent

Demonstrates a multi-phase investigation strategy:
  Phase 1: SCAN visible logs to discover surface-level PII
  Phase 2: INVESTIGATE entities to reveal deeper logs and secrets
  Phase 3: REDACT all discovered PII (no regex fallback)
  Phase 4: SUBMIT findings

REQUIRED ENVIRONMENT VARIABLES (Hackathon Setup):
  - HF_TOKEN: Hugging Face token for OpenAI-compatible endpoint
  - API_BASE_URL: OpenAI API endpoint (default: HF inference)
  - MODEL_NAME: Model to use (default: meta-llama/Llama-2-70b-chat-hf)
"""

import os
import sys
import json
import time
import argparse
import statistics
from typing import Optional, List, Dict, Set, Any

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

HF_TOKEN = os.getenv("HF_TOKEN", None)
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/openai/")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-2-70b-chat-hf")

if not HF_TOKEN:
    raise RuntimeError(
        "HF_TOKEN is required for the baseline inference run. "
        "Set it as an environment variable (HF Spaces: add as a Secret)."
    )

# OpenAI client initialization
client = None
try:
    from openai import OpenAI
    client = OpenAI(api_key=HF_TOKEN, base_url=API_BASE_URL)
    print(f"[INFO] OpenAI Client initialized | Model: {MODEL_NAME}")
except Exception as e:
    raise RuntimeError(f"Failed to initialize OpenAI client: {e}") from e

# Import environment
sys.path.insert(0, os.path.dirname(__file__))
from env import SentinelEnvironment
from models import AgentAction, ActionType, Difficulty


def _is_ipv4(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit():
            return False
        n = int(p)
        if n < 0 or n > 255:
            return False
    return True


def _is_phone(s: str) -> bool:
    """Detect phone numbers in various formats."""
    if not isinstance(s, str):
        return False
    s = s.strip()
    
    # Pattern 1: +1-XXX-XXX-XXXX (US)
    if s.startswith("+1-"):
        parts = s.split("-")
        if len(parts) == 4:
            try:
                return (len(parts[1]) == 3 and parts[1].isdigit() and
                        len(parts[2]) == 3 and parts[2].isdigit() and
                        len(parts[3]) == 4 and parts[3].isdigit())
            except:
                return False
    
    # Pattern 2: +CC-XXXXX-XXXXX (India +91)
    if s.startswith("+91-"):
        parts = s.split("-")
        if len(parts) == 3:
            try:
                return (len(parts[1]) == 5 and parts[1].isdigit() and
                        len(parts[2]) == 5 and parts[2].isdigit())
            except:
                return False
    
    # Pattern 3: +44-20-XXXX-XXXX (UK)
    if s.startswith("+44-"):
        parts = s.split("-")
        if len(parts) == 4:
            try:
                return (parts[1] == "20" and  # London area code
                        len(parts[2]) == 4 and parts[2].isdigit() and
                        len(parts[3]) == 4 and parts[3].isdigit())
            except:
                return False
    
    # Pattern 4: +1-555-XXXX-XXX (toll-free variant)
    if s.startswith("+1-555-"):
        parts = s.split("-")
        if len(parts) == 4:
            try:
                return (len(parts[2]) == 4 and parts[2].isdigit() and
                        len(parts[3]) == 3 and parts[3].isdigit())
            except:
                return False
    
    return False


def _classify_entity(entity: str) -> str:
    if "@" in entity and "." in entity:
        return "email"
    if _is_phone(entity):
        return "phone"
    if _is_ipv4(entity):
        return "ip"
    low = entity.lower()
    if (
        low.startswith("sk_live_")
        or low.startswith("sk_test_")
        or low.startswith("ghp_")
        or low.startswith("hf_")
        or low.startswith("akia")
        or low.startswith("asia")
        or low.startswith("eyJ") # case-sensitive check often needed, but startswith matches prefix
        or low.startswith("api_key_")
        or low.startswith("xoxp-")
        or low.startswith("xoxb-")
        or low.startswith("bearer ")
        or len(entity) > 24 # Increased threshold for entropy-based tokens
    ):
        return "token"
    return "username"


def _strict_reward_value(value: float) -> float:
    return max(0.01, min(0.99, float(value)))

# ============================================================================
# LLM-GUIDED INVESTIGATION (Primary mode)
# ============================================================================

def _llm_choose_action(observation_summary: str, *, max_retries: int = 3, timeout: int = 30) -> Dict[str, Any]:
    """
    Use LLM to choose the next action. Strict JSON only.
    Retries on transient failures / JSON parse issues with exponential backoff.
    """
    prompt = f"""You are a security analyst investigating a data breach inside an RL environment.

Choose the best next action to maximize final score under a step budget.

Current State:
{observation_summary}

Valid actions (must be one of these):
- scan
- investigate (requires target)
- redact
- submit

Rules:
- Only choose investigate targets that appear in Targets.
- Prefer scan after new logs are revealed.
- Avoid investigating obvious decoys if they reveal nothing.
- Redact only after you have discovered enough entities.

Return ONLY strict JSON in this schema:
{{"action":"scan|investigate|redact|submit","target":null|string,"reason":"short"}}
"""

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                max_tokens=220,
                temperature=0.3,  # Lower temperature for more consistent outputs
                timeout=timeout,
                messages=[{"role": "user", "content": prompt}],
            )
            txt = (resp.choices[0].message.content or "").strip()
            
            # Try to extract JSON from response (LLM might add extra text)
            import re as re_module
            json_match = re_module.search(r'\{.*\}', txt, re_module.DOTALL)
            if json_match:
                txt = json_match.group(0)
            
            data = json.loads(txt)
            if not isinstance(data, dict):
                raise ValueError("LLM output is not a JSON object")
            action = data.get("action", "").lower()
            if action not in {"scan", "investigate", "redact", "submit"}:
                raise ValueError(f"Invalid action '{action}'")
            if action == "investigate" and not data.get("target"):
                raise ValueError("Investigate requires a target")
            data.setdefault("reason", "")
            if "target" not in data:
                data["target"] = None
            return data
        except Exception as e:
            last_err = e
            wait_time = 0.8 * (2 ** attempt)
            if attempt < max_retries - 1:
                time.sleep(wait_time)
    
    raise RuntimeError(f"LLM action selection failed after {max_retries} attempts: {last_err}") from last_err


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
    
    Gracefully handles API errors and returns fallback result.
    CRITICAL: [END] is guaranteed to print even on exception.
    """
    env = None
    step_num = 0
    episode_rewards = []
    result = None
    
    try:
        env = SentinelEnvironment()
        reset_result = env.reset(difficulty=difficulty, seed=seed)
        obs = reset_result.observation

        print(f"[START] task=investigation env=sentinel-log-shield model={MODEL_NAME}")

        all_found_pii: List[Dict[str, str]] = []
        investigated: Set[str] = set()

        # Always start with SCAN
        step_num += 1
        result = env.step(AgentAction(action_type=ActionType.SCAN))
        obs = result.observation
        episode_rewards.append(_strict_reward_value(result.reward.total_reward))
        print(f"[STEP] step={step_num} action=scan reward={_strict_reward_value(result.reward.total_reward):.2f} done=false error=null")

        while obs.steps_remaining > 0 and not (result.terminated or result.truncated):
            if obs.steps_remaining <= 1:
                step_num += 1
                result = env.step(AgentAction(action_type=ActionType.SUBMIT))
                obs = result.observation
                episode_rewards.append(_strict_reward_value(result.reward.total_reward))
                print(f"[STEP] step={step_num} action=submit reward={_strict_reward_value(result.reward.total_reward):.2f} done=true error=null")
                break

            all_found_pii = [{"original": e, "type": _classify_entity(e)} for e in obs.discovered_entities]
            summary = (
                f"Visible logs: {len(obs.visible_logs)}\n"
                f"Discovered: {obs.discovered_entities}\n"
                f"Targets: {obs.investigation_targets}\n"
                f"Steps remaining: {obs.steps_remaining}\n"
                f"Coverage so far: {obs.pii_found_count}/{obs.total_pii_to_find}\n"
            )
            
            try:
                decision = _llm_choose_action(summary)
                act = decision["action"]
            except Exception as e:
                print(f"[WARN] LLM error (will attempt SCAN instead): {e}")
                act = "scan"  # Fallback to SCAN on LLM failure

            if act == "scan":
                step_num += 1
                result = env.step(AgentAction(action_type=ActionType.SCAN))
                obs = result.observation
                episode_rewards.append(_strict_reward_value(result.reward.total_reward))
                print(f"[STEP] step={step_num} action=scan reward={_strict_reward_value(result.reward.total_reward):.2f} done=false error=null")
                continue

            if act == "investigate":
                target = decision.get("target")
                if not target or target not in obs.investigation_targets or target in investigated:
                    # If invalid/repeated target, fall back to SCAN (still LLM-only; we don't pick a target heuristically)
                    step_num += 1
                    result = env.step(AgentAction(action_type=ActionType.SCAN))
                    obs = result.observation
                    episode_rewards.append(_strict_reward_value(result.reward.total_reward))
                    print(f"[STEP] step={step_num} action=scan reward={_strict_reward_value(result.reward.total_reward):.2f} done=false error=null")
                    continue
                investigated.add(target)
                step_num += 1
                result = env.step(AgentAction(action_type=ActionType.INVESTIGATE, target_entity=target))
                obs = result.observation
                episode_rewards.append(_strict_reward_value(result.reward.total_reward))
                print(f"[STEP] step={step_num} action=investigate reward={_strict_reward_value(result.reward.total_reward):.2f} done=false error=null")
                continue

            if act == "redact":
                step_num += 1
                result = env.step(AgentAction(action_type=ActionType.REDACT, redactions=all_found_pii))
                obs = result.observation
                episode_rewards.append(_strict_reward_value(result.reward.total_reward))
                print(f"[STEP] step={step_num} action=redact reward={_strict_reward_value(result.reward.total_reward):.2f} done=false error=null")
                continue

            if act == "submit":
                step_num += 1
                result = env.step(AgentAction(action_type=ActionType.SUBMIT))
                obs = result.observation
                episode_rewards.append(_strict_reward_value(result.reward.total_reward))
                print(f"[STEP] step={step_num} action=submit reward={_strict_reward_value(result.reward.total_reward):.2f} done=true error=null")
                break

        # Final output
        success = result.reward.metrics.get("f1_score", 0) >= 0.70 if result.reward.metrics else False
        rewards_str = ",".join(f"{r:.2f}" for r in episode_rewards) if episode_rewards else ""

        raw_final_score = result.reward.metrics.get("total_score", 0.01)
        total_score = max(0.01, min(0.99, float(raw_final_score)))

        print(f"[END] task=investigation score={total_score:.2f} steps={step_num} success={'true' if success else 'false'} rewards={rewards_str}", flush=True)

        return {
            "difficulty": difficulty,
            "steps": step_num,
            "total_score": total_score,
            "f1_score": max(0.01, min(0.99, float(result.reward.metrics.get("f1_score", 0.01)))),
            "discovery_rate": max(0.01, min(0.99, float(result.reward.metrics.get("discovery_rate", 0.01)))),
            "success": success,
            "rewards": episode_rewards,
            "metrics": result.reward.metrics,
        }
    
    except Exception as e:
        # Ensure [END] is printed even on exception
        rewards_str = ",".join(f"{r:.2f}" for r in episode_rewards) if episode_rewards else ""
        fallback_score = max(0.01, min(0.99, float(sum(episode_rewards) / len(episode_rewards)))) if episode_rewards else 0.01
        print(f"[END] task=investigation score={fallback_score:.2f} steps={step_num} success=false rewards={rewards_str}", flush=True)
        print(f"[ERROR] Episode crashed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        # Return a default failed result so benchmarking can continue
        fallback_total = max(0.01, min(0.99, float(sum(episode_rewards)))) if episode_rewards else 0.01
        return {
            "difficulty": difficulty,
            "steps": step_num,
            "total_score": fallback_total,
            "f1_score": 0.01,
            "discovery_rate": 0.01,
            "success": False,
            "rewards": episode_rewards,
            "metrics": {},
            "error": str(e),
        }


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run investigation episodes across all difficulty levels."""
    try:
        parser = argparse.ArgumentParser(description="Sentinel-Log-Shield baseline (LLM-only).")
        parser.add_argument("--seeds", type=int, default=1, help="Number of seeds per difficulty for benchmarking.")
        parser.add_argument("--seed-start", type=int, default=0, help="Starting seed (inclusive).")
        args = parser.parse_args()

        print("=" * 70)
        print("Sentinel-Log-Shield v2: Interactive Investigation Agent")
        print("=" * 70)
        print(f"Model: {MODEL_NAME}")
        print(f"API Base: {API_BASE_URL}")
        print("LLM Mode: True")
        print("=" * 70)
        print()

        difficulties = ["easy", "medium", "hard"]
        results = []

        for diff in difficulties:
            for si in range(args.seeds):
                seed = args.seed_start + si
                if results:
                    print()
                print(f"{'--' * 30}")
                print(f"  Episode: {diff.upper()} seed={seed}")
                print(f"{'--' * 30}")
                try:
                    result = run_episode(difficulty=diff, seed=seed)
                    results.append(result)
                except Exception as e:
                    print(f"[ERROR] Failed to run episode {diff} seed={seed}: {e}", file=sys.stderr)
                    # Log failure and continue
                    results.append({
                        "difficulty": diff,
                        "steps": 0,
                        "total_score": 0.01,
                        "f1_score": 0.01,
                        "discovery_rate": 0.01,
                        "success": False,
                        "rewards": [],
                        "metrics": {},
                        "error": str(e),
                    })

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

        if results:
            avg_f1 = sum(r["f1_score"] for r in results) / len(results)
            avg_score = sum(r["total_score"] for r in results) / len(results)
            scores = [r["total_score"] for r in results]
            score_std = statistics.pstdev(scores) if len(scores) > 1 else 0.0
            print(f"  {'--' * 28}")
            print(f"  {'AVERAGE':<12} {'':>6} {avg_f1:>8.3f} {'':>10} {avg_score:>8.3f}  (std={score_std:.3f})")
        print()
        
        return 0
    
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"[CRITICAL] Unhandled error in main: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
