@echo off
rem FORAN skill launcher. Prefers a venv next to the skill, falls back to python.
setlocal
set "HERE=%~dp0"
set "SKILL_ROOT=%HERE%.."
set "PY=%FORAN_PY%"
if not defined PY if exist "%SKILL_ROOT%\.venv\Scripts\python.exe" set "PY=%SKILL_ROOT%\.venv\Scripts\python.exe"
if not defined PY if exist "%SKILL_ROOT%\..\..\..\.venv\Scripts\python.exe" set "PY=%SKILL_ROOT%\..\..\..\.venv\Scripts\python.exe"
if not defined PY set "PY=python"
set "PYTHONIOENCODING=utf-8"
"%PY%" -I "%HERE%foran_cli.py" %*
exit /b %errorlevel%
