@echo off
rem Inicia o servidor JARVIS e reinicia sozinho se o processo cair (watchdog).
cd /d "%~dp0.."
:loop
"%USERPROFILE%\miniconda3\envs\jarvis\python.exe" server\run.py >> server\data\jarvis.log 2>&1
echo [%date% %time%] servidor caiu, reiniciando em 5s... >> server\data\jarvis.log
timeout /t 5 /nobreak > nul
goto loop
