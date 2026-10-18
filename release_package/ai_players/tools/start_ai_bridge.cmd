@echo off
setlocal
where python >nul 2>nul
if errorlevel 1 goto try_py
python "%~dp0ai_http_bridge.py"
goto finished
:try_py
where py >nul 2>nul
if errorlevel 1 goto missing
py -3 "%~dp0ai_http_bridge.py"
goto finished
:missing
echo Python 3 is required. Install Python and enable Add Python to PATH.
:finished
if errorlevel 1 pause
