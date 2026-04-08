# Comprehensive Score Range Validation Audit

## Sentinel-Log-Shield v2 Hackathon Codebase

**Error:** "One or more task scores are out of range. Each task's score must be strictly between 0 and 1 (not 0.0 and not 1.0)."

**Validation Requirement:** All scores must be in `(0, 1)` — strictly: `0 < score < 1` (never exactly 0.0 or 1.0)

---

## CRITICAL BUGS FOUND

### 🔴 BUG #1: Observation.score_so_far Default = 0.0

**File:** [models.py](models.py#L126)  
**Line:** [126](models.py#L126)  
**Severity:** 🔴 CRITICAL  
**Code:**

```python
score_so_far: float = Field(
    default=0.0, description="Running score based on redactions submitted"
)
```

**Why It's Broken:**

- Every `Observation` object returned to the API has `score_so_far` = exactly 0.0
- This violates the strict bound requirement (cannot be exactly 0.0)
- **Impact:** EVERY API response with an observation returns a score of 0.0, which fails validation

**Fix:** Change to EPSILON (0.001)

---

### 🔴 BUG #2: EnvironmentState.total_reward Default = 0.0

**File:** [models.py](models.py#L282)  
**Line:** [282](models.py#L282)  
**Severity:** 🔴 CRITICAL  
**Code:**

```python
total_reward: float = Field(
    default=0.0, description="Cumulative reward this episode"
)
```

**Why It's Broken:**

- The `/state` endpoint returns `total_reward` = exactly 0.0 when episode hasn't started
- Violates strict bound requirement
- **Impact:** GET /state endpoint exposes a score of 0.0

**Fix:** Change to EPSILON (0.001)

---

### 🟠 BUG #3: SentinelEnvironment.total_reward Initialization = 0.0

**File:** [env.py](env.py#L655-L672)  
**Lines:** [655](env.py#L655), [672](env.py#L672)  
**Severity:** 🟠 HIGH  
**Code:**

```python
# Line 655 in __init__
self.total_reward = 0.0

# Line 672 in reset()
self.total_reward = 0.0
```

**Why It's Broken:**

- While `total_reward` is an internal state variable (not directly exposed in models), it gets incremented
- If no steps are taken, cumulative reward could be exactly 0.0
- If sent to Observation or EnvironmentState without proper clamping, violates bounds
- **Impact:** Edge case where episode with no progress could report 0.0 score

**Fix:** Initialize to EPSILON instead

---

### 🟡 BUG #4: Reward Validator May Not Catch All Metrics

**File:** [models.py](models.py#L199)  
**Lines:** [199-227](models.py#L199-L227)  
**Severity:** 🟡 MEDIUM  
**Code:**

```python
@model_validator(mode="after")
def _ensure_strict_scores(self) -> "Reward":
    # ... clamps top-level fields ...

    # Recursively clamp metrics
    if self.metrics:
        for k, v in self.metrics.items():
            if isinstance(v, float):
                self.metrics[k] = max(_EPSILON, min(_MAX_SCORE, v))
    return self
```

**Why It's Risky:**

- The validator clamps ALL float metrics, both scores AND counts
- If a count (like `true_positives=1` or `false_positives=0`) is mixed with scores, it gets clamped
- But more importantly: **counts should never be in (0, 1) range** - they might legitimately be 0, 1, 2, etc.
- The validator correctly doesn't validate counts, BUT the dict mixing creates ambiguity
- **Impact:** Code relies on convention that scores are named consistently to distinguish them (works now, but fragile)

**Fix:** Use a separate `scores` dict for actual scores, or document which keys are scores vs counts

---

### 🟡 BUG #5: Division Results Could Produce Exact Boundary Values

**File:** [env.py](env.py#L1015) & [grader.py](grader.py#L71)  
**Severity:** 🟡 MEDIUM  
**Code (env.py):**

```python
precision = safe_unit(true_positives / (true_positives + false_positives)) if (true_positives + false_positives) > 0 else EPSILON
```

**Why It's Risky:**

- **Edge case 1:** `precision = 1.0` when all predictions are correct: `(true_positives=5) / (true_positives=5 + false_positives=0) = 1.0` → exact 1.0!
- **Edge case 2:** `recall = 0.0` when nothing is ground truth: `(true_positives=0) / (total=0)` → caught by check, but if total≠0 but TP=0, recall=0.0
- The `safe_unit()` function should clamp these, but let's verify it works for boundary values

**Fix:** Ensure `safe_unit()` properly clamps even intermediate results

---

### 🟡 BUG #6: Demo Episode Rounding Could Produce 0.0

**File:** [server.py](server.py#L195) & [244](server.py#L244)  
**Lines:** [195](server.py#L195), [244](server.py#L244)  
**Severity:** 🟡 MEDIUM  
**Code:**

```python
trace["steps"].append({
    ...
    "reward": round(result.reward.total_reward, 3),  # Line 195
    ...
})

trace["final_score"] = trace["final_metrics"].get("total_score", 0.001)  # Line 244
```

**Why It's Risky:**

- Rounding EPSILON (0.001) to 3 decimals = 0.001 ✓ (safe)
- But if a reward becomes 0.0005, rounding to 3 decimals = 0.000 = 0.0 ✗ (VIOLATION!)
- Line 244 uses `0.001` as fallback, which is correct, but hardcoded instead of using EPSILON constant
- **Impact:** If any intermediate score rounds to 0.0, the demo response fails validation

**Fix:** Use EPSILON constant and avoid rounding below EPSILON precision

---

## CLEAN CODE / MAINTAINABILITY ISSUES

### Issue #7: Inconsistent EPSILON Definitions

**Files:** `env.py`, `grader.py`, `models.py`  
**Problem:** EPSILON is defined separately in 3 files:

- `env.py`: `EPSILON = 0.001`
- `grader.py`: `EPSILON = 0.001`
- `models.py`: `_EPSILON = 0.001`

**Risk:** If someone changes one EPSILON and forgets the others, inconsistency breaks bounds guarantees

**Fix:** Define EPSILON in a single `constants.py` file, import everywhere

---

### Issue #8: Mixed Scores and Counts in Metrics Dict

**File:** `env.py` - all action handlers  
**Problem:** Metrics dict simultaneously holds:

- Scores: `precision`, `recall`, `f1_score`, `discovery_rate` (must be in (0, 1))
- Counts: `true_positives`, `false_positives`, `steps_used` (can be any non-negative int)
- Mixed in same dict without structure

**Risk:** If a new developer adds metrics by convention, they might accidentally add a score that violates bounds or add a count that looks like a score

**Fix:** Create separate `MetricsScores` and `MetricsCounts` dataclasses, or use a `TypedDict`

---

### Issue #9: safe_nonnegative Returns 0.0

**File:** [env.py](env.py#L61)  
**Code:**

```python
def safe_nonnegative(x: float) -> float:
    """Clamp to [0.0, +inf), allowing zero."""
    if x is None:
        return 0.0
    return max(0.0, float(x))
```

**Problem:** This helper allows 0.0, which is fine for counts and penalties, but dangerous if misused for scores

**Risk:** If anyone uses `safe_nonnegative()` for a score field, it could produce 0.0

**Fix:** Document that `safe_nonnegative()` is ONLY for non-score metrics; consider renaming

---

## DATA FLOW TRACE

### How a Score Gets to the Validator

```
[env.py] _handle_submit() returns Reward(..., total_reward=value)
    ↓ safe_score(raw_total) called to bound intermediate result
    ↓
[models.py] Reward.__init__ → @model_validator runs _ensure_strict_scores()
    ↓ Clamps ALL float fields including nested metrics
    ↓
[server.py] step() endpoint returns StepResult with clamped Reward
    ↓ Pydantic serializes to JSON
    ↓
[OpenEnv validator] Checks all "score" fields are in (0, 1)
    ✓ Reward.total_reward ← properly clamped
    ✓ Reward.score ← mirrors total_reward ✓ properly clamped
    ✗ Observation.score_so_far ← DEFAULT 0.0 ✗ FAILS
    ✗ EnvironmentState.total_reward ← DEFAULT 0.0 ✗ FAILS
```

---

## ROOT CAUSE ANALYSIS

**Primary Bug:** Pydantic model defaults (`default=0.0`) bypass the `@model_validator` hook!

1. Pydantic validators only run on model **instantiation** with data
2. Fields with `default=0.0` are **never instantiated as 0.0** — they're set as the default **before** validation
3. When `Observation(...)` is created without passing `score_so_far`, it gets default 0.0 **without validator running**
4. Validator only runs if you explicitly pass `score_so_far=something`

**Why It Works Elsewhere:**

- `Reward` is always explicitly constructed in `env.py` with all fields passed
- Validator runs and clamps them ✓
- But `Observation` is constructed with partial kwargs, gets default fields ✗

---

## RECOMMENDED FIXES (PRIORITY ORDER)

### Priority 1: CRITICAL (Fix Immediately)

1. **models.py line 126:** Change `default=0.0` → `default=0.001` (or use EPSILON constant)
2. **models.py line 282:** Change `default=0.0` → `default=0.001`

### Priority 2: HIGH (Fix Before Submission)

3. **env.py lines 655, 672:** Change `= 0.0` → `= EPSILON`
4. **models.py lines 199-227:** Enhance validator to explicitly document/separate scores from counts

### Priority 3: MEDIUM (Maintainability)

5. **Create constants.py:** Centralize EPSILON definition
6. **Add validation tests:** Unit tests that verify no score is exactly 0.0 or 1.0
7. **Document metrics dict:** Clearly mark which keys are scores vs counts

### Priority 4: NICE-TO-HAVE (Code Quality)

8. **Refactor metrics dict:** Use TypedDict or separate dictionaries
9. **Rename/document safe_nonnegative:** Only use for counts
10. **Add type hints:** Use `Score` type alias to catch misuse

---

## VALIDATION CHECKLIST

After applying all fixes, verify:

- [ ] All `Field(..., default=0.0)` in models.py are changed to EPSILON or generator
- [ ] `SentinelEnvironment.__init__` sets `self.total_reward = EPSILON` not 0.0
- [ ] `SentinelEnvironment.reset()` sets `self.total_reward = EPSILON` not 0.0
- [ ] Run a full demo episode and verify all reward values > 0.0 and < 1.0
- [ ] Check `/reset` endpoint returns Observation with `score_so_far > 0.0`
- [ ] Check `/state` endpoint returns EnvironmentState with `total_reward > 0.0`
- [ ] Verify rounding in demo_run_episode doesn't produce 0.0 or 1.0
- [ ] Add unit test that creates Observation() with no args and checks `score_so_far`
- [ ] Run full integration test against OpenEnv validator

---

## FILES REQUIRING CHANGES

| File      | Lines   | Issue                    | Fix                       |
| --------- | ------- | ------------------------ | ------------------------- |
| models.py | 126     | score_so_far default=0.0 | Change to EPSILON         |
| models.py | 282     | total_reward default=0.0 | Change to EPSILON         |
| env.py    | 655     | total_reward = 0.0       | Change to EPSILON         |
| env.py    | 672     | total_reward = 0.0       | Change to EPSILON         |
| models.py | 199-227 | Validator ambiguity      | Document/separate metrics |
| server.py | 244     | Hardcoded 0.001          | Use EPSILON constant      |
| \*.py     | All     | EPSILON defined 3 times  | Extract to constants.py   |

---

## EXPECTED IMPACT

- **Breaking Changes:** None (increasing default from 0.0 to 0.001 is transparent)
- **Score Shifts:** Minimal (EPSILON is tiny; only affects already-zero cases)
- **API Compatibility:** Fully backward compatible
- **Test Coverage:** Existing tests should pass; add new boundary tests
