@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem Usage: push.bat ["commit message"]

if not exist ".git" (
    echo Initializing git repository...
    git init
    git branch -M main
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
    set /p REPO_URL="Enter the remote repository URL (e.g. https://github.com/you/repo.git): "
    if "!REPO_URL!"=="" (
        echo No URL entered. Aborting.
        exit /b 1
    )
    git remote add origin "!REPO_URL!"
)

set "COMMIT_MSG=%*"
if defined COMMIT_MSG set "COMMIT_MSG=!COMMIT_MSG:"=!"
if not "!COMMIT_MSG!"=="" goto :have_message
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set DATESTAMP=%%a-%%b-%%c
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set TIMESTAMP=%%a-%%b
set "COMMIT_MSG=Update !DATESTAMP! !TIMESTAMP!"
:have_message

git add -A
git commit -m "!COMMIT_MSG!"
if errorlevel 1 (
    echo Nothing to commit or commit failed.
)

for /f "tokens=*" %%b in ('git rev-parse --abbrev-ref HEAD') do set CURRENT_BRANCH=%%b

git push -u origin "%CURRENT_BRANCH%"
if errorlevel 1 (
    echo Push failed. Check your remote URL and credentials.
    exit /b 1
)

echo Done.
endlocal
