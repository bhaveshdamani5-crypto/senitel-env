#!/usr/bin/env python3
"""
Score Bounds Validation Test
Ensures all scores returned from the environment and grader are strictly in (0, 1).
"""

import sys
import json
from env import SentinelEnvironment, EPSILON, MAX_SCORE
from models import AgentAction, ActionType, Difficulty
from grader import InvestigationGrader

EPSILON_VAL = 0.05
MIN_ALLOWED = EPSILON_VAL
MAX_ALLOWED = 1.0 - EPSILON_VAL


def check_score_bounds(name: str, value: any, allow_none=False) -> bool:
    """Check if a value is strictly within (0, 1) or is a non-score.
    
    Validator requirement: Scores must not be exactly 0.0 or 1.0
    So valid range is [0.001, 0.999] inclusive (EPSILON to 1-EPSILON)
    """
    if value is None:
        if allow_none:
            print(f"  ✓ {name}: None (allowed)")
            return True
        else:
            print(f"  ✗ {name}: None (not allowed for scores)")
            return False
    
    # Skip non-float types
    if isinstance(value, str):
        print(f"  ✓ {name}: '{value}' (string, skipped)")
        return True
    
    if isinstance(value, int):
        print(f"  ✓ {name}: {value} (integer/count, skipped)")
        return True
    
    if isinstance(value, bool):
        print(f"  ✓ {name}: {value} (bool, skipped)")
        return True
    
    if not isinstance(value, float):
        print(f"  ✓ {name}: {type(value).__name__} (skipped)")
        return True
    
    # Check score bounds: must NOT be exactly 0.0 or 1.0
    # Valid range: [0.001, 0.999] (inclusive on both ends)
    is_valid = MIN_ALLOWED <= value <= MAX_ALLOWED
    
    if is_valid:
        print(f"  ✓ {name}: {value:.6f} ✓")
        return True
    else:
        if value == 0.0 or value == 1.0:
            symbol = "✗✗✗ CRITICAL"
        else:
            symbol = "✗✗ INVALID"
        print(f"  {symbol}: {name}: {value:.6f} (outside [{MIN_ALLOWED}, {MAX_ALLOWED}])")
        return False


def validate_observation(obs, test_name=""):
    """Check that an Observation's scores are in bounds."""
    print(f"\n📋 Validating Observation {test_name}")
    errors = []
    
    if hasattr(obs, 'score_so_far'):
        if not check_score_bounds("score_so_far", obs.score_so_far):
            errors.append("score_so_far")
    
    return len(errors) == 0


def validate_reward(reward, test_name=""):
    """Check that a Reward's scores are in bounds."""
    print(f"\n💰 Validating Reward {test_name}")
    errors = []
    
    # Check reward fields - penalty can be negative, so exclude from bounds check
    score_fields = ["redaction_score", "discovery_bonus", "efficiency_bonus", "total_reward", "score"]
    for field in score_fields:
        if hasattr(reward, field):
            value = getattr(reward, field)
            if not check_score_bounds(field, value):
                errors.append(field)
    
    # Penalty can be zero or negative - just log it
    if hasattr(reward, 'penalty'):
        penalty_val = reward.penalty
        if isinstance(penalty_val, float):
            print(f"  ✓ penalty: {penalty_val:.6f} (penalty, can be negative)")
    
    # Check metrics
    if hasattr(reward, 'metrics') and reward.metrics:
        print("\n  Metrics:")
        for key, value in reward.metrics.items():
            # These are score fields and MUST be strictly bounded
            score_fields = {
                "precision", "recall", "f1_score", "discovery_rate", "efficiency",
                "efficiency_bonus", "f1_component", "discovery_component", 
                "recall_component", "total_score"
            }
            
            # These are COUNTS and STRINGS (not scores)
            non_score_fields = {
                "discovered_count", "steps_used", "steps_budget", "steps_saved",
                "secrets_found", "secrets_missed", "secrets_total",
                "true_positives", "false_positives", "false_negatives", "total_pii",
                "new_entities", "total_discovered", "deadend", "new_logs_revealed",
                "secrets_found", "honeypot_triggered", "correct", "coverage",
                "items_redacted_total", "items_remaining", "grade"
            }
            
            if key in score_fields:
                if not check_score_bounds(f"  metrics[{key}]", value):
                    errors.append(f"metrics.{key}")
            elif key in non_score_fields or key.startswith("items_") or key.startswith("new_"):
                # These are allowed to be any value
                if isinstance(value, (int, str)):
                    print(f"    ✓ metrics[{key}]: {value} (count/string)")
                elif isinstance(value, float) and key == "coverage":
                    # coverage is a special score that should be bounded
                    if not check_score_bounds(f"  metrics[{key}]", value):
                        errors.append(f"metrics.{key}")
            else:
                # Unknown field - be lenient but report
                print(f"    ? metrics[{key}]: {type(value).__name__} value={value} (unknown field)")
    
    # CRITICAL: Check for secret_penalty (should NOT exist)
    if hasattr(reward, 'metrics') and reward.metrics:
        if "secret_penalty" in reward.metrics:
            pen_val = reward.metrics["secret_penalty"]
            print(f"\n  ✗✗✗ CRITICAL: Found secret_penalty={pen_val} in metrics (should be removed!)")
            errors.append("secret_penalty_present")
    
    return len(errors) == 0


def validate_grader_metrics(metrics, test_name=""):
    """Check that grader.compute_metrics returns valid scores."""
    print(f"\n🎯 Validating Grader Metrics {test_name}")
    errors = []
    
    # These MUST be strictly bounded
    score_fields = {
        "precision", "recall", "f1_score", "discovery_rate", "efficiency",
        "f1_component", "discovery_component", "recall_component", "efficiency_bonus",
        "total_score"
    }
    
    # These are counts/strings
    non_score_fields = {
        "discovered_count", "steps_used", "steps_budget", "steps_saved",
        "secrets_found", "secrets_missed", "secrets_total",
        "true_positives", "false_positives", "false_negatives", "total_pii", "grade"
    }
    
    for key, value in metrics.items():
        if key in score_fields:
            if not check_score_bounds(f"metrics[{key}]", value):
                errors.append(f"metrics.{key}")
        elif key in non_score_fields:
            if isinstance(value, (int, str)):
                print(f"  ✓ metrics[{key}]: {value} (count/string)")
            else:
                print(f"  ✓ metrics[{key}]: {value}")
        else:
            print(f"  ? metrics[{key}]: {type(value).__name__} = {value}")
    
    # CRITICAL: Check for secret_penalty (should NOT exist in grader output)
    if "secret_penalty" in metrics:
        print(f"\n  ✗✗✗ CRITICAL: Found secret_penalty={metrics['secret_penalty']} (should be removed!)")
        errors.append("secret_penalty_present")
    
    return len(errors) == 0


def test_full_episode():
    """Run a complete episode and validate all scores."""
    print("\n" + "="*70)
    print("🧪 FULL EPISODE TEST")
    print("="*70)
    
    all_valid = True
    
    # Reset
    print("\n1️⃣  Resetting environment...")
    env = SentinelEnvironment()
    reset_result = env.reset(difficulty="easy", seed=42)
    print("   ✓ Reset successful")
    
    if not validate_observation(reset_result.observation, "(after reset)"):
        all_valid = False
    
    # Scan
    print("\n2️⃣  Scanning visible logs...")
    result = env.step(AgentAction(action_type=ActionType.SCAN))
    print("   ✓ Scan successful")
    
    if not validate_reward(result.reward, "(after SCAN)"):
        all_valid = False
    if not validate_observation(result.observation, "(after SCAN)"):
        all_valid = False
    
    # Investigate
    print("\n3️⃣  Investigating first entity...")
    if result.observation.investigation_targets:
        target = result.observation.investigation_targets[0]
        result = env.step(AgentAction(action_type=ActionType.INVESTIGATE, target_entity=target))
        print(f"   ✓ Investigation of '{target}' successful")
        
        if not validate_reward(result.reward, f"(after INVESTIGATE {target})"):
            all_valid = False
        if not validate_observation(result.observation, f"(after INVESTIGATE {target})"):
            all_valid = False
    
    # Redact
    print("\n4️⃣  Redacting discovered PII...")
    if result.observation.discovered_entities:
        redactions = [
            {"original": e, "type": "username"}
            for e in list(result.observation.discovered_entities)[:2]
        ]
        result = env.step(AgentAction(action_type=ActionType.REDACT, redactions=redactions))
        print(f"   ✓ Redaction of {len(redactions)} items successful")
        
        if not validate_reward(result.reward, "(after REDACT)"):
            all_valid = False
        if not validate_observation(result.observation, "(after REDACT)"):
            all_valid = False
    
    # Get state
    print("\n5️⃣  Getting environment state...")
    state = env.state()
    print("   ✓ State retrieval successful")
    
    if hasattr(state, 'total_reward'):
        if not check_score_bounds("EnvironmentState.total_reward", state.total_reward):
            all_valid = False
    
    # Submit
    print("\n6️⃣  Submitting findings...")
    result = env.step(AgentAction(action_type=ActionType.SUBMIT))
    print("   ✓ Submit successful")
    
    if not validate_reward(result.reward, "(after SUBMIT)"):
        all_valid = False
    
    return all_valid


def test_grader():
    """Test the grader with various scenarios."""
    print("\n" + "="*70)
    print("📊 GRADER TEST")
    print("="*70)
    
    all_valid = True
    
    # Test case 1: Perfect score
    print("\n📌 Test Case 1: Perfect performance")
    metrics = InvestigationGrader.compute_metrics(
        redacted={"email1", "email2", "ip1", "token1"},
        ground_truth={"email1", "email2", "ip1", "token1"},
        discovered={"email1", "email2", "ip1", "token1"},
        steps_used=2,
        steps_budget=10,
        secret_tokens={"token1"},
    )
    if not validate_grader_metrics(metrics, "(perfect score)"):
        all_valid = False
    
    # Test case 2: Missed secrets (penalty scenario)
    print("\n📌 Test Case 2: Missed critical secrets (penalty)")
    metrics = InvestigationGrader.compute_metrics(
        redacted={"email1", "ip1"},
        ground_truth={"email1", "email2", "ip1", "token1"},
        discovered={"email1", "ip1"},
        steps_used=8,
        steps_budget=10,
        secret_tokens={"token1"},
    )
    if not validate_grader_metrics(metrics, "(with penalty)"):
        all_valid = False
    
    # Test case 3: Empty ground truth (edge case)
    print("\n📌 Test Case 3: Edge case - empty scenario")
    metrics = InvestigationGrader.compute_metrics(
        redacted=set(),
        ground_truth=set(),
        discovered=set(),
        steps_used=0,
        steps_budget=10,
        secret_tokens=set(),
    )
    if not validate_grader_metrics(metrics, "(empty scenario)"):
        all_valid = False
    
    return all_valid


def main():
    print("\n" + "="*70)
    print("🔬 SCORE BOUNDS VALIDATION TEST SUITE")
    print("="*70)
    print(f"\nExpected bounds: ({MIN_ALLOWED}, {MAX_ALLOWED})")
    print(f"EPSILON = {EPSILON_VAL}")
    
    results = []
    
    # Run all tests
    try:
        results.append(("Full Episode", test_full_episode()))
        results.append(("Grader Metrics", test_grader()))
    except Exception as e:
        print(f"\n❌ TEST CRASHED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Summary
    print("\n" + "="*70)
    print("📋 TEST SUMMARY")
    print("="*70)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED - Ready for submission!")
    else:
        print("❌ SOME TESTS FAILED - Fix issues before submission")
    print("="*70 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
