# PowerShell script to commit and push changes to GitHub and Hugging Face

Set-Location "C:\Users\BHAVESH\Downloads\senitelenv"

Write-Host "=== Starting Git Commit and Push Process ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Add all changes
Write-Host "[1/5] Staging all changes..." -ForegroundColor Yellow
git add -A
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ All changes staged successfully" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to stage changes" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Show what will be committed
Write-Host "[2/5] Changes to be committed:" -ForegroundColor Yellow
git diff --cached --name-only
Write-Host ""

# Step 3: Commit changes
Write-Host "[3/5] Creating commit..." -ForegroundColor Yellow
$commitMessage = "Fix: Ensure all scores are strictly between 0 and 1 (not 0.0 or 1.0)`n`n- Update EPSILON constant from 0.001 to 0.0001 across all files`n- Initialize all scores to EPSILON instead of 0.0`n- Apply strict clamping: max(EPSILON, min(1.0-EPSILON, value))`n- Fix grader empty ground_truth to return 0.9999 (not 1.0)`n- Add _strict_reward_value() wrapper for step rewards`n- Update inference.py to use metrics.get('total_score') instead of sum(rewards)`n- Harden return dict score defaults with explicit clamping`n`nValidator requirement: Scores must be strictly in open interval (0, 1), never exactly 0.0 or 1.0"

git commit -m $commitMessage
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Commit created successfully" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to create commit" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 4: Push to GitHub
Write-Host "[4/5] Pushing to GitHub..." -ForegroundColor Yellow
git push origin main
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Pushed to GitHub successfully" -ForegroundColor Green
} else {
    Write-Host "⚠ GitHub push had issues (may not have remote configured)" -ForegroundColor Yellow
}

Write-Host ""

# Step 5: Push to Hugging Face
Write-Host "[5/5] Pushing to Hugging Face..." -ForegroundColor Yellow
$hfRemote = git remote | Select-String "huggingface"
if ($hfRemote) {
    git push huggingface main
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Pushed to Hugging Face successfully" -ForegroundColor Green
    } else {
        Write-Host "⚠ Hugging Face push encountered an issue" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠ Hugging Face remote not configured. To add it:" -ForegroundColor Yellow
    Write-Host "   git remote add huggingface https://huggingface.co/username/repo-name.git" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=== Git Operations Complete ===" -ForegroundColor Cyan
Write-Host "Commit created with all score boundary fixes!" -ForegroundColor Green
Write-Host ""
Write-Host "Commit Summary:" -ForegroundColor Yellow
git log --oneline -1
