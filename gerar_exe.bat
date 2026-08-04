@echo off
setlocal enabledelayedexpansion
rem ============================================================================
rem  Gera o instalador do JARVIS pra Windows.
rem
rem  Basta dar dois cliques (ou rodar `gerar_exe.bat`). Ele faz tudo:
rem    1. instala as dependencias que faltarem (web e desktop)
rem    2. builda a interface (apps/web -> dist)
rem    3. copia a interface pra dentro do app (sync-web)
rem    4. gera o instalador NSIS com o electron-builder
rem    5. deixa o .exe pronto em releases\JARVIS-Desktop-Setup.exe
rem
rem  Opcoes:
rem    gerar_exe.bat            gera com a versao atual do package.json
rem    gerar_exe.bat 0.2.0      grava essa versao antes de gerar
rem ============================================================================

cd /d "%~dp0"
set "RAIZ=%CD%"
set "WEB=%RAIZ%\apps\web"
set "APP=%RAIZ%\apps\desktop"
set "SAIDA=%RAIZ%\releases"
set "FINAL=%SAIDA%\JARVIS-Desktop-Setup.exe"

echo.
echo  =========================================
echo   JARVIS - gerando o instalador do Windows
echo  =========================================
echo.

rem ---------------------------------------------------------------- pre-requisitos
where npm >nul 2>&1
if errorlevel 1 (
    echo  [X] Nao achei o npm. Instale o Node.js: https://nodejs.org
    goto :erro
)
for /f "delims=" %%v in ('node --version 2^>nul') do set "NODEV=%%v"
echo  Node !NODEV!

if not exist "%WEB%\package.json" (
    echo  [X] Nao achei %WEB%. Rode este script de dentro da pasta do projeto.
    goto :erro
)

rem ---------------------------------------------------------------- versao
if not "%~1"=="" (
    echo.
    echo  [versao] gravando %~1 no package.json...
    pushd "%APP%"
    call npm version "%~1" --no-git-tag-version --allow-same-version >nul
    if errorlevel 1 ( popd & echo  [X] versao invalida: %~1 & goto :erro )
    popd
)
for /f "tokens=2 delims=:, " %%v in ('findstr /c:"\"version\"" "%APP%\package.json"') do (
    set "VERSAO=%%~v"
    goto :temversao
)
:temversao
echo  Versao: %VERSAO%

rem ---------------------------------------------------------------- 1. dependencias
echo.
echo  [1/4] dependencias...
if not exist "%WEB%\node_modules" (
    echo        instalando as da interface ^(demora na primeira vez^)...
    pushd "%WEB%"
    call npm install --no-audit --no-fund
    if errorlevel 1 ( popd & echo  [X] npm install falhou na interface & goto :erro )
    popd
) else (
    echo        interface: ja instaladas
)
if not exist "%APP%\node_modules" (
    echo        instalando as do app ^(baixa o Electron, ~200 MB^)...
    pushd "%APP%"
    call npm install --no-audit --no-fund
    if errorlevel 1 ( popd & echo  [X] npm install falhou no app & goto :erro )
    popd
) else (
    echo        app: ja instaladas
)

rem ---------------------------------------------------------------- 2. interface
echo.
echo  [2/4] buildando a interface...
pushd "%WEB%"
call npm run build
if errorlevel 1 ( popd & echo  [X] o build da interface falhou & goto :erro )
popd
if not exist "%WEB%\dist\index.html" (
    echo  [X] o build nao gerou apps\web\dist\index.html
    goto :erro
)

rem ---------------------------------------------------------------- 3. instalador
echo.
echo  [3/4] gerando o instalador ^(pode levar alguns minutos^)...
rem  `npm run dist` ja roda o sync-web antes do electron-builder
pushd "%APP%"
call npm run dist
if errorlevel 1 ( popd & echo  [X] o electron-builder falhou & goto :erro )
popd

set "GERADO=%APP%\dist\JARVIS Setup %VERSAO%.exe"
if not exist "%GERADO%" (
    echo  [X] nao achei o instalador esperado:
    echo      %GERADO%
    echo      veja o que saiu em %APP%\dist
    goto :erro
)

rem ---------------------------------------------------------------- 4. entrega
echo.
echo  [4/4] publicando em releases...
if not exist "%SAIDA%" mkdir "%SAIDA%"
copy /y "%GERADO%" "%FINAL%" >nul
if errorlevel 1 (
    echo  [X] nao consegui copiar pra %FINAL%
    echo      o JARVIS esta aberto? feche pela bandeja e rode de novo.
    goto :erro
)

rem  Nao registra nada no boot: quem decide isso e a opcao "Iniciar com o
rem  Windows", na engrenagem do app. Tarefa agendada guarda caminho absoluto e
rem  foi exatamente o que quebrou quando o projeto mudou de pasta (o wscript
rem  passou a abrir erro de script em todo boot).

for %%f in ("%FINAL%") do set /a MB=%%~zf/1048576
echo.
echo  =========================================
echo   PRONTO - versao %VERSAO%, !MB! MB
echo.
echo   %FINAL%
echo.
echo   E so dar dois cliques nele pra instalar.
echo   Pra ele ligar junto com o Windows, marque a opcao na engrenagem.
echo  =========================================
echo.

rem abre a pasta ja com o instalador selecionado
explorer /select,"%FINAL%"

pause
exit /b 0

:erro
echo.
echo  Nao deu pra gerar o instalador. O erro esta logo acima.
echo.
pause
exit /b 1
