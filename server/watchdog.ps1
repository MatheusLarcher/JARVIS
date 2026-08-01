# Vigia do JARVIS: garante que servidor, servico de voz e app da bandeja estejam
# no ar. Roda pela tarefa agendada "JARVIS Watchdog" a cada poucos minutos.
# Nao mata nada que ja esteja funcionando.

$ErrorActionPreference = "SilentlyContinue"
$raiz = Split-Path -Parent $PSScriptRoot
$log = Join-Path $raiz "server\data\watchdog.log"

function Escreve($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Out-File -Append -Encoding utf8 $log
}

function NoAr($porta) {
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:$porta/api/status" -TimeoutSec 5 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch {
        if ($porta -eq 8041) {
            try {
                return (Invoke-WebRequest "http://127.0.0.1:8041/health" -TimeoutSec 5 -UseBasicParsing).StatusCode -eq 200
            } catch { return $false }
        }
        return $false
    }
}

# --- servidor (8040): sobe junto com o servico de voz pelo start_jarvis.bat ---
$servidorVivo = (Get-Process python | Where-Object { $_.Path -like "*envs\jarvis\*" }) -ne $null
if (-not $servidorVivo) {
    Escreve "servidor fora do ar; iniciando"
    Start-Process cmd -ArgumentList '/c', (Join-Path $raiz "server\start_jarvis.bat") -WindowStyle Minimized
    Start-Sleep -Seconds 5
}

# --- servico de voz (8041) ---
$vozViva = (Get-Process python | Where-Object { $_.Path -like "*envs\jarvis-tts\*" }) -ne $null
if ($servidorVivo -and -not $vozViva) {
    Escreve "servico de voz fora do ar; iniciando"
    Start-Process cmd -ArgumentList '/c', (Join-Path $raiz "server\start_voice.bat") -WindowStyle Minimized
}

# --- app da bandeja ---
$app = "$env:LOCALAPPDATA\Programs\jarvis-desktop\JARVIS.exe"
if ((Test-Path $app) -and -not (Get-Process JARVIS)) {
    Escreve "app da bandeja fora do ar; iniciando"
    Start-Process $app
}
