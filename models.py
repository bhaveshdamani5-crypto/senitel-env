"""
Sentinel-Log-Shield v2: Data Models for Interactive Security Investigation Environment.

Defines the action space, observation space, reward structure, and state tracking
for a genuine multi-step RL investigation environment.
"""

from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional, Any
from enum import Enum

# Scores must be strictly between 0 and 1 (not 0.0 or 1.0)
_EPSILON = 1e-6
_MAX_SCORE = 1.0 - _EPSILON


# ============================================================================
# ACTION SPACE
# ============================================================================

class ActionType(str, Enum):
    """Available actions for the investigating agent."""
    SCAN = "scan"               # Extract PII from currently visible logs
    INVESTIGATE = "investigate" # Deep-dive into an entity → reveals connected logs
    REDACT = "redact"           # Submit discovered PII items for scoring
    SUBMIT = "submit"           # End episode early, receive final score


class Difficulty(str, Enum):
    """Environment difficulty levels."""
    EASY = "easy"       # 2 layers, 12 step budget, 2 users
    MEDIUM = "medium"   # 3 layers, 10 step budget, 3 users
    HARD = "hard"       # 4 layers, 8 step budget, 4+ users


class AgentAction(BaseModel):
    """Action taken by the agent at each step.

    The action_type determines which optional fields are used:
    - SCAN: no extra fields needed (scans visible logs)
    - INVESTIGATE: requires target_entity (e.g., a username, IP, or email)
    - REDACT: requires redactions list
    - SUBMIT: no extra fields (ends episode)
    """
    action_type: ActionType = Field(
        ..., description="Type of action: scan, investigate, redact, or submit"
    )
    target_entity: Optional[str] = Field(
        None,
        description="Entity to investigate (required for 'investigate' action)"
    )
    redactions: Optional[List[Dict[str, str]]] = Field(
        None,
        description="PII items to redact: [{'original': '...', 'type': 'email|ip|username|token|phone|secret'}]"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "action_type": "scan",
                },
                {
                    "action_type": "investigate",
                    "target_entity": "alice",
                },
                {
                    "action_type": "redact",
                    "redactions": [
                        {"original": "alice@corp.com", "type": "email"},
                        {"original": "10.0.0.5", "type": "ip"},
                    ],
                },
                {
                    "action_type": "submit",
                },
            ]
        }


# ============================================================================
# OBSERVATION SPACE
# ============================================================================

class Observation(BaseModel):
    """What the agent sees at each step.

    The observation updates based on agent actions:
    - After SCAN: discovered_entities and scan_results populate
    - After INVESTIGATE: visible_logs expands with connected entries
    - After REDACT: redacted_items updates, score_so_far changes
    """
    visible_logs: List[str] = Field(
        ..., description="Log entries currently visible to the agent"
    )
    discovered_entities: List[str] = Field(
        default_factory=list,
        description="Entities the agent has discovered so far (usernames, IPs, etc.)"
    )
    investigation_targets: List[str] = Field(
        default_factory=list,
        description="Entities available for deeper investigation"
    )
    scan_results: List[Dict[str, str]] = Field(
        default_factory=list,
        description="PII items found in the latest scan"
    )
    redacted_items: List[Dict[str, str]] = Field(
        default_factory=list,
        description="PII items already successfully redacted"
    )
    steps_remaining: int = Field(
        ..., description="Investigation budget remaining"
    )
    steps_used: int = Field(
        default=0, description="Steps consumed so far"
    )
    difficulty: str = Field(
        ..., description="Current difficulty level"
    )
    hint: str = Field(
        default="",
        description="Environment hint about what to look for next"
    )
    score_so_far: float = Field(
        default=0.0, description="Running score based on redactions submitted"
    )
    total_pii_to_find: int = Field(
        default=0,
        description="Total number of PII items the agent should try to find"
    )
    pii_found_count: int = Field(
        default=0, description="Number of PII items correctly redacted so far"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "visible_logs": [
                    "2026-04-07 AUTH: Failed login for alice@corp.com from 10.0.0.5",
                    "2026-04-07 ALERT: Suspicious activity from 10.0.0.5",
                ],
                "discovered_entities": ["alice@corp.com", "10.0.0.5"],
                "investigation_targets": ["alice", "10.0.0.5"],
                "scan_results": [
                    {"original": "alice@corp.com", "type": "email"},
                    {"original": "10.0.0.5", "type": "ip"},
                ],
                "redacted_items": [],
                "steps_remaining": 11,
                "steps_used": 1,
                "difficulty": "medium",
                "hint": "Try investigating the IP address to discover connected users.",
                "score_so_far": 0.0,
                "total_pii_to_find": 8,
                "pii_found_count": 0,
            }
        }


# ============================================================================
# REWARD STRUCTURE
# ============================================================================

class Reward(BaseModel):
    """Reward signal with multiple components for rich feedback."""
    redaction_score: float = Field(
        default=_EPSILON,
        description="Score for correctly redacted items this step"
    )
    discovery_bonus: float = Field(
        default=_EPSILON,
        description="Bonus for discovering hidden/deep-layer PII"
    )
    efficiency_bonus: float = Field(
        default=_EPSILON,
        description="Bonus for completing with steps remaining"
    )
    penalty: float = Field(
        default=_EPSILON,
        description="Penalty for false positives or missed critical secrets"
    )
    total_reward: float = Field(
        ..., description="Sum of all reward components"
    )
    score: float = Field(
        default=_EPSILON,
        description="Task score strictly in (0, 1) — required by OpenEnv validator. Mirrors total_reward, clamped to (EPSILON, 1-EPSILON)."
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed metrics: precision, recall, f1, discovery_rate, etc."
    )
    feedback: str = Field(
        default="", description="Human-readable feedback about this step"
    )

    @model_validator(mode="after")
    def _ensure_strict_scores(self) -> "Reward":
        """
        Guarantee ALL score fields and metrics are strictly between 0 and 1.
        OpenEnv validator is strict: 0.0 and 1.0 are rejected.
        """
        # Clamp top-level floats
        self.redaction_score = max(_EPSILON, min(_MAX_SCORE, self.redaction_score))
        self.discovery_bonus = max(_EPSILON, min(_MAX_SCORE, self.discovery_bonus))
        self.efficiency_bonus = max(_EPSILON, min(_MAX_SCORE, self.efficiency_bonus))
        self.penalty = max(_EPSILON, min(_MAX_SCORE, self.penalty))
        self.total_reward = max(_EPSILON, min(_MAX_SCORE, self.total_reward))
        
        # Sync 'score' field (OpenEnv requirement)
        self.score = self.total_reward
        
        # Recursively clamp metrics
        if self.metrics:
            for k, v in self.metrics.items():
                if isinstance(v, float):
                    self.metrics[k] = max(_EPSILON, min(_MAX_SCORE, v))
        
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "redaction_score": 0.6,
                "discovery_bonus": 0.2,
                "efficiency_bonus": 0.0001,
                "penalty": 0.0001,
                "total_reward": 0.8,
                "score": 0.8,
                "metrics": {
                    "precision": 0.9999,
                    "recall": 0.75,
                    "f1_score": 0.857,
                    "discovery_rate": 0.6,
                    "items_redacted": 6,
                    "items_total": 8,
                },
                "feedback": "Good progress. 6/8 PII items found. Try investigating deeper.",
            }
        }


# ============================================================================
# STEP RESULT
# ============================================================================

class StepResult(BaseModel):
    """Result of a single environment step (Gymnasium-style)."""
    observation: Observation = Field(..., description="Updated observation after action")
    reward: Reward = Field(..., description="Reward for this step")
    terminated: bool = Field(
        ..., description="Whether the episode ended (agent submitted or found everything)"
    )
    truncated: bool = Field(
        ..., description="Whether the episode was cut short (ran out of steps)"
    )
    info: Dict[str, Any] = Field(
        default_factory=dict, description="Diagnostic information"
    )


class ResetResult(BaseModel):
    """Result of environment reset."""
    observation: Observation = Field(..., description="Initial observation")
    info: Dict[str, Any] = Field(
        default_factory=dict, description="Episode metadata"
    )


# ============================================================================
# ENVIRONMENT STATE
# ============================================================================

class EnvironmentState(BaseModel):
    """Full environment state for the /state endpoint."""
    current_observation: Observation = Field(
        ..., description="Current observation"
    )
    episode_step: int = Field(..., description="Current step number")
    total_reward: float = Field(
        default=0.0, description="Cumulative reward this episode"
    )
    action_history: List[Dict[str, Any]] = Field(
        default_factory=list, description="History of actions taken"
    )
    is_running: bool = Field(
        ..., description="Whether an episode is active"
    )
    difficulty: str = Field(default="medium", description="Current difficulty")
    scenario_seed: Optional[int] = Field(
        None, description="Seed used for scenario generation"
    )
