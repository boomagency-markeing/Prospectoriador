@echo off
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
pause
