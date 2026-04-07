"""
Sentinel-Log-Shield: Pydantic models for observation, action, and reward.
Defines the interfaces for SST-compliant OpenEnv environment.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum


class TaskEnum(str, Enum):
    """Difficulty levels for redaction tasks."""
    TASK_1 = "task_1"  # Email + IPv4
    TASK_2 = "task_2"  # Username from logs
    TASK_3 = "task_3"  # Auth tokens/secrets


class Observation(BaseModel):
    """Observation from the environment: raw log content and task specification."""
    task: TaskEnum = Field(..., description="Difficulty level (task_1, task_2, task_3)")
    raw_log: str = Field(..., description="Raw system log with potential PII")
    pii_types_expected: List[str] = Field(
        default_factory=list,
        description="Expected PII types to redact: ['email', 'ipv4', 'username', 'token', 'ssn']"
    )
    log_id: str = Field(..., description="Unique identifier for this log")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task": "task_1",
                "raw_log": "User john.doe@example.com connected from 192.168.1.1",
                "pii_types_expected": ["email", "ipv4"],
                "log_id": "log_001"
            }
        }


class RedactionAction(BaseModel):
    """Action taken by the agent: specify what to redact."""
    log_id: str = Field(..., description="ID of the log being processed")
    redactions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of redactions: [{'type': 'email', 'original': '...', 'redacted': '...'}]"
    )
    redacted_log: str = Field(..., description="Final redacted log content")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Agent's confidence in the redactions (0.0-1.0)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "log_id": "log_001",
                "redactions": [
                    {
                        "type": "email",
                        "original": "john.doe@example.com",
                        "redacted": "[REDACTED_EMAIL]"
                    },
                    {
                        "type": "ipv4",
                        "original": "192.168.1.1",
                        "redacted": "[REDACTED_IP]"
                    }
                ],
                "redacted_log": "User [REDACTED_EMAIL] connected from [REDACTED_IP]",
                "confidence": 0.95
            }
        }


class Reward(BaseModel):
    """Reward signal: accuracy, penalties, and quality metrics."""
    base_reward: float = Field(
        ...,
        description="Base reward: +0.2 for partial, variable for full accuracy"
    )
    penalties: Dict[str, float] = Field(
        default_factory=dict,
        description="Penalties: -1.0 for missed high-risk secrets, -0.3 for over-redacting"
    )
    total_reward: float = Field(..., description="Final reward = base + sum(penalties)")
    metrics: Dict[str, float] = Field(
        default_factory=dict,
        description="Quality metrics: precision, recall, f1_score, over_redaction_ratio"
    )
    feedback: str = Field(
        default="",
        description="Human-readable feedback on the redaction quality"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "base_reward": 0.9,
                "penalties": {"missed_secrets": -0.5},
                "total_reward": 0.4,
                "metrics": {
                    "precision": 0.95,
                    "recall": 0.85,
                    "f1_score": 0.90,
                    "over_redaction_ratio": 0.05
                },
                "feedback": "Good email detection. Consider improving token detection."
            }
        }


class StepResponse(BaseModel):
    """Response from environment.step(): observation, reward, done flag."""
    observation: Observation = Field(..., description="Next observation")
    reward: Reward = Field(..., description="Reward for the action")
    done: bool = Field(..., description="Episode termination flag")
    info: Dict = Field(
        default_factory=dict,
        description="Diagnostic information"
    )


class ResetResponse(BaseModel):
    """Response from environment.reset(): initial observation and info."""
    observation: Observation = Field(..., description="Initial observation")
    info: Dict = Field(
        default_factory=dict,
        description="Diagnostic information"
    )


class EnvironmentState(BaseModel):
    """Current state of the environment."""
    current_observation: Observation = Field(..., description="Current observation")
    episode_step: int = Field(..., description="Current step in episode")
    cumulative_reward: float = Field(..., description="Total reward accumulated")
    task_history: List[Dict] = Field(
        default_factory=list,
        description="History of completed tasks"
    )
    is_running: bool = Field(..., description="Whether an episode is active")
