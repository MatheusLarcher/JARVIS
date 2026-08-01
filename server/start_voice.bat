@echo off
rem Servico de TTS com a voz clonada do JARVIS (env jarvis-tts, porta 8041).
cd /d "%~dp0.."

rem evita o "forrtl: error (200) window-CLOSE" da runtime Fortran (numpy/scipy)
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1

:loop
"%USERPROFILE%\miniconda3\envs\jarvis-tts\python.exe" -u server\voice_service\service.py --preload >> server\data\voice.log 2>&1
echo [%date% %time%] servico de voz caiu, reiniciando em 5s... >> server\data\voice.log
timeout /t 5 /nobreak > nul
goto loop
