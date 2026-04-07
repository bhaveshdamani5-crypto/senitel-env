"""
Sentinel-Log-Shield: Competition-compliant inference script.
Uses OpenAI client for LLM-based redaction decisions.
Emits structured [START]/[STEP]/[END] logging for automated validation.
"""

import json
import logging
import os
import sys
import re
from typing import Dict, List, Optional
from openai import OpenAI
from models import Observation, RedactionAction, TaskEnum
from env import LogSanitizerEnvironment

# Configure logging for debugging (separate from stdout logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # All debug logs to stderr, leave stdout clean
)
logger = logging.getLogger(__name__)

# Environment variables (competition spec)
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")

# Initialize OpenAI client
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = OpenAI()  # Will use OPENAI_API_KEY env var


class SentinelInferenceAgent:
    """
    SST-compliant inference agent for log redaction.
    Uses gpt-4o-mini for decision-making.
    """
    
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        self.model = model
        self.temperature = temperature
        self.session_num = 0
        logger.info(f"[START] Inference agent initialized with model: {model}")
    
    def process_log(self, observation: Observation) -> RedactionAction:
        """
        Process a log observation and return redaction action.
        
        Args:
            observation: Observation with raw log and task info
        
        Returns:
            RedactionAction with redactions
        """
        self.session_num += 1
        logger.info(f"[START] Processing observation - Session {self.session_num}")
        logger.info(f"Task: {observation.task.value}, Log ID: {observation.log_id}")
        
        # Build prompt based on task
        prompt = self._build_prompt(observation)
        logger.info(f"[STEP] Built prompt for task: {observation.task.value}")
        
        try:
            # Call LLM
            logger.info(f"[STEP] Calling {self.model} for redaction inference")
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a security-focused PII redaction expert. Extract sensitive information from logs and suggest secure redactions. Return JSON format only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=500
            )
            
            logger.info(f"[STEP] Received LLM response")
            response_text = response.choices[0].message.content
            
            # Parse LLM response
            logger.info(f"[STEP] Parsing LLM response")
            redaction_data = self._parse_response(response_text, observation)
            
            # Create action
            action = RedactionAction(
                log_id=observation.log_id,
                redactions=redaction_data["redactions"],
                redacted_log=redaction_data["redacted_log"],
                confidence=redaction_data["confidence"]
            )
            
            logger.info(
                f"[STEP] Generated action - "
                f"Redactions: {len(action.redactions)}, "
                f"Confidence: {action.confidence:.2f}"
            )
            logger.info(f"[END] Inference complete")
            
            return action
        
        except Exception as e:
            logger.error(f"[ERROR] Inference failed: {str(e)}")
            # Fallback: use regex-based redaction
            logger.info(f"[STEP] Falling back to regex-based redaction")
            return self._fallback_redaction(observation)
    
    def _build_prompt(self, observation: Observation) -> str:
        """Build task-specific prompt for LLM."""
        
        base_instruction = f"""
You are a PII redaction specialist. Analyze the following log and identify sensitive information.
Task: {observation.task.value}
Expected PII types: {', '.join(observation.pii_types_expected)}

Log Content:
{observation.raw_log}

Instructions:
1. Identify all PII of the specified types
2. For each PII found, provide: original text, PII type, and suggested redaction mask
3. Return ONLY valid JSON with this exact structure:
{{
    "redactions": [
        {{"type": "<type>", "original": "<original_text>", "redaction_mask": "[REDACTED_<TYPE>]"}},
        ...
    ],
    "confidence": <0.0-1.0>
}}
4. Be strict about accuracy - only mark clear PII
5. Confidence reflects your certainty in the findings
"""
        
        # Task-specific instructions
        if observation.task == TaskEnum.TASK_1:
            base_instruction += """
Task-specific guidance for TASK_1:
- Email: Look for patterns like name@domain.extension
- IPv4: Look for patterns like xxx.xxx.xxx.xxx where xxx is 0-255
"""
        elif observation.task == TaskEnum.TASK_2:
            base_instruction += """
Task-specific guidance for TASK_2:
- Username: Extract names in quotes after 'User', e.g., User 'John'
- Look for contextual clues: "Error", "Failed", "Debug", etc.
- Focus on proper names
"""
        elif observation.task == TaskEnum.TASK_3:
            base_instruction += """
Task-specific guidance for TASK_3:
- Auth tokens: sk_* patterns, long alphanumeric strings in sensitive contexts
- Secrets: strings assigned to variables named 'secret', 'key', 'api_key', 'password', 'token'
- High-entropy strings: 20+ character alphanumeric sequences
- Focus on high-risk leakage (secrets are CRITICAL to identify)
"""
        
        return base_instruction
    
    def _parse_response(self, response_text: str, observation: Observation) -> Dict:
        """Parse LLM response and convert to redaction data."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                logger.warning("No JSON found in response, using regex fallback")
                return self._regex_fallback_redaction(observation)
            
            response_json = json.loads(json_match.group())
            
            # Build redacted log
            redacted_log = observation.raw_log
            redactions = []
            
            for item in response_json.get("redactions", []):
                original = item.get("original", "")
                mask = item.get("redaction_mask", "[REDACTED]")
                
                if original in redacted_log:
                    redacted_log = redacted_log.replace(original, mask)
                    redactions.append({
                        "type": item.get("type", "unknown"),
                        "original": original,
                        "redacted": mask
                    })
            
            confidence = min(1.0, max(0.0, response_json.get("confidence", 0.5)))
            
            return {
                "redactions": redactions,
                "redacted_log": redacted_log,
                "confidence": confidence
            }
        
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse JSON response: {str(e)}")
            return self._regex_fallback_redaction(observation)
    
    def _falls_back_redaction(self, observation: Observation) -> RedactionAction:
        """Fallback: regex-based redaction."""
        logger.info("Using regex-based redaction")
        return RedactionAction(
            log_id=observation.log_id,
            redactions=self._extract_pii_regex(observation),
            redacted_log=self._apply_regex_redaction(observation),
            confidence=0.6
        )
    
    def _regex_fallback_redaction(self, observation: Observation) -> Dict:
        """Regex-based extraction fallback."""
        redactions = []
        redacted_log = observation.raw_log
        
        # Task 1: Email + IPv4
        if observation.task == TaskEnum.TASK_1:
            # Email
            emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', observation.raw_log)
            for email in emails:
                redactions.append({
                    "type": "email",
                    "original": email,
                    "redacted": "[REDACTED_EMAIL]"
                })
                redacted_log = redacted_log.replace(email, "[REDACTED_EMAIL]")
            
            # IPv4
            ipv4s = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', observation.raw_log)
            for ip in ipv4s:
                redactions.append({
                    "type": "ipv4",
                    "original": ip,
                    "redacted": "[REDACTED_IP]"
                })
                redacted_log = redacted_log.replace(ip, "[REDACTED_IP]")
        
        # Task 2: Username
        elif observation.task == TaskEnum.TASK_2:
            usernames = re.findall(r"User\s+'([A-Za-z]+)'", observation.raw_log)
            for name in usernames:
                redactions.append({
                    "type": "username",
                    "original": name,
                    "redacted": "[REDACTED_USER]"
                })
                redacted_log = redacted_log.replace(f"'{name}'", "'[REDACTED_USER]'")
        
        # Task 3: Secrets
        elif observation.task == TaskEnum.TASK_3:
            # Tokens
            tokens = re.findall(r'\bsk_[a-z0-9_]{20,}\b', observation.raw_log, re.IGNORECASE)
            for token in tokens:
                redactions.append({
                    "type": "token",
                    "original": token,
                    "redacted": "[REDACTED_TOKEN]"
                })
                redacted_log = redacted_log.replace(token, "[REDACTED_TOKEN]")
        
        return {
            "redactions": redactions,
            "redacted_log": redacted_log,
            "confidence": 0.65
        }
    
    def _fallback_redaction(self, observation: Observation) -> RedactionAction:
        """Return fallback action on LLM error."""
        data = self._regex_fallback_redaction(observation)
        return RedactionAction(
            log_id=observation.log_id,
            redactions=data["redactions"],
            redacted_log=data["redacted_log"],
            confidence=data["confidence"]
        )


def run_episode(task_name: Optional[str] = None) -> Dict:
    """
    Run a single episode and emit [START]/[STEP]/[END] logs.
    
    Args:
        task_name: Specific task to run (or None for random)
    
    Returns:
        Episode result with score and rewards
    """
    # Initialize environment and agent
    env = LogSanitizerEnvironment()
    agent = SentinelInferenceAgent(model=MODEL_NAME)
    
    # Reset environment
    reset_resp = env.reset()
    task = reset_resp.observation.task
    
    # Emit [START] log
    print(f"[START] task={task.value} env=sentinel-log-shield model={MODEL_NAME}")
    
    episode_rewards = []
    step_num = 0
    success = False
    last_error = None
    
    try:
        # Run episode steps
        for step_num in range(1, env.max_steps + 1):
            obs = env.state().current_observation
            
            try:
                # Agent processes observation
                action = agent.process_log(obs)
                
                # Execute environment step
                step_resp = env.step(action)
                reward = step_resp.reward.total_reward
                done = step_resp.done
                
                # Store reward
                episode_rewards.append(reward)
                
                # Format action summary for log
                action_summary = f"redact_{len(action.redactions)}_{task.value}"
                
                # Emit [STEP] log (exact format specified in competition)
                print(f"[STEP] step={step_num} action={action_summary} reward={reward:.2f} done={'true' if done else 'false'} error=null")
                
                if done:
                    success = True
                    break
            
            except Exception as e:
                last_error = str(e)
                reward = -1.0
                episode_rewards.append(reward)
                print(f"[STEP] step={step_num} action=error reward={reward:.2f} done=true error={last_error}")
                break
    
    except Exception as e:
        last_error = str(e)
        success = False
    
    # Calculate final score (average of rewards, normalized)
    final_score = 0.0
    if episode_rewards:
        # Normalize score to [0, 1]
        avg_reward = sum(episode_rewards) / len(episode_rewards)
        final_score = max(0.0, min(1.0, (avg_reward + 1.0) / 2.0))  # Map [-1, 1] to [0, 1]
    
    # Emit [END] log (exact format specified in competition)
    rewards_str = ",".join([f"{r:.2f}" for r in episode_rewards])
    print(f"[END] success={'true' if success else 'false'} steps={step_num} score={final_score:.2f} rewards={rewards_str}")
    
    return {
        "task": task.value,
        "success": success,
        "steps": step_num,
        "score": final_score,
        "rewards": episode_rewards,
        "final_reward": episode_rewards[-1] if episode_rewards else 0.0
    }


def main():
    """Run inference on all 3 tasks."""
    logger.info("Starting Sentinel-Log-Shield inference", extra={"to_stderr": True})
    
    # Run one episode per task (or multiple for better averaging)
    num_runs = int(os.getenv("NUM_RUNS", "1"))
    
    all_results = {
        TaskEnum.TASK_1.value: [],
        TaskEnum.TASK_2.value: [],
        TaskEnum.TASK_3.value: []
    }
    
    try:
        # Run episodes
        for run in range(num_runs):
            for task_num, task_name in enumerate([TaskEnum.TASK_1.value, TaskEnum.TASK_2.value, TaskEnum.TASK_3.value], 1):
                result = run_episode(task_name=task_name)
                all_results[task_name].append(result)
                
                # Small delay between episodes
                if run < num_runs - 1:
                    pass  # No need for delay in sequential execution
        
        # Log summary to stderr (debug info)
        logger.info(f"Completed {num_runs} runs across 3 tasks")
        for task_name, results in all_results.items():
            avg_score = sum(r["score"] for r in results) / len(results) if results else 0.0
            logger.info(f"  {task_name}: avg_score={avg_score:.2f}")
    
    except Exception as e:
        logger.error(f"Error during inference: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
