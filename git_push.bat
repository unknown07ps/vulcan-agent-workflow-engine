@echo off
REM Initializes git repo (if needed), commits current stage, and pushes to GitHub.
REM
REM Usage:
REM   git_push.bat "Stage 1: scaffolding" https://github.com/unknown07ps/agent-workflow-engine.git
REM
REM First run: git init, set branch to main, add remote, commit, push.
REM Later runs: git_push.bat "Stage 2: ..."   (remote already set, arg optional)

setlocal

set COMMIT_MSG=%~1
set REMOTE_URL=%~2

if "%COMMIT_MSG%"=="" set COMMIT_MSG=chore: update

if not exist ".git" (
    echo ^>^> Initializing git repo
    git init
    git branch -M main
)

if not "%REMOTE_URL%"=="" (
    git remote get-url origin >nul 2>&1
    if errorlevel 1 (
        echo ^>^> Adding remote origin: %REMOTE_URL%
        git remote add origin "%REMOTE_URL%"
    )
)

git add .
git commit -m "%COMMIT_MSG%"
git push -u origin main

endlocal
