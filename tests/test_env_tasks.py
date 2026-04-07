from env import LogSanitizerEnvironment
from models import RedactionAction, TaskEnum


def _build_action(env: LogSanitizerEnvironment, redactions: list[dict]) -> RedactionAction:
    return RedactionAction(
        log_id=env.current_log_id,
        redactions=redactions,
        redacted_log=env.current_log,
        confidence=0.9 if redactions else 0.3,
    )


def test_task_1_perfect_reward():
    env = LogSanitizerEnvironment()
    env.reset()
    env.current_task = TaskEnum.TASK_1
    env.current_log = "User alice.smith@company.com logged in from 10.0.0.5 at 14:30 UTC"
    action = _build_action(
        env,
        [
            {"type": "email", "original": "alice.smith@company.com", "redacted": "[EMAIL_REDACTED]"},
            {"type": "ipv4", "original": "10.0.0.5", "redacted": "[IP_REDACTED]"},
        ],
    )
    step = env.step(action)
    assert step.reward.metrics["f1_score"] == 1.0
    assert step.reward.total_reward >= 1.0


def test_task_2_perfect_reward():
    env = LogSanitizerEnvironment()
    env.reset()
    env.current_task = TaskEnum.TASK_2
    env.current_log = "Error: User 'Bhavesh' failed login attempt after 3 tries"
    action = _build_action(
        env,
        [{"type": "username", "original": "Bhavesh", "redacted": "[USER_REDACTED]"}],
    )
    step = env.step(action)
    assert step.reward.metrics["f1_score"] == 1.0
    assert step.reward.total_reward >= 1.0


def test_task_3_missed_secret_penalty():
    env = LogSanitizerEnvironment()
    env.reset()
    env.current_task = TaskEnum.TASK_3
    env.current_log = "Traceback (most recent call last): sk_live_51234567890abcdef in auth.py line 42"
    action = _build_action(env, [])
    step = env.step(action)
    assert "missed_secrets" in step.reward.penalties
    assert step.reward.penalties["missed_secrets"] <= -1.0
