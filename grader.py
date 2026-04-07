"""
grader.py — Evaluation and Reward Calculation Engine

Implements scoring logic for all 3 PII redaction tasks:
- Task 1: Email & IPv4 detection
- Task 2: Username extraction
- Task 3: High-entropy secret detection

Uses F1-score for primary metric with reward shaping for agent feedback.
"""

import re
from typing import Dict, Set, Tuple
from models import TaskEnum


class RedactionGrader:
    """Evaluates redaction quality and computes rewards."""

    # Regex patterns for ground truth extraction
    PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "ipv4": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        "username": r"User\s+'([A-Za-z]+)'",
        "token_sk": r'\bsk_[a-z0-9_]{20,}\b',
        "token_aws": r'\b[A-Z0-9]{20}\b',
        "token_secret": r'(?:secret|key|password|api_key|token)\s*=\s*(\S+)',
    }

    @staticmethod
    def extract_ground_truth(log: str, task: TaskEnum) -> Set[str]:
        """
        Extract ground truth PII from raw log based on task type.

        Args:
            log: Raw log content
            task: Task type (TASK_1, TASK_2, TASK_3)

        Returns:
            Set of ground truth PII entries
        """
        pii_set = set()

        if task == TaskEnum.TASK_1:
            # Email addresses
            emails = re.findall(RedactionGrader.PATTERNS["email"], log)
            pii_set.update(emails)

            # IPv4 addresses
            ipv4s = re.findall(RedactionGrader.PATTERNS["ipv4"], log)
            # Filter out broadcast addresses
            ipv4s = [ip for ip in ipv4s if ip != "255.255.255.255"]
            pii_set.update(ipv4s)

        elif task == TaskEnum.TASK_2:
            # Usernames in quotes: User 'Name'
            usernames = re.findall(RedactionGrader.PATTERNS["username"], log, re.IGNORECASE)
            pii_set.update(usernames)

        elif task == TaskEnum.TASK_3:
            # OpenAI-style tokens (sk_live_*, sk_test_*)
            tokens = re.findall(RedactionGrader.PATTERNS["token_sk"], log, re.IGNORECASE)
            pii_set.update(tokens)

            # AWS-like keys (20 alphanumeric characters)
            aws_keys = re.findall(RedactionGrader.PATTERNS["token_aws"], log)
            pii_set.update(aws_keys)

            # Secret assignments (key=value format)
            secrets = re.findall(
                RedactionGrader.PATTERNS["token_secret"], log, re.IGNORECASE
            )
            pii_set.update(secrets)

        return pii_set

    @staticmethod
    def calculate_metrics(
        detected_pii: Set[str], ground_truth: Set[str]
    ) -> Tuple[float, float, float, float]:
        """
        Calculate precision, recall, F1-score, and over-redaction ratio.

        Args:
            detected_pii: Set of PII the agent detected
            ground_truth: Set of actual PII in the log

        Returns:
            Tuple of (precision, recall, f1_score, over_redaction_ratio)
        """
        if not ground_truth:
            # No PII in the log - perfect if agent also found nothing
            if detected_pii:
                return 0.0, 1.0, 0.0, 1.0
            else:
                return 1.0, 1.0, 1.0, 0.0

        true_positives = len(detected_pii & ground_truth)
        false_positives = len(detected_pii - ground_truth)
        false_negatives = len(ground_truth - detected_pii)

        precision = true_positives / len(detected_pii) if detected_pii else 0.0
        recall = true_positives / len(ground_truth) if ground_truth else 0.0
        f1_score = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        over_redaction_ratio = false_positives / len(detected_pii) if detected_pii else 0.0

        return precision, recall, f1_score, over_redaction_ratio

    @staticmethod
    def shape_reward(
        f1_score: float,
        recall: float,
        precision: float,
        over_redaction_ratio: float,
        false_negatives: int,
        task: TaskEnum,
    ) -> Tuple[float, Dict[str, float], str]:
        """
        Apply reward shaping based on redaction quality.

        Reward structure:
        - 1.0 (perfect): F1==1.0
        - 0.8 (excellent): Recall>=0.9, Precision>=0.8
        - 0.5 (good): F1>=0.6
        - 0.2 (partial): Otherwise
        - MINUS 1.0 (critical): Missed secrets in Task 3
        - MINUS 0.3 (penalty): Over-redacting >20% non-PII

        Args:
            f1_score: F1-score (0.0-1.0)
            recall: Recall metric (0.0-1.0)
            precision: Precision metric (0.0-1.0)
            over_redaction_ratio: Ratio of false positives (0.0-1.0)
            false_negatives: Count of missed PII
            task: Task type for critical secret penalty

        Returns:
            Tuple of (base_reward, penalties_dict, feedback_message)
        """
        penalties = {}
        feedback = ""

        # Base reward from F1 score
        if f1_score == 1.0:
            base_reward = 1.0
            feedback = "Perfect redaction! All PII detected and redacted correctly."
        elif recall >= 0.9 and precision >= 0.8:
            base_reward = 0.8
            feedback = "Excellent redaction. Minor improvement possible."
        elif f1_score >= 0.6:
            base_reward = 0.5
            feedback = "Good effort. Consider improving detection."
        else:
            base_reward = 0.2
            feedback = "Partial progress. Review detection logic."

        # Critical penalty: Missed secrets in Task 3
        if false_negatives > 0 and task == TaskEnum.TASK_3:
            penalties["missed_secrets"] = -1.0
            feedback += " ⚠️ CRITICAL: High-risk secret not redacted!"

        # Over-redaction penalty: Destroying log utility
        if over_redaction_ratio > 0.2:
            penalties["over_redacting"] = -0.3
            feedback += " ⚠️ Caution: Over-redacting useful data (>20%)."

        return base_reward, penalties, feedback

    @classmethod
    def grade(
        cls, detected_redactions: list, raw_log: str, task: TaskEnum
    ) -> Dict:
        """
        Complete grading pipeline: extract ground truth → calculate metrics → shape reward.

        Args:
            detected_redactions: List of dicts with 'original' field
            raw_log: Raw log content
            task: Task type

        Returns:
            Dict with keys:
            - base_reward: Raw score before penalties
            - penalties: Dict of penalty_name -> penalty_value
            - total_reward: base_reward + sum(penalties)
            - metrics: Dict with precision, recall, f1_score, over_redaction_ratio
            - feedback: Human-readable feedback message
        """
        # Extract detected PII
        detected_pii = {r["original"] for r in detected_redactions}

        # Extract ground truth
        ground_truth = cls.extract_ground_truth(raw_log, task)

        # Calculate metrics
        precision, recall, f1_score, over_redaction_ratio = cls.calculate_metrics(
            detected_pii, ground_truth
        )

        # Count false negatives
        false_negatives = len(ground_truth - detected_pii)

        # Shape reward
        base_reward, penalties, feedback = cls.shape_reward(
            f1_score, recall, precision, over_redaction_ratio, false_negatives, task
        )

        total_reward = base_reward + sum(penalties.values())

        return {
            "base_reward": base_reward,
            "penalties": penalties,
            "total_reward": total_reward,
            "metrics": {
                "precision": precision,
                "recall": recall,
                "f1_score": f1_score,
                "over_redaction_ratio": over_redaction_ratio,
            },
            "feedback": feedback,
        }


# Convenience function for simple grading
def grade_redaction(detected_redactions: list, raw_log: str, task: TaskEnum) -> Dict:
    """
    Simple interface to grade a redaction.

    Usage:
        result = grade_redaction(
            detected_redactions=[{"original": "user@example.com"}],
            raw_log="User user@example.com logged in",
            task=TaskEnum.TASK_1
        )
        print(result["total_reward"])  # 1.0
    """
    return RedactionGrader.grade(detected_redactions, raw_log, task)
