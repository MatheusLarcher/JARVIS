@echo off
rem Serviço de TTS com a voz clonada do JARVIS (env jarvis-tts, porta 8041).
cd /d "%~dp0.."
:loop
"%USERPROFILE%\miniconda3\envs\jarvis-tts\python.exe" server\voice_service\service.py --preload >> server\data\voice.log 2>&1
echo [%date% %time%] servico de voz caiu, reiniciando em 5s... >> server\data\voice.log
timeout /t 5 /nobreak > nul
goto loop
