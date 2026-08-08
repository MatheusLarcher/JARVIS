@echo off
rem Inicia o JARVIS: servico de voz clonada + servidor. Cada um se reinicia sozinho.
cd /d "%~dp0.."

rem A runtime Fortran da Intel (dentro do numpy/scipy) mata o processo quando o
rem console recebe evento de fechar/logoff -> "forrtl: error (200)". Sem isto o
rem servidor morre ao ligar/deslogar a maquina.
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1

rem os modelos ficam no D: (o C: encheu e corrompeu downloads); sem isto o
rem cache volta pro C: e baixa ~50 GB de novo
if not defined HF_HOME set HF_HOME=D:\ai-cache\huggingface

rem servico de voz (env jarvis-tts, porta 8041) em janela propria, com watchdog
start "JARVIS Voz" /min cmd /c "%~dp0start_voice.bat"

:loop
rem  Mesma trava do start_voice.bat: duplicata sai, em vez de reiniciar pra
rem  sempre disputando uma porta que ja tem dono.
netstat -ano | findstr /r /c:":8040 " | findstr /c:"LISTENING" >nul 2>&1
if not errorlevel 1 (
    rem  mesmo motivo do start_voice.bat: o servidor no ar segura o jarvis.log
    echo [%date% %time%] ja existe servidor na 8040; encerrando esta copia >> server\data\startup.log
    exit /b 0
)

rem -u = log sem buffer (senao o jarvis.log so aparece quando enche 8KB)
"%USERPROFILE%\miniconda3\envs\jarvis\python.exe" -u server\run.py >> server\data\jarvis.log 2>&1
echo [%date% %time%] servidor caiu, reiniciando em 5s... >> server\data\jarvis.log
timeout /t 5 /nobreak > nul
goto loop
