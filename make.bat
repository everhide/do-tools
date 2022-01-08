@echo off

set APP_DIR=%cd%\
set VENV=%APP_DIR%venv

rmdir /s /q %VENV% > nul

python -m venv venv

%VENV%\Scripts\activate && ^
python -m pip install --upgrade pip && ^
python -m pip install wheel && ^
python -m pip install piny && ^
python -m pip install psycopg[binary] && ^
python -m pip install -r requirements.txt && ^
python install.py
