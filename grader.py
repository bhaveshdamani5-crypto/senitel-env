"""
Sentinel-Log-Shield v2: Grading Engine.

Evaluates agent performance using hidden ground truth from the scenario.
Unlike v1 where grader and agent used the same regexes, here the grader
has access to the full entity graph and scores based on discovery depth,
redaction accuracy, and investigation efficiency.

Scoring components:
- F1 Score (precision/recall of redacted vs ground truth) — 70% weight
- Discovery Rate (fraction of total PII the agent even found) — 20% weight
- Efficiency Bonus (steps saved from budget) — 5% weight
- Secret Penalty (harsh penalty per missed critical secret) — up to -30%
"""

from typing import Dict, Set, List, Tuple, Any

# Epsilon bounds: scores must be strictly between 0 and 1 (not exactly 0.0 or 1.0)
EPSILON = 0.0001
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

        Args:
            redacted: PII items the agent chose to redact
            ground_truth: All PII items in the scenario (hidden from agent)
            discovered: PII items the agent discovered through scanning/investigation
            steps_used: Number of steps the agent consumed
            steps_budget: Maximum steps allowed
            secret_tokens: Set of critical secret tokens in the scenario

        Returns:
            Dictionary with all metrics and component scores
        """
        total = len(ground_truth)
        if total == 0:
            return {
                "precision": MAX_SCORE, "recall": MAX_SCORE, "f1_score": MAX_SCORE,
                "discovery_rate": MAX_SCORE, "efficiency": MAX_SCORE,
                "total_score": MAX_SCORE, "grade": "S",
            }

        # Core metrics
        true_positives = len(redacted & ground_truth)
        false_positives = len(redacted - ground_truth)
        false_negatives = len(ground_truth - redacted)

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else MIN_SCORE
        recall = true_positives / total
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else MIN_SCORE

        # Discovery rate
        discovered_correct = len(discovered & ground_truth)
        discovery_rate = discovered_correct / total if total > 0 else MIN_SCORE

        # Efficiency
        steps_saved = max(0, steps_budget - steps_used)
        efficiency = steps_saved / steps_budget if steps_budget > 0 else MIN_SCORE

        # Secret handling
        secrets_found = len(secret_tokens & redacted)
        secrets_missed = len(secret_tokens - redacted)
        secrets_total = len(secret_tokens)

        # Composite score
        f1_component = f1 * 0.70
        discovery_component = discovery_rate * 0.20
        recall_component = recall * 0.10
        efficiency_bonus = efficiency * 0.05
        secret_penalty = -0.30 * secrets_missed

        total_score = max(MIN_SCORE, min(MAX_SCORE,
            f1_component + discovery_component + recall_component + efficiency_bonus + secret_penalty
        ))

        # Letter grade
        grade = InvestigationGrader._letter_grade(total_score)

        # Helper to strictly bound values (never return 0.0 or 1.0)
        def strictly_bound(val: float) -> float:
            # Clip to EPSILON bounds without any rounding
            return max(EPSILON, min(1.0 - EPSILON, val))

        return {
            # Core metrics - strictly bounded (no rounding, no 0.0 or 1.0)
            "precision": strictly_bound(precision),
            "recall": strictly_bound(recall),
            "f1_score": strictly_bound(f1),
            # Discovery
            "discovery_rate": strictly_bound(discovery_rate),
            "discovered_count": discovered_correct,
            # Efficiency
            "efficiency": strictly_bound(efficiency),
            "steps_used": steps_used,
            "steps_budget": steps_budget,
            "steps_saved": steps_saved,
            # Secrets
            "secrets_found": secrets_found,
            "secrets_missed": secrets_missed,
            "secrets_total": secrets_total,
            # Counts
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "total_pii": total,
            # Score components
            "f1_component": strictly_bound(f1_component),
            "discovery_component": strictly_bound(discovery_component),
            "recall_component": strictly_bound(recall_component),
            "efficiency_bonus": efficiency_bonus,  # Can be 0 (no bonus if no steps saved)
            "secret_penalty": secret_penalty,  # Can be 0 or negative (semantically correct)
            # Final
            "total_score": strictly_bound(total_score),
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
