---
title: Sentinel-Log-Shield OpenEnv Environment
emoji: 🔐
colorFrom: indigo
colorTo: purple
sdk: docker
pinned: false
---

# Sentinel-Log-Shield v2

**Interactive Security Investigation RL Environment — Built for OpenEnv**

[![Python](https://img.shields.io/badge/python-3.10+-blue)](#)
[![FastAPI](https://img.shields.io/badge/api-fastapi-009688)](#)
[![OpenEnv](https://img.shields.io/badge/framework-openenv-orange)](#)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

## What Makes This a Real RL Environment

Unlike classification tasks wrapped in `step()`, this environment has **genuine RL dynamics**:

| RL Property | Implementation |
|---|---|
| **State transitions** | Investigating entity X reveals connected logs and hidden entities |
| **Sequential decisions** | Each discovery opens new investigation paths |
| **Hidden information** | Secrets are buried in deep layers — only found through multi-step investigation |
| **Strategy required** | Limited step budget forces explore vs. exploit tradeoffs |
| **Procedural generation** | Every episode is unique — 50+ templates, random PII pools, entity graphs |
| **Non-trivial optimal policy** | Agent must learn when to scan, what to investigate, and when to stop |

## How It Works

The agent plays a **security analyst investigating a data breach**. The environment procedurally generates a scenario with users, IPs, emails, and hidden secrets linked through an entity graph.

```
reset() → Agent sees initial alert logs (surface layer)
   ↓
step(SCAN) → Extracts visible PII entities from current logs
   ↓
step(INVESTIGATE, "alice") → Reveals logs connected to "alice"
   ↓                          (may expose hidden tokens/secrets)
step(INVESTIGATE, "10.0.0.5") → Reveals logs from that IP
   ↓                             (may connect to other users)
step(REDACT, [...]) → Submits discovered PII for scoring
   ↓
step(SUBMIT) → Ends episode, receives comprehensive score
```

**Key constraint:** The agent has a **limited step budget** (8-12 steps depending on difficulty). Surface scanning finds ~40% of PII. Full investigation finds 100%. The agent must decide: explore deeper or submit early?

## Action Space

| Action | Description | Parameters |
|---|---|---|
| `SCAN` | Extract PII from visible logs | None |
| `INVESTIGATE` | Deep-dive into entity → reveals connected logs | `target_entity` |
| `REDACT` | Submit PII items for scoring | `redactions: [{original, type}]` |
| `SUBMIT` | End episode, receive final score | None |

## Observation Space

| Field | Description |
|---|---|
| `visible_logs` | Log entries currently visible to the agent |
| `discovered_entities` | PII entities found so far |
| `investigation_targets` | Entities available for investigation |
| `steps_remaining` | Budget countdown |
| `total_pii_to_find` | How many PII items exist in this scenario |
| `pii_found_count` | Items correctly redacted so far |
| `hint` | Environment guidance |

## Reward Structure

| Component | Weight | Description |
|---|---|---|
| F1 Score | 70% | Precision/Recall of redacted vs ground truth |
| Discovery Rate | 20% | Fraction of total PII the agent discovered |
| Recall | 10% | Raw coverage |
| Efficiency Bonus | +5% per step saved | Reward for completing under budget |
| Secret Penalty | -30% per missed | Critical penalty for each missed secret |

## Difficulty Levels

| Level | Users | Layers | Budget | Secrets | Description |
|---|---|---|---|---|---|
| Easy | 2 | 2 | 12 | 1 | Shallow investigation, generous budget |
| Medium | 3 | 3 | 10 | 2 | Moderate depth, balanced budget |
| Hard | 4 | 4 | 8 | 3 | Deep investigation, tight budget |

## Entity Graph Architecture

```
Layer 0 (visible on reset):
  |-- Log: "Failed login for alice@corp.com from 10.0.0.5"
  |-- Log: "Suspicious activity from 10.0.0.5"

Layer 1 (revealed by INVESTIGATE("alice") or INVESTIGATE("10.0.0.5")):
  |-- Log: "User 'alice' accessed secrets vault with token sk_live_abc..."
  |-- Log: "alice@corp.com connected from 172.16.0.1"

Layer 2 (revealed by INVESTIGATE("172.16.0.1")):
  |-- Log: "Config loaded: aws_secret_key=wJalrXUtn... from 172.16.0.1"
  |-- Log: "User 'bob' also accessed from 172.16.0.1"
```

## Quick Start

```bash
git clone https://github.com/bhaveshdamani5-crypto/senitel-env.git
cd senitel-env
pip install -r requirements.txt

# Run the baseline agent
python inference.py

# Run the demo
python demo.py

# Start the API server
python server.py
```

## API Usage

```bash
# Start server
uvicorn server:app --host 0.0.0.0 --port 7860

# Reset (start new episode)
curl -X POST "http://localhost:7860/reset?difficulty=medium"

# Scan visible logs
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "scan"}'

# Investigate an entity
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "investigate", "target_entity": "alice"}'

# Redact discovered PII
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "redact", "redactions": [{"original": "alice@corp.com", "type": "email"}]}'

# Submit findings
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "submit"}'

# Check state
curl http://localhost:7860/state

# Health check
curl http://localhost:7860/health
```

## Repository Structure

```
senitel-env/
|-- env.py             # Core RL environment with procedural generation
|-- models.py          # Pydantic action/observation/reward schemas
|-- grader.py          # Hidden ground truth scoring engine
|-- inference.py       # Baseline agent with investigation strategy
|-- server.py          # FastAPI server (OpenEnv API)
|-- demo.py            # Standalone demo script
|-- openenv.yaml       # OpenEnv environment specification
|-- Dockerfile         # HF Spaces deployment
|-- requirements.txt   # Python dependencies
|-- README.md          # This file
```

## Live Deployment

- GitHub: https://github.com/bhaveshdamani5-crypto/senitel-env
- Hugging Face Space: https://huggingface.co/spaces/bhavesh657/senitel-env
- API Docs: `/docs` (after deployment)
- Technical Docs: `/redoc`

## Why This Problem Matters

Log sanitization is a **critical real-world challenge**:
- Enterprise systems generate millions of log entries daily
- PII (emails, IPs, tokens) frequently leaks into logs
- Manual redaction doesn't scale; automated detection misses context
- High-risk secrets (API keys, auth tokens) require deep investigation

This environment trains agents to perform **intelligent, strategic investigation** — not just pattern matching.

## License

MIT License. See `LICENSE`.

---

Built for the Meta PyTorch OpenEnv Hackathon x Scaler School of Technology.
