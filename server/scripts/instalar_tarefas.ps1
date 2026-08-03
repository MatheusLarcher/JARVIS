# Registra (ou conserta) as tarefas agendadas do JARVIS.
#
#   powershell -ExecutionPolicy Bypass -File server\scripts\instalar_tarefas.ps1
#
# SEM ACENTOS DE PROPOSITO: o Windows PowerShell 5.1 le .ps1 como ANSI quando o
# arquivo nao tem BOM, e um "nao" acentuado vira erro de parser.
#
# Por que existe: as tarefas foram criadas uma vez com `schtasks /TR "...\x.vbs"`.
# A barra invertida antes da aspa final escapa a aspa, entao o caminho e o
# `/RL LIMITED` viraram um argumento so e a tarefa passou a falhar (resultado 1).
# Somado a isso, o projeto saiu de ~\Documents\GitHub\JARVIS e os caminhos
# gravados ficaram apontando pro vazio. Aqui a raiz vem do proprio arquivo, e o
# Register-ScheduledTask recebe o caminho como argumento - sem passar por parser
# de linha de comando.
$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vbs = Join-Path $raiz "server\start_jarvis_hidden.vbs"
$watchdog = Join-Path $raiz "server\watchdog.ps1"

foreach ($f in @($vbs, $watchdog)) {
    if (-not (Test-Path $f)) { throw "nao achei $f - rode de dentro do projeto" }
}

Write-Host "projeto: $raiz"

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)

# --- vigia: reergue o que cair, a cada 5 minutos ---
# Sem -RepetitionDuration a repeticao fica indefinida. Passar [TimeSpan]::MaxValue
# gera P99999999DT23H59M59S, que o agendador recusa ("valor fora do intervalo").
$gatilho = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$gatilho.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition

$tarefas = @(
    @{
        nome = "JARVIS Server"
        acao = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`"" -WorkingDirectory $raiz
        gatilho = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        desc = "Sobe o servidor do JARVIS (e o servico de voz) sem janela."
    },
    @{
        nome = "JARVIS Watchdog"
        acao = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdog`"" `
            -WorkingDirectory $raiz
        gatilho = $gatilho
        desc = "Verifica servidor, voz, Ollama e app da bandeja; sobe o que estiver fora."
    }
)

$negados = @()
foreach ($t in $tarefas) {
    try {
        Register-ScheduledTask -TaskName $t.nome -Force -Principal $principal -Settings $settings `
            -Trigger $t.gatilho -Action $t.acao -Description $t.desc -ErrorAction Stop | Out-Null
        Write-Host ("  [ok] " + $t.nome)
    } catch {
        # Tarefa que ja existe criada por outro contexto (ou elevada) so aceita
        # ser regravada com admin. Nao e fatal: o app da bandeja entra sozinho na
        # inicializacao do Windows e ja sobe/vigia servidor, voz e Ollama.
        Write-Host ("  [!] " + $t.nome + ": " + $_.Exception.Message)
        $negados += $t.nome
    }
}

Write-Host ""
if ($negados.Count -gt 0) {
    Write-Host "Nao consegui regravar: $($negados -join ', ')"
    Write-Host "Elas ja existem e so mudam com administrador. O JARVIS funciona sem elas"
    Write-Host "(o app da bandeja sobe e vigia tudo), mas pra deixar limpo, num PowerShell"
    Write-Host "como administrador rode:"
    Write-Host ""
    Write-Host ("  powershell -ExecutionPolicy Bypass -File `"" + $PSCommandPath + "`"")
    Write-Host ""
}

Write-Host "Como as tarefas estao agora:"
foreach ($t in $tarefas) {
    $ta = Get-ScheduledTask -TaskName $t.nome -ErrorAction SilentlyContinue
    if ($ta) {
        Write-Host ("  " + $t.nome + " -> " + $ta.Actions[0].Execute + " " + $ta.Actions[0].Arguments)
    } else {
        Write-Host ("  " + $t.nome + " -> nao registrada")
    }
}
