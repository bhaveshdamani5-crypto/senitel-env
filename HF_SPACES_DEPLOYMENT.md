# HuggingFace Spaces Deployment Guide

## Quick Start (5 minutes)

### 1. Create Space

1. Go to https://huggingface.co/spaces
2. Click "Create new Space"
3. Fill in:
   - **Space name:** `senitel-env` (or your choice)
   - **License:** MIT
   - **SDK:** Docker
4. Connect your GitHub fork of this repo
5. Create Space

### 2. Add Secrets

1. Go to your Space settings
2. Click "Repository secrets"
3. Add two secrets:
   - `HF_TOKEN` = Your HF API token (from https://huggingface.co/settings/tokens)
   - `API_BASE_URL` = `https://router.huggingface.co/openai/` (default)

### 3. Deploy

1. Space automatically builds from `Dockerfile`
2. Wait 5-10 minutes for build to complete
3. Your Space is live! 🎉

**Your Space URL:** `https://huggingface.co/spaces/<username>/<space-name>`

---

## What Judges See

When judges visit your Space, they get:

### 1. Interactive Demo UI (at `/`)

- Manual scenario controls
- Step-by-step visualization
- Real-time metrics

### 2. API Endpoints (at `/api`)

- OpenEnv-compliant REST API
- Full documentation at `/api/docs`
- Ready for automated evaluation

### 3. Health Check

- `GET /health` → `{"status": "ok"}`

---

## Testing Before Submission

```bash
# Local test
python server.py
# Visit http://localhost:7860

# Run full benchmark
export HF_TOKEN="hf_YourToken"
python inference.py --seeds 5

# Run tests
python -m pytest tests/ -v
```

---

## Monitoring Your Space

### Check Build Status

1. Go to your Space
2. Click "Logs" (top right)
3. Look for:
   - ✅ `docker build ... SUCCESS`
   - ✅ Server started on port 7860

### Common Issues

| Issue                | Solution                                                 |
| -------------------- | -------------------------------------------------------- |
| `HF_TOKEN not found` | Make sure secret is in Space settings                    |
| Port 7860 error      | Docker config is correct; try rebuilding                 |
| Slow first inference | Model loading takes ~30s first time                      |
| Timeout errors       | Increase timeout in `inference.py: _llm_choose_action()` |

---

## File Checklist Before Submission

```
✅ env.py                  # Core environment
✅ models.py               # Pydantic schemas
✅ grader.py               # Scoring logic
✅ inference.py            # LLM baseline
✅ server.py               # FastAPI server
✅ demo.py                 # Demo (optional, but nice)
✅ Dockerfile              # Container image
✅ requirements.txt        # Dependencies
✅ openenv.yaml            # Specification
✅ README.md               # Documentation
✅ LICENSE                 # MIT license
✅ pytest.ini              # Test config
✅ tests/                  # Unit tests
```

---

## Judge Evaluation Checklist

When a judge visits your Space, they should see:

- [ ] Space loads without errors
- [ ] `/` displays interactive UI
- [ ] `/api` shows Swagger documentation
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] Can make test API calls
- [ ] Demo completes in < 30 seconds
- [ ] README clearly explains task

---

## Performance Tuning

### If Inference is Slow

```python
# In inference.py, adjust:
timeout = 60  # Increase from 30s
max_retries = 2  # Decrease from 3
```

### If Space Keeps Timing Out

1. Reduce batch size (environment already does this)
2. Choose faster model:
   ```python
   MODEL_NAME = "mistralai/Mixtral-8x7B-Instruct-v0.1"  # Faster
   ```
3. Remove heavy dependencies from `requirements.txt`

### Current Performance

- Demo run: 30-60 seconds
- Reset: < 1 second
- Step: 1-5 seconds
- Full 5-seed benchmark: ~10-15 minutes

---

## Post-Deployment

### Share Your Results

1. Add benchmark results to README:

   ```markdown
   ## Baseline Performance

   Tested with 10 seeds per difficulty:

   - Easy: 0.85 F1 ± 0.05
   - Medium: 0.68 F1 ± 0.08
   - Hard: 0.52 F1 ± 0.12
   ```

2. Share Space URL in hackathon submission

3. Optional: Create GitHub release with benchmark results

---

## Rollback / Debugging

If Space breaks:

1. **Check logs:** Click "Logs" in Space settings
2. **Revert commit:** Push a fix to GitHub (Space auto-rebuilds)
3. **Manual restart:** Click "Restart space" in settings
4. **Contact support:** HF Spaces support is responsive

---

## Security Best Practices

- ✅ Never commit `HF_TOKEN` to GitHub (use Space secrets)
- ✅ Validate all API inputs (server.py does this)
- ✅ Rate limit enabled (FastAPI built-in)
- ✅ CORS enabled (safe for judges' requests)

---

For additional help, see HF Spaces docs:
https://huggingface.co/docs/hub/spaces
