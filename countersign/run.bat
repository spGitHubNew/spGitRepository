@echo off
cd /d "%~dp0"
echo Starting CounterSign at http://localhost:8765
start "" http://localhost:8765
python app.py
