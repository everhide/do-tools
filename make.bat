@echo off

set APP_DIR=%cd%\
set VENV=%APP_DIR%venv
set PATH=%PATH%;%APP_DIR%

python -m venv venv

%VENV%\Scripts\activate && ^
python -m pip install --upgrade pip && ^
python -m pip install wheel && ^
python -m pip install piny && ^
python -m pip install psycopg[binary] && ^
python -m pip install -r requirements.txt && ^
python install.py

reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v "Path" /t REG_EXPAND_SZ /d "%PATH%" /f
exit
