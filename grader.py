"""
Sentinel-Log-Shield v2: Grading Engine.

Evaluates agent performance using hidden ground truth from the scenario.
Unlike v1 where grader and agent used the same regexes, here the grader
has access to the full entity graph and scores based on discovery depth,
redaction accuracy, and investigation efficiency.

Scoring components:
- F1 Score (precision/recall of redacted vs ground truth) — 70% weight
- Discovery Rate (fraction of total PII the agent even found) — 20% weight
- Recall Component (raw recall bonus) — 10% weight
- Efficiency Bonus (steps saved from budget) — 5% weight
- Secret Penalty (harsh penalty per missed critical secret) — up to -30%
"""

from typing import Dict, Set, List, Tuple, Any

# Epsilon bounds: scores must be strictly between 0 and 1 (not exactly 0.0 or 1.0)
# Using 0.05 as the boundary to ensure strict bounds with safety margin
EPSILON = 0.05
MIN_SCORE = EPSILON
MAX_SCORE = 1.0 - EPSILON


class InvestigationGrader:
    """Evaluates the agent's investigation and redaction performance."""

    @staticmethod
    def compute_metrics(
        redacted: Set[str],
        ground_truth: Set[str],
        discovered: Set[str],
        steps_used: int,
        steps_budget: int,
        secret_tokens: Set[str],
    ) -> Dict[str, Any]:
        """
        Compute comprehensive metrics for the investigation episode.

        PRINCIPLE: All returned scores are strictly bounded within (MIN_SCORE, MAX_SCORE).
        - Counts are raw integers (not scores)
        - Rates are strict percentages bounded [MIN_SCORE, MAX_SCORE]
        - Penalties are internal deductions, never exposed as negative scores
        - Empty ground truth returns minimal scores, not perfect scores
        """
        # Input validation: steps_budget must be positive for meaningful efficiency calculation
        assert steps_budget > 0, f"steps_budget must be positive, got {steps_budget}"
        
        total_pii = len(ground_truth)
        
        # ====== EDGE CASE: Empty ground truth ======
        # No work to grade → return minimal (failure) scores
        if total_pii == 0:
            return {
                # Score fields - all return minimal bounded scores
                "precision": MIN_SCORE,
                "recall": MIN_SCORE,
                "f1_score": MIN_SCORE,
                "discovery_rate": MIN_SCORE,
                "efficiency": MIN_SCORE,
                "total_score": MIN_SCORE,
                
                # Non-score fields (counts and metadata)
                "discovered_count": 0,
                "steps_used": steps_used,
                "steps_budget": steps_budget,
                "steps_saved": max(0, steps_budget - steps_used),  # Clamp properly
                "secrets_found": 0,
                "secrets_missed": 0,
                "secrets_total": 0,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "total_pii": 0,
                
                # Component scores - all minimal
                "f1_component": MIN_SCORE,
                "discovery_component": MIN_SCORE,
                "recall_component": MIN_SCORE,
                "efficiency_bonus": MIN_SCORE,
                
                # Metadata
                "grade": "F",
            }
        
        # ====== NORMAL CASE: Non-empty ground truth ======
        
        # Count metrics
        true_positives = len(redacted & ground_truth)
        false_positives = len(redacted - ground_truth)
        false_negatives = len(ground_truth - redacted)
        discovered_correct = len(discovered & ground_truth)
        secrets_found = len(secret_tokens & redacted)
        secrets_missed = len(secret_tokens - redacted)
        secrets_total = len(secret_tokens)
        
        # ====== PRECISION: TP / (TP + FP) ======
        if true_positives + false_positives > 0:
            precision = true_positives / (true_positives + false_positives)
        else:
            precision = MIN_SCORE  # No redactions made → minimal score
        precision = max(MIN_SCORE, min(MAX_SCORE, precision))
        
        # ====== RECALL: TP / total ======
        recall = true_positives / total_pii  # Always valid (total_pii > 0)
        recall = max(MIN_SCORE, min(MAX_SCORE, recall))
        
        # ====== F1 SCORE: 2 * P * R / (P + R) ======
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = MIN_SCORE
        f1 = max(MIN_SCORE, min(MAX_SCORE, f1))
        
        # ====== DISCOVERY RATE: correct_discoveries / total ======
        discovery_rate = discovered_correct / total_pii
        discovery_rate = max(MIN_SCORE, min(MAX_SCORE, discovery_rate))
        
        # ====== EFFICIENCY: steps_saved / steps_budget ======
        steps_saved = max(0, steps_budget - steps_used)  # Always non-negative
        if steps_budget > 0:
            efficiency = steps_saved / steps_budget
        else:
            efficiency = MIN_SCORE
        efficiency = max(MIN_SCORE, min(MAX_SCORE, efficiency))
        
        # ====== COMPONENT SCORES (for breakdown, all bounded) ======
        f1_component = max(MIN_SCORE, min(MAX_SCORE, f1 * 0.70))
        discovery_component = max(MIN_SCORE, min(MAX_SCORE, discovery_rate * 0.20))
        recall_component = max(MIN_SCORE, min(MAX_SCORE, recall * 0.10))
        efficiency_bonus = max(MIN_SCORE, min(MAX_SCORE, efficiency * 0.05))
        
        # ====== SECRET PENALTY (internal deduction only, NOT returned as score) ======
        # Negative penalty for missed secrets: -0.20 per secret missed (reduced from -0.30 for less harsh impact)
        secret_penalty = -0.20 * secrets_missed
        
        # ====== TOTAL SCORE: sum of all components + penalty ======
        # Raw combination
        raw_score = f1_component + discovery_component + recall_component + efficiency_bonus + secret_penalty
        
        # Clamp final score to valid range
        total_score = max(MIN_SCORE, min(MAX_SCORE, raw_score))
        
        # ====== LETTER GRADE ======
        grade = InvestigationGrader._letter_grade(total_score)
        
        # ====== BUILD RESULT ======
        # CRITICAL: Only return bounded scores and raw counts.
        # No negative values. No MAX_SCORE for empty cases.
        return {
            # ===== SCORE FIELDS (all strictly bounded) =====
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "discovery_rate": discovery_rate,
            "efficiency": efficiency,
            "f1_component": f1_component,
            "discovery_component": discovery_component,
            "recall_component": recall_component,
            "efficiency_bonus": efficiency_bonus,
            "total_score": total_score,
            
            # ===== NON-SCORE FIELDS (counts, not bounded as scores) =====
            "discovered_count": discovered_correct,
            "steps_used": steps_used,
            "steps_budget": steps_budget,
            "steps_saved": steps_saved,
            "secrets_found": secrets_found,
            "secrets_missed": secrets_missed,
            "secrets_total": secrets_total,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "total_pii": total_pii,
            
            # ===== METADATA =====
            "grade": grade,
        }

    @staticmethod
    def _letter_grade(score: float) -> str:
        """Assign a letter grade based on total score."""
        if score >= 0.95:
            return "S"   # Perfect
        elif score >= 0.85:
            return "A"   # Excellent
        elif score >= 0.70:
            return "B"   # Good
        elif score >= 0.50:
            return "C"   # Adequate
        elif score >= 0.30:
            return "D"   # Poor
        else:
            return "F"   # Failed

    @staticmethod
    def generate_feedback(metrics: Dict[str, Any]) -> str:
        """Generate human-readable feedback from metrics."""
        parts = []
        grade = metrics["grade"]
        score = metrics["total_score"]

        parts.append(f"Grade: {grade} ({score:.1%})")

        # F1 feedback
        f1 = metrics["f1_score"]
        if f1 >= 0.95:
            parts.append("Redaction accuracy: Outstanding.")
        elif f1 >= 0.80:
            parts.append("Redaction accuracy: Strong. Minor improvements possible.")
        elif f1 >= 0.60:
            parts.append("Redaction accuracy: Moderate. Missed several items.")
        else:
            parts.append("Redaction accuracy: Needs significant improvement.")

        # Discovery feedback
        dr = metrics["discovery_rate"]
        if dr < 0.5:
            parts.append(f"Investigation depth: Shallow ({dr:.0%}). Explore more entities.")
        elif dr < 0.8:
            parts.append(f"Investigation depth: Moderate ({dr:.0%}). Go deeper.")
        else:
            parts.append(f"Investigation depth: Thorough ({dr:.0%}).")

        # Secret feedback
        if metrics["secrets_missed"] > 0:
            parts.append(f"⚠️ CRITICAL: {metrics['secrets_missed']} secret(s) missed! Heavy penalty applied.")
        elif metrics["secrets_total"] > 0:
            parts.append(f"✅ All {metrics['secrets_total']} secret(s) found and redacted.")

        # Efficiency
        if metrics["steps_saved"] > 2:
            parts.append(f"Efficient: {metrics['steps_saved']} steps saved (bonus applied).")

        return " | ".join(parts)
