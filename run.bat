@echo off
cd /d "%~dp0"

echo Checking dependencies...
python -c "import pystray" 2>nul
if %errorlevel% neq 0 (
    echo Installing required libraries...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo Starting Water Assistant...
start "" pythonw main.py
timeout /t 1 /nobreak >nul
exit
