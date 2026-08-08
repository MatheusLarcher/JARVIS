@echo off
rem Servico de TTS com a voz clonada do JARVIS (env jarvis-tts, porta 8041).
cd /d "%~dp0.."

rem evita o "forrtl: error (200) window-CLOSE" da runtime Fortran (numpy/scipy)
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1

rem os modelos ficam no D: (o C: encheu e corrompeu downloads); sem isto o
rem cache volta pro C: e baixa ~50 GB de novo
if not defined HF_HOME set HF_HOME=D:\ai-cache\huggingface

:loop
rem  Se alguem JA esta servindo na 8041, esta copia e duplicata: sai em vez de
rem  tentar pra sempre. Sem esta trava, a copia que perdia a porta morria na
rem  hora, o loop a reerguia e o `timeout /t 5 /nobreak` abaixo piscava uma
rem  janela na tela a cada 5 segundos, sem parar.
netstat -ano | findstr /r /c:":8041 " | findstr /c:"LISTENING" >nul 2>&1
if not errorlevel 1 (
    rem  NAO escrever no voice.log: o servico que esta no ar segura esse arquivo
    rem  ("O arquivo ja esta sendo usado por outro processo") e a mensagem se perde
    echo [%date% %time%] ja existe servico de voz na 8041; encerrando esta copia >> server\data\startup.log
    exit /b 0
)

"%USERPROFILE%\miniconda3\envs\jarvis-tts\python.exe" -u server\voice_service\service.py --preload >> server\data\voice.log 2>&1
echo [%date% %time%] servico de voz caiu, reiniciando em 5s... >> server\data\voice.log
timeout /t 5 /nobreak > nul
goto loop
