@echo off
REM Batch script to commit and push changes to GitHub and Hugging Face

cd /d "C:\Users\BHAVESH\Downloads\senitelenv"

echo.
echo ===================================================
echo Starting Git Commit and Push Process
echo ===================================================
echo.

echo [1/5] Staging all changes...
git add -A
if %ERRORLEVEL% EQU 0 (
    echo + All changes staged successfully
) else (
    echo - Failed to stage changes
    exit /b 1
)
echo.

echo [2/5] Changes to be committed:
git diff --cached --name-only
echo.

echo [3/5] Creating commit...
git commit -m "Fix: Ensure all scores are strictly between 0 and 1 (not 0.0 or 1.0) - Update EPSILON from 0.001 to 0.0001 and apply strict clamping across all files"
if %ERRORLEVEL% EQU 0 (
    echo + Commit created successfully
) else (
    echo - Failed to create commit
    exit /b 1
)
echo.

echo [4/5] Pushing to GitHub...
git push origin main
if %ERRORLEVEL% EQU 0 (
    echo + Pushed to GitHub successfully
) else (
    echo * GitHub push had issues
)
echo.

echo [5/5] Pushing to Hugging Face...
git push hf main
if %ERRORLEVEL% EQU 0 (
    echo + Pushed to Hugging Face successfully
) else (
    echo * Hugging Face push had issues
)
echo.

echo ===================================================
echo Git Operations Complete
echo ===================================================
echo.
echo Commit Summary:
git log --oneline -1
echo.
