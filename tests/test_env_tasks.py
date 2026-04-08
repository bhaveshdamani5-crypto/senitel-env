import re

from env import SentinelEnvironment
from models import AgentAction, ActionType


PHONE_RE = re.compile(r"^\+\d{1,3}-\d{3}-\d{3}-\d{4}$")


def _collect_pii_entities(obs):
    # entities are already ground-truth items discovered via env scan/investigate
    return list(obs.discovered_entities)


def test_easy_episode_can_finish_and_scores_in_range():
    env = SentinelEnvironment()
    env.reset(difficulty="easy", seed=1)

    scan = env.step(AgentAction(action_type=ActionType.SCAN))
    obs = scan.observation

    # Do at most 2 investigates to avoid dead-end penalties dominating
    for _ in range(2):
        if obs.steps_remaining <= 2 or not obs.investigation_targets:
            break
        inv = env.step(AgentAction(action_type=ActionType.INVESTIGATE, target_entity=obs.investigation_targets[0]))
        obs = inv.observation
        if inv.terminated or inv.truncated:
            break

    # Redact all discovered entities (includes phones/tokens if visible)
    if obs.steps_remaining > 1:
        redactions = []
        for e in _collect_pii_entities(obs):
            if "@" in e:
                t = "email"
            elif PHONE_RE.match(e):
                t = "phone"
            elif re.match(r"^\d{1,3}(\.\d{1,3}){3}$", e):
                t = "ip"
            else:
                t = "token" if len(e) > 15 else "username"
            redactions.append({"original": e, "type": t})

        env.step(AgentAction(action_type=ActionType.REDACT, redactions=redactions))

    submit = env.step(AgentAction(action_type=ActionType.SUBMIT))
    score = submit.reward.metrics.get("total_score", 0.0)
    assert 0.0 <= score <= 1.0


def test_honeypot_investigation_penalizes():
    env = SentinelEnvironment()
    env.reset(difficulty="hard", seed=2)

    # Find a honeypot by scanning then trying any obvious decoy (admin/root/etc)
    env.step(AgentAction(action_type=ActionType.SCAN))
    # the scenario stores honeypots explicitly; this is a whitebox test for environment behavior
    honeypots = list(getattr(env.scenario, "honeypots", set()))
    assert honeypots, "Expected honeypots to be generated"

    res = env.step(AgentAction(action_type=ActionType.INVESTIGATE, target_entity=honeypots[0]))
    assert res.reward.total_reward < 0
    assert "Honeypot" in (res.reward.feedback or "")

