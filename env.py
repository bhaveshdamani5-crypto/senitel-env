"""
Sentinel-Log-Shield: Core OpenEnv environment.
Implements step(), reset(), state() for log sanitization with 3 difficulty levels.
"""

import re
import random
import uuid
from typing import Dict, List, Tuple, Optional
from models import (
    Observation, RedactionAction, Reward, TaskEnum,
    StepResponse, ResetResponse, EnvironmentState
)
from grader import RedactionGrader


class LogSanitizerEnvironment:
    """
    SST-compliant OpenEnv environment for PII redaction.
    
    Tasks:
    - Task 1 (Easy): Email + IPv4 detection and redaction
    - Task 2 (Medium): Username extraction from conversational logs
    - Task 3 (Hard): High-entropy secrets/tokens detection
    """
    
    # Sample logs for each task
    TASK_1_LOGS = [
        "User alice.smith@company.com logged in from 10.0.0.5 at 14:30 UTC",
        "Error: Email contact@service.io failed validation. IP: 172.16.254.1",
        "Admin report: user.test@domain.org accessed DB from 192.168.100.50",
        "Alert: Multiple login attempts from john.email@mail.net (IP: 203.0.113.42)",
        "System: Backup completed. Admin: supervisor@corp.com, Server: 192.0.2.1",
    ]
    
    TASK_2_LOGS = [
        "Error: User 'Bhavesh' failed login attempt after 3 tries",
        "Debug: User 'Sarah' triggered exception in auth module",
        "Info: User 'Mike' successfully renewed session token",
        "Warning: User 'Jennifer' exceeded rate limit on API calls",
        "Critical: User 'David' tried unauthorized database access",
    ]
    
    TASK_3_LOGS = [
        "Traceback (most recent call last): sk_live_51234567890abcdef in auth.py line 42",
        "Stack trace: Token MIIEvQIBADANBgkq invalid in crypto module (line 89)",
        "Error log: Secret key AKIAIOSFODNN7EXAMPLE exposed in config.py:15",
        "Debug dump: aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "Exception: API key xsecret_1234567890abcdefghijklmnop leaked in request",
    ]
    
    def __init__(self):
        """Initialize the environment."""
        self.current_task = None
        self.current_log = None
        self.current_log_id = None
        self.episode_step = 0
        self.cumulative_reward = 0.0
        self.max_steps = 10
        self.task_history = []
        self.is_running = False
        
    def reset(self) -> ResetResponse:
        """Reset the environment and return initial observation."""
        self.episode_step = 0
        self.cumulative_reward = 0.0
        self.task_history = []
        self.is_running = True
        
        # Randomly select task and log
        task = random.choice(list(TaskEnum))
        self.current_task = task
        self.current_log_id = str(uuid.uuid4())[:8]
        
        if task == TaskEnum.TASK_1:
            self.current_log = random.choice(self.TASK_1_LOGS)
            pii_types = ["email", "ipv4"]
        elif task == TaskEnum.TASK_2:
            self.current_log = random.choice(self.TASK_2_LOGS)
            pii_types = ["username"]
        else:  # TASK_3
            self.current_log = random.choice(self.TASK_3_LOGS)
            pii_types = ["token", "secret", "api_key"]
        
        observation = Observation(
            task=task,
            raw_log=self.current_log,
            pii_types_expected=pii_types,
            log_id=self.current_log_id
        )
        
        return ResetResponse(observation=observation, info={"reset": True})
    
    def step(self, action: RedactionAction) -> StepResponse:
        """Process redaction action and return step response."""
        if not self.is_running:
            raise ValueError("Episode not running. Call reset() first.")
        
        self.episode_step += 1
        
        # Evaluate the redaction quality
        reward_info = self._evaluate_redaction(action)
        reward_value = reward_info["total_reward"]
        
        self.cumulative_reward += reward_value
        
        # Record in history
        self.task_history.append({
            "step": self.episode_step,
            "task": self.current_task.value,
            "action": action.dict(),
            "reward": reward_value,
            "metrics": reward_info["metrics"]
        })
        
        # Check if episode is done
        done = self.episode_step >= self.max_steps
        
        if done:
            self.is_running = False
        
        # Generate next observation (or same if not done)
        if not done:
            next_obs = Observation(
                task=self.current_task,
                raw_log=self.current_log,
                pii_types_expected=[],  # Agent should learn from feedback
                log_id=self.current_log_id
            )
        else:
            # Reset for next episode on done
            reset_resp = self.reset()
            next_obs = reset_resp.observation
        
        reward = Reward(
            base_reward=reward_info["base_reward"],
            penalties=reward_info["penalties"],
            total_reward=reward_value,
            metrics=reward_info["metrics"],
            feedback=reward_info["feedback"]
        )
        
        return StepResponse(
            observation=next_obs,
            reward=reward,
            done=done,
            info={
                "episode_step": self.episode_step,
                "cumulative_reward": self.cumulative_reward,
                "task": self.current_task.value if not done else "new_task"
            }
        )
    
    def state(self) -> EnvironmentState:
        """Return current environment state."""
        obs = Observation(
            task=self.current_task,
            raw_log=self.current_log,
            pii_types_expected=[],
            log_id=self.current_log_id
        )
        
        return EnvironmentState(
            current_observation=obs,
            episode_step=self.episode_step,
            cumulative_reward=self.cumulative_reward,
            task_history=self.task_history,
            is_running=self.is_running
        )
    
    def _evaluate_redaction(self, action: RedactionAction) -> Dict:
        """
        Evaluate redaction quality using RedactionGrader.
        
        Uses F1-score with reward shaping:
        - +1.0 (perfect): F1 = 1.0
        - +0.8 (excellent): Recall ≥0.9, Precision ≥0.8
        - +0.5 (good): F1 ≥ 0.6
        - +0.2 (partial): Otherwise
        - -1.0 (critical): Missed secrets in Task 3
        - -0.3 (penalty): Over-redacting >20% non-PII
        """
        return RedactionGrader.grade(action.redactions, self.current_log, self.current_task)
