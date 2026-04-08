# Pre-Submission Checklist for Hackathon Judges

Use this checklist before submitting your project to hackathon.

---

## ✅ Code Quality & Correctness

- [ ] All tests pass: `python -m pytest tests/ -v` → 4 passed
- [ ] Demo runs without errors: `python demo.py` → Shows full episode
- [ ] No crashes on edge cases
- [ ] Proper error handling in server.py
- [ ] Environment variable defaults work
- [ ] Deterministic grading (same seed = same score)

**How to verify:**

```bash
python -m pytest tests/ -v            # Tests must pass
python demo.py                         # Demo must complete
echo $PYTHONPATH; python demo.py      # Verify imports work
```

---

## ✅ OpenEnv Compliance

- [ ] `SentinelEnvironment.reset()` implemented ✅ Returns `ResetResult`
- [ ] `SentinelEnvironment.step()` implemented ✅ Returns `StepResult`
- [ ] `SentinelEnvironment.state()` implemented ✅ Returns `EnvironmentState`
- [ ] `openenv.yaml` matches implementation
- [ ] All action types (SCAN, INVESTIGATE, REDACT, SUBMIT) work
- [ ] Observation schema is consistent
- [ ] Reward computation is transparent

**How to verify:**

```python
from env import SentinelEnvironment
env = SentinelEnvironment()
result = env.reset(difficulty="easy", seed=42)
assert result.observation is not None
assert result.info is not None
```

---

## ✅ LLM Baseline

- [ ] `inference.py` uses LLM (no regex fallback)
- [ ] HF_TOKEN required (environment variable enforced)
- [ ] Retry logic implemented (3 attempts, exponential backoff)
- [ ] Timeout handling (30 second default)
- [ ] Deterministic (seed-based reproducibility)
- [ ] Benchmark mode working: `--seeds 5 --seed-start 0`
- [ ] Output format has [START], [STEP], [END] markers

**How to verify:**

```bash
# Must fail without token
unset HF_TOKEN
python inference.py 2>&1 | grep -i "required|error"  # Should show error

# Must succeed with token
export HF_TOKEN="hf_YourToken"
python inference.py --seeds 1
```

---

## ✅ Grading Logic

- [ ] Grading is deterministic (same input = same output)
- [ ] F1 score calculated correctly
- [ ] Discovery rate based on hidden ground truth
- [ ] Efficiency bonus applied properly
- [ ] Secret penalties enforced
- [ ] Scoring explained in README

**How to verify:**

```python
from grader import InvestigationGrader
# Test same redacted set twice
metrics1 = InvestigationGrader.compute_metrics(redacted, truth, discovered, steps, budget, secrets)
metrics2 = InvestigationGrader.compute_metrics(redacted, truth, discovered, steps, budget, secrets)
assert metrics1 == metrics2  # Should be identical
```

---

## ✅ Documentation

- [ ] README is comprehensive (covers all judgment criteria)
- [ ] Examples show how to run locally
- [ ] API documentation is clear (what endpoints exist)
- [ ] Deployment instructions included
- [ ] Design decisions explained (why this task?)
- [ ] Known limitations documented (if any)

**Specific sections judges look for:**

- [ ] "What Makes This Real RL?" → Explains genuine RL properties
- [ ] "How It Works" → Clear walkthrough
- [ ] "Quick Start" → Get running in < 5 min
- [ ] "Baseline Performance" → Shows reproducible results
- [ ] "Architecture" → Clean, modular structure

---

## ✅ File Organization

```
senitel-env/
├── env.py ......................... ✅ 600+ lines, well-documented
├── models.py ...................... ✅ Pydantic schemas
├── grader.py ...................... ✅ Deterministic scoring
├── inference.py ................... ✅ LLM baseline, no regex fallback
├── server.py ...................... ✅ FastAPI server, error handling
├── demo.py ........................ ✅ Standalone demo
├── openenv.yaml ................... ✅ Full specification
├── Dockerfile ..................... ✅ For HF Spaces
├── requirements.txt ............... ✅ 9 lightweight packages
├── README.md ...................... ✅ Comprehensive judge-facing docs
├── HF_SPACES_DEPLOYMENT.md ........ ✅ Deployment instructions
├── LICENSE ........................ ✅ MIT
├── pytest.ini ..................... ✅ Test configuration
└── tests/
    ├── test_env_tasks.py ......... ✅ 2 tests
    └── test_smoke.py ............. ✅ 2 tests

└── senitel-env-deploy/ ........... ✅ Mirror folder (identical to root)
```

---

## ✅ Dependency Validation

Ensure dependencies are lightweight and necessary:

```bash
pip freeze | wc -l
# Should be < 50 packages (including transitive deps)

# Core dependencies (must have):
python -c "import fastapi, pydantic, openai, openenv"
# Should succeed

# No heavy ML frameworks:
python -c "import tensorflow" 2>&1 | grep -i "no module"
# Should say "not found" (that's good)
```

---

## ✅ Performance Baseline

Before submitting, run and record:

```bash
export HF_TOKEN="hf_YourToken"

# 1. Single episode completeness
python demo.py | tail -5
# Should show [END] with score

# 2. Benchmark consistency
python inference.py --seeds 3 --seed-start 0
# Should show mean ± std with consistent formatting

# 3. API latency
time curl -X POST "http://localhost:7860/reset?difficulty=easy"
# Should respond in < 5 seconds
```

**Target stats:**

- Reset: < 1 second
- Step: 1-3 seconds
- Full episode (8 steps): < 30 seconds
- API response: < 5 seconds

---

## ✅ Error Handling

Test edge cases:

```bash
# 1. Invalid action
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "invalid"}' \
  2>&1 | grep -i "error|invalid"
# Should return proper error

# 2. Missing required field
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "investigate"}'
# Should return error about missing target

# 3. Out of budget
# (Manually play until budget = 0, then step)
# Should return "Episode terminated" or similar
```

---

## ✅ Reproducibility

Verify deterministic behavior:

```bash
# Run episode with seed twice
python -c "
from env import SentinelEnvironment
from inference import run_episode

seed = 42
result1 = run_episode(difficulty='easy', seed=seed)
result2 = run_episode(difficulty='easy', seed=seed)

print(f'Score 1: {result1[\"total_score\"]:.4f}')
print(f'Score 2: {result2[\"total_score\"]:.4f}')
print(f'Match: {result1[\"total_score\"] == result2[\"total_score\"]}')
"
# Both scores must match exactly
```

---

## ✅ OpenEnv Validator

If available, test with OpenEnv CLI:

```bash
# Check specification compliance
python -m openenv.cli validate
# Should return: "valid" or list any errors

# Run environment check
python -m openenv.cli check env.SentinelEnvironment
# Should verify: reset(), step(), state() implemented correctly
```

---

## ✅ Git & Repository

Before pushing to hackathon:

- [ ] No secrets committed (HF_TOKEN, API keys)
- [ ] `.gitignore` excludes `__pycache__`, `.venv`, etc.
- [ ] Commit message is clear
- [ ] README links are correct
- [ ] GitHub repo is public
- [ ] License is MIT

```bash
# Verify no secrets
git log --all --oneline | xargs git show | grep -i "hf_\|sk_\|ghp_"
# Should return nothing

# Verify public access
curl -s https://api.github.com/repos/<username>/senitel-env | grep -c "public"
# Should return "1"
```

---

## ✅ Submission Checklist

When ready to submit to hackathon:

1. [ ] All tests pass locally
2. [ ] Demo runs successfully: `python demo.py`
3. [ ] Benchmark completes: `python inference.py --seeds 3`
4. [ ] README is complete and judge-facing
5. [ ] GitHub repo is public and clean
6. [ ] HF Space is deployed and working
7. [ ] No secrets in repository
8. [ ] Dockerfile works locally: `docker build .`
9. [ ] All files synced (root + senitel-env-deploy/)
10. [ ] Submission deadline noted

---

## ✅ Judge-Facing Presentation

Your submission should make it easy for judges to evaluate:

**In README:**

- [ ] "Quick Summary" section (< 100 words) at top
- [ ] "How to Evaluate" section with clear steps
- [ ] Hackathon criteria checklist (✅ shows compliance)
- [ ] Link to HF Space
- [ ] Link to GitHub
- [ ] Baseline performance table

**In HF Space:**

- [ ] Working REST API
- [ ] `/docs` shows all endpoints
- [ ] `/` shows interactive demo
- [ ] No console errors when accessed

**In code:**

- [ ] Clear docstrings on all public methods
- [ ] Inline comments explaining complex logic
- [ ] Proper logging (judges can debug)
- [ ] Type hints everywhere

---

## 🎯 Final Sanity Check

Run this before submitting:

```bash
#!/bin/bash
set -e
echo "1. Running tests..."
python -m pytest tests/ -v

echo "2. Running demo..."
python demo.py > /tmp/demo_output.log 2>&1 && echo "✅ Demo pass" || echo "❌ Demo fail"

echo "3. Checking files..."
for f in env.py models.py grader.py server.py inference.py demo.py; do
  [ -f "$f" ] && echo "✅ $f" || echo "❌ $f missing"
done

echo "4. Checking documentation..."
[ -f "README.md" ] && wc -l README.md || echo "❌ README missing"

echo "5. All checks passed! ✅"
```

---

## 🚀 GO! Submit Your Project

You're ready when:

- ✅ All tests pass
- ✅ Demo works locally
- ✅ README is comprehensive
- ✅ HF Space is deployed
- ✅ GitHub is public
- ✅ No secrets committed

**Submit to hackathon with:**

- GitHub repo link
- HF Space URL
- Brief description of your approach

Good luck! 🎉
