@echo off
rem Inicia o JARVIS: serviço de voz clonada + servidor. Cada um se reinicia sozinho.
cd /d "%~dp0.."

rem serviço de voz (env jarvis-tts, porta 8041) em janela própria, com watchdog
start "JARVIS Voz" /min cmd /c "%~dp0start_voice.bat"

:loop
"%USERPROFILE%\miniconda3\envs\jarvis\python.exe" server\run.py >> server\data\jarvis.log 2>&1
echo [%date% %time%] servidor caiu, reiniciando em 5s... >> server\data\jarvis.log
timeout /t 5 /nobreak > nul
goto loop
