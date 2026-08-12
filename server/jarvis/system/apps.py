"""Abrir programas do Windows a partir do que a pessoa falou.

Não pede pra você cadastrar cada app: qualquer atalho que já está no Menu Iniciar
é encontrado por aproximação de nome. `config/apps.yml` só serve pra apelido
("navegador" → Chrome) ou pra forçar um caso que a busca acerta errado.

Roda no processo do servidor (a mesma máquina do `pc-matheus`), então
`os.startfile` abre o programa na tela de quem está usando o JARVIS ali.
"""
import asyncio
import logging
import os
import subprocess
from pathlib import Path

from ..config import config
from ..intents.router import normalize

log = logging.getLogger("jarvis.apps")

# utilitários do Windows que sempre resolvem por nome, sem precisar de atalho
EMBUTIDOS = {
    "bloco de notas": "notepad.exe",
    "notas": "notepad.exe",
    "calculadora": "calc.exe",
    "explorador de arquivos": "explorer.exe",
    "explorador": "explorer.exe",
    "arquivos": "explorer.exe",
    "paint": "mspaint.exe",
    "painel de controle": "control.exe",
    "gerenciador de tarefas": "taskmgr.exe",
    "prompt de comando": "cmd.exe",
    "terminal": "wt.exe",
    "configuracoes": "ms-settings:",
    "configuracoes do windows": "ms-settings:",
}

PASTAS_MENU_INICIAR = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
]


def _atalhos() -> list[Path]:
    achados = []
    for pasta in PASTAS_MENU_INICIAR:
        if pasta.is_dir():
            achados += pasta.rglob("*.lnk")
    return achados


def _apelidos() -> dict[str, str]:
    return {normalize(k): v for k, v in config.apps.items()}


def _por_nome_de_atalho(alvo: str) -> Path | None:
    """Casa `alvo` (já normalizado) contra o nome dos atalhos do Menu Iniciar.
    Exato bate primeiro; sem isso "excel" podia perder pra "excel starter"."""
    exato, contem, melhor_contem = None, None, 10_000
    for atalho in _atalhos():
        cand = normalize(atalho.stem)
        if cand == alvo:
            return atalho
        if alvo in cand and len(cand) < melhor_contem:
            contem, melhor_contem = atalho, len(cand)
    return exato or contem


def resolver(nome_falado: str) -> tuple[str | None, str | None]:
    """(alvo pro os.startfile, nome bonito pra confirmar) ou (None, None).

    Cobre programa clássico (.exe/.lnk). Quem só existe como app da Microsoft
    Store — sem atalho em arquivo, ex.: WhatsApp — cai no fallback de
    `_resolver_uwp`, que é mais lento (consulta os pacotes instalados).
    """
    alvo = normalize(nome_falado)
    if not alvo:
        return None, None

    if alvo in EMBUTIDOS:
        return EMBUTIDOS[alvo], nome_falado

    apelido = _apelidos().get(alvo)
    if apelido:
        # o apelido pode já ser um caminho/exe (funciona direto no os.startfile)
        # ou o nome de exibição de um atalho ("Google Chrome") — que só abre de
        # verdade se a gente achar o .lnk correspondente primeiro
        atalho = _por_nome_de_atalho(normalize(apelido))
        return (str(atalho), atalho.stem) if atalho else (apelido, nome_falado)

    atalho = _por_nome_de_atalho(alvo)
    if atalho:
        return str(atalho), atalho.stem
    return None, None


def _apps_da_store() -> list[tuple[str, str]]:
    """[(nome de exibição, AppID pro shell:AppsFolder), ...] dos pacotes UWP
    instalados. Custa ~1s (um processo PowerShell) — só roda quando a busca
    normal não achou nada, então o caminho comum continua instantâneo."""
    script = (
        "$out = @()\n"
        "foreach ($p in Get-AppxPackage) {\n"
        "  try {\n"
        "    $m = Get-AppxPackageManifest $p -ErrorAction Stop\n"
        "    $app = $m.Package.Applications.Application | Select-Object -First 1\n"
        "    if ($app) {\n"
        "      $disp = $m.Package.Properties.DisplayName\n"
        "      if ($disp -notmatch '^ms-resource:') {\n"
        "        $out += $disp + '|' + $p.PackageFamilyName + '!' + $app.Id\n"
        "      }\n"
        "    }\n"
        "  } catch {}\n"
        "}\n"
        "$out -join \"`n\""
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning("não consegui listar os apps da Store: %s", e)
        return []
    pares = []
    for linha in r.stdout.splitlines():
        if "|" in linha:
            nome, app_id = linha.split("|", 1)
            pares.append((nome.strip(), app_id.strip()))
    return pares


def _resolver_uwp(alvo: str) -> tuple[str | None, str | None]:
    exato, contem, melhor_contem = None, None, 10_000
    for nome, app_id in _apps_da_store():
        cand = normalize(nome)
        if cand == alvo:
            return app_id, nome
        if alvo in cand and len(cand) < melhor_contem:
            contem, melhor_contem = (app_id, nome), len(cand)
    return exato or (contem or (None, None))


async def abrir(nome_falado: str) -> dict:
    alvo, bonito = resolver(nome_falado)
    if alvo:
        try:
            await asyncio.to_thread(os.startfile, alvo)  # não bloqueia; thread por garantia
            log.info("abrindo %r (pedido: %r)", alvo, nome_falado)
            return {"ok": True, "aberto": bonito}
        except OSError as e:
            log.warning("falhou abrir %r: %s", alvo, e)
            return {"ok": False, "erro": str(e)}

    app_id, bonito = await asyncio.to_thread(_resolver_uwp, normalize(nome_falado))
    if app_id:
        try:
            # apps da Store não têm um .exe pra apontar: só abrem por este atalho
            await asyncio.to_thread(
                subprocess.run, ["explorer.exe", f"shell:AppsFolder\\{app_id}"], timeout=10)
            log.info("abrindo (store) %r (pedido: %r)", app_id, nome_falado)
            return {"ok": True, "aberto": bonito}
        except (subprocess.SubprocessError, OSError) as e:
            log.warning("falhou abrir (store) %r: %s", app_id, e)
            return {"ok": False, "erro": str(e)}

    return {"ok": False, "erro": f"não achei um programa chamado '{nome_falado}'"}
