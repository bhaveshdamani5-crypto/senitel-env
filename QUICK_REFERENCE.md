# Quick Reference: Score Bounds Fix

## TL;DR - What Was Fixed

❌ **Problem:** Validator rejected code because scores were exactly 0.0 or 1.0
✅ **Solution:** Changed all defaults and initializations to use EPSILON (0.001)

---

## The 6 Critical Changes

### 1. `models.py` Line 126

```python
# BEFORE
score_so_far: float = Field(default=0.0, ...)

# AFTER
score_so_far: float = Field(default=_EPSILON, ...)
```

### 2. `models.py` Line 282

```python
# BEFORE
total_reward: float = Field(default=0.0, ...)

# AFTER
total_reward: float = Field(default=_EPSILON, ...)
```

### 3. `env.py` Line 655 (**init**)

```python
# BEFORE
self.total_reward = 0.0

# AFTER
self.total_reward = EPSILON
```

### 4. `env.py` Line 672 (reset())

```python
# BEFORE
self.total_reward = 0.0

# AFTER
self.total_reward = EPSILON
```

### 5. `server.py` Line 244

```python
# BEFORE
trace["final_score"] = trace["final_metrics"].get("total_score", 0.001)

# AFTER
trace["final_score"] = trace["final_metrics"].get("total_score", EPSILON)
```

(Also add import: `from env import EPSILON` at top)

### 6. `grader.py` Lines 100-120

```python
# BEFORE
return {
    ...
    "secret_penalty": secret_penalty,  # Negative value!
    ...
}

# AFTER
return {
    ...
    # secret_penalty removed (already in total_score)
    ...
}
```

---

## Validation

Run this to confirm everything works:

```bash
python test_score_bounds.py
```

You should see:

```
✅ ALL TESTS PASSED - Ready for submission!
```

---

## Score Constraints

Valid range: **[0.001, 0.999]** (inclusive on both ends)

- ✅ 0.001 (EPSILON) = Valid
- ✅ 0.5 = Valid
- ✅ 0.999 (1-EPSILON) = Valid
- ❌ 0.0 = Invalid (boundary)
- ❌ 1.0 = Invalid (boundary)
- ❌ -0.3 = Invalid (negative)

---

## Files Changed

**Main:**

- `models.py` (2 lines)
- `env.py` (2 lines)
- `server.py` (2 lines)
- `grader.py` (4 lines)

**Deploy:**

- `senitel-env-deploy/models.py` (2 lines)
- `senitel-env-deploy/env.py` (2 lines)
- `senitel-env-deploy/server.py` (2 lines)
- `senitel-env-deploy/grader.py` (4 lines)

---

## Checklist Before Submission

- [ ] Run `test_score_bounds.py` - all tests pass
- [ ] Check `/reset` endpoint - observe score_so_far > 0
- [ ] Check `/state` endpoint - environment total_reward > 0
- [ ] Run `/demo/run` - all scores in valid range
- [ ] Verify no "0.0" or "1.0" in any returned score field
- [ ] Confirm "secret_penalty" removed from grader output
- [ ] Both main and deploy folders updated

---

## If Still Failing

1. **Search for remaining '0.0' defaults:**

   ```bash
   grep -n "default=0" models.py
   grep -n "= 0\.0" env.py
   ```

   Should return nothing for score fields.

2. **Verify EPSILON is imported:**

   ```bash
   grep "from env import EPSILON" server.py
   ```

   Should show the import line.

3. **Check grader output:**

   ```bash
   python -c "from grader import InvestigationGrader; m = InvestigationGrader.compute_metrics({}, set(), set(), 0, 10, set()); print('secret_penalty' in m)"
   ```

   Should print: `False`

4. **Run validation test:**
   ```bash
   python test_score_bounds.py 2>&1 | grep -i "fail\|pass"
   ```
   Should show all PASS.

---

## Key Constants

```python
EPSILON = 0.001
MIN_SCORE = EPSILON = 0.001
MAX_SCORE = 1.0 - EPSILON = 0.999
```

These are defined in:

- `env.py` (lines 33-35)
- `grader.py` (lines 19-21)
- `models.py` (lines 13-14)

---

## Contact/Support

Check these files for more details:

- `AUDIT_FINDINGS.md` - Complete audit report
- `FIX_SUMMARY.md` - Detailed fix explanation
- `test_score_bounds.py` - Validation test (see test cases)

All fixes are backward compatible and transparent to agents.

---

**Version:** 1.0  
**Date:** 2026-04-08  
**Status:** ✅ READY
