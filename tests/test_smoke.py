from env import SentinelEnvironment
from models import AgentAction, ActionType


def test_env_reset_and_basic_step_flow():
    env = SentinelEnvironment()
    reset = env.reset(difficulty="easy", seed=123)

    assert reset.observation.steps_remaining > 0
    assert len(reset.observation.visible_logs) > 0
    assert reset.observation.total_pii_to_find > 0

    # scan should discover at least something (unless only decoys visible, but surface has real PII templates too)
    scan = env.step(AgentAction(action_type=ActionType.SCAN))
    assert scan.observation.steps_used == 1
    assert scan.observation.steps_remaining >= 0
    assert isinstance(scan.observation.discovered_entities, list)

    # investigate (if there is a target) should not crash
    if scan.observation.investigation_targets:
        inv = env.step(
            AgentAction(
                action_type=ActionType.INVESTIGATE,
                target_entity=scan.observation.investigation_targets[0],
            )
        )
        assert isinstance(inv.observation.visible_logs, list)


def test_server_imports():
    # validator expects importable app/main entrypoints
    from server.app import app, main  # noqa: F401
    assert app is not None
    assert callable(main)

