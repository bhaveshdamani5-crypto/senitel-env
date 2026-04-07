import json
import time
import unittest

from fastapi.testclient import TestClient

from server import app


def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": "ae233e",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open("debug-ae233e.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


class TestSpaceSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # #region agent log
        _debug_log(
            run_id="baseline",
            hypothesis_id="H1",
            location="tests/test_smoke.py:setUpClass",
            message="Smoke test client initialized",
            data={"app_title": app.title},
        )
        # #endregion

    def test_space_routes(self):
        status = {}
        for route in ["/", "/demo", "/docs", "/redoc", "/health"]:
            resp = self.client.get(route, follow_redirects=True)
            status[route] = resp.status_code
            self.assertEqual(resp.status_code, 200)
        # #region agent log
        _debug_log(
            run_id="baseline",
            hypothesis_id="H2",
            location="tests/test_smoke.py:test_space_routes",
            message="Space routes tested",
            data={"status_map": status},
        )
        # #endregion

    def test_episode_endpoints(self):
        reset_resp = self.client.post("/reset")
        self.assertEqual(reset_resp.status_code, 200)
        observation = reset_resp.json()["observation"]

        action = {
            "log_id": observation["log_id"],
            "redactions": [],
            "redacted_log": observation["raw_log"],
            "confidence": 0.5,
        }
        step_resp = self.client.post("/step", json=action)
        self.assertEqual(step_resp.status_code, 200)
        state_resp = self.client.get("/state")
        self.assertEqual(state_resp.status_code, 200)
        # #region agent log
        _debug_log(
            run_id="baseline",
            hypothesis_id="H3",
            location="tests/test_smoke.py:test_episode_endpoints",
            message="Episode flow tested",
            data={
                "reset_status": reset_resp.status_code,
                "step_status": step_resp.status_code,
                "state_status": state_resp.status_code,
            },
        )
        # #endregion


if __name__ == "__main__":
    unittest.main()
