@echo off
setlocal
cd /d %~dp0
if not exist venv (
  py -m venv venv
)
call venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
