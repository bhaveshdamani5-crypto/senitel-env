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
# Using 0.01 as the boundary to ensure strict bounds
EPSILON = 0.01
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
            # For empty scenarios, return bounded scores
            return {
                "precision": MAX_SCORE,
                "recall": MAX_SCORE,
                "f1_score": MAX_SCORE,
                "discovery_rate": MAX_SCORE,
                "efficiency": MAX_SCORE,
                "total_score": MAX_SCORE,
                "grade": "S",
                "discovered_count": 0,
                "steps_used": steps_used,
                "steps_budget": steps_budget,
                "steps_saved": steps_budget - steps_used,
                "secrets_found": 0,
                "secrets_missed": 0,
                "secrets_total": 0,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "total_pii": 0,
                "f1_component": 0.7 * MAX_SCORE,
                "discovery_component": 0.2 * MAX_SCORE,
                "recall_component": 0.1 * MAX_SCORE,
                "efficiency_bonus": 0.05 * MAX_SCORE,
            }

        # Core metrics with proper bounds checking
        true_positives = len(redacted & ground_truth)
        false_positives = len(redacted - ground_truth)
        false_negatives = len(ground_truth - redacted)

        # Calculate base metrics, ensuring no division by zero and proper bounds
        if true_positives + false_positives > 0:
            precision = true_positives / (true_positives + false_positives)
        else:
            precision = MIN_SCORE

        recall = true_positives / total if total > 0 else MIN_SCORE

        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = MIN_SCORE

        # Discovery rate
        discovered_correct = len(discovered & ground_truth)
        discovery_rate = discovered_correct / total if total > 0 else MIN_SCORE

        # Efficiency (steps saved as fraction of budget)
        steps_saved = max(0, steps_budget - steps_used)
        efficiency = steps_saved / steps_budget if steps_budget > 0 else MIN_SCORE

        # Secret handling
        secrets_found = len(secret_tokens & redacted)
        secrets_missed = len(secret_tokens - redacted)
        secrets_total = len(secret_tokens)

        # Composite score calculation
        f1_component = f1 * 0.70
        discovery_component = discovery_rate * 0.20
        recall_component = recall * 0.10
        efficiency_bonus = efficiency * 0.05
        secret_penalty = -0.30 * secrets_missed

        # Calculate raw total before clamping
        raw_score = f1_component + discovery_component + recall_component + efficiency_bonus + secret_penalty

        # Ensure total_score is strictly bounded
        total_score = max(MIN_SCORE, min(MAX_SCORE, raw_score))

        # Letter grade based on bounded score
        grade = InvestigationGrader._letter_grade(total_score)

        return {
            # Core metrics - strictly bounded
            "precision": max(MIN_SCORE, min(MAX_SCORE, precision)),
            "recall": max(MIN_SCORE, min(MAX_SCORE, recall)),
            "f1_score": max(MIN_SCORE, min(MAX_SCORE, f1)),
            # Discovery
            "discovery_rate": max(MIN_SCORE, min(MAX_SCORE, discovery_rate)),
            "discovered_count": discovered_correct,
            # Efficiency
            "efficiency": max(MIN_SCORE, min(MAX_SCORE, efficiency)),
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
            # Score components - only actual scores clamped
            "f1_component": max(MIN_SCORE, min(MAX_SCORE, f1_component)),
            "discovery_component": max(MIN_SCORE, min(MAX_SCORE, discovery_component)),
            "recall_component": max(MIN_SCORE, min(MAX_SCORE, recall_component)),
            "efficiency_bonus": max(MIN_SCORE, min(MAX_SCORE, efficiency_bonus)),
            # Final
            "total_score": total_score,
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

        # Calculate raw total before clamping
        raw_score = f1_component + discovery_component + recall_component + efficiency_bonus + secret_penalty
        total_score = max(MIN_SCORE, min(MAX_SCORE, raw_score))

        # Letter grade
        grade = InvestigationGrader._letter_grade(total_score)

        return {
            # Core metrics - strictly bounded (no rounding, no 0.0 or 1.0)
            "precision": max(MIN_SCORE, min(MAX_SCORE, precision)),
            "recall": max(MIN_SCORE, min(MAX_SCORE, recall)),
            "f1_score": max(MIN_SCORE, min(MAX_SCORE, f1)),
            # Discovery
            "discovery_rate": max(MIN_SCORE, min(MAX_SCORE, discovery_rate)),
            "discovered_count": discovered_correct,
            # Efficiency
            "efficiency": max(MIN_SCORE, min(MAX_SCORE, efficiency)),
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
            # Score components - only actual scores clamped (strictly bounded for validator)
            "f1_component": max(MIN_SCORE, min(MAX_SCORE, f1_component)),
            "discovery_component": max(MIN_SCORE, min(MAX_SCORE, discovery_component)),
            "recall_component": max(MIN_SCORE, min(MAX_SCORE, recall_component)),
            "efficiency_bonus": max(MIN_SCORE, min(MAX_SCORE, efficiency_bonus)),
            # NOTE: secret_penalty is NOT included here because it's negative and violates strict bounds
            # The penalty is already incorporated into total_score via raw_total calculation above
            # Final
            "total_score": max(MIN_SCORE, min(MAX_SCORE, total_score)),
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
