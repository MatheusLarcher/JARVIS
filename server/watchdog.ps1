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

# --- Ollama (11434): o roteador e os agentes locais nao respondem sem ele ---
# Quando o ollama morre, os llama-server filhos SOBREVIVEM segurando a VRAM.
# Nesta placa (8 GB) um orfao de 1,1 GB ja deixa o TTS e o Whisper sem espaco.
# Limpa antes de subir de novo, senao a cada reinicio sobra mais um.
$orfaos = Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" | Where-Object {
    -not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue)
}
foreach ($o in $orfaos) {
    Escreve "llama-server orfao (pid $($o.ProcessId)) segurando VRAM; encerrando"
    Stop-Process -Id $o.ProcessId -Force -ErrorAction SilentlyContinue
}

if (-not (Get-Process ollama)) {
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $ollama) {
        Escreve "ollama fora do ar; iniciando"
        Start-Process $ollama -ArgumentList 'serve' -WindowStyle Hidden
    } else {
        Escreve "ollama nao encontrado em $ollama"
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
