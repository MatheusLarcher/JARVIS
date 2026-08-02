"""Mostra o que o JARVIS guardou das últimas interações: rota, resposta,
áudio gravado e o que o observador anotou.

É por aqui que se enxerga onde ele erra com a SUA voz.
Uso: python tests/ver_registros.py [quantos]
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "server" / "data"
DB = DATA / "jarvis.db"
QUANTOS = int(sys.argv[1]) if len(sys.argv) > 1 else 10

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
linhas = con.execute(
    "SELECT id, ts, transcricao, audio_path, agente, rota_json, resposta, erro, "
    "revisado, observacao, agente_correto, transcricao_correta, metricas_json "
    "FROM registros ORDER BY id DESC LIMIT ?", (QUANTOS,)).fetchall()

for (rid, ts, tr, audio, ag, rota_j, resp, erro, rev, obs, agc, trc,
     met_j) in reversed(linhas):
    rota = json.loads(rota_j or "{}")
    met = json.loads(met_j or "{}")
    quando = datetime.fromtimestamp(ts).strftime("%d/%m %H:%M:%S")
    wav = DATA / audio if audio else None
    kb = wav.stat().st_size // 1024 if wav and wav.exists() else 0

    print(f"\n#{rid}  {quando}   {tr!r}")
    destino = ag or "?"
    if rota.get("confianca"):
        destino += f" (confiança {rota['confianca']}: {rota.get('motivo', '')})"
    print(f"    destino : {destino}")
    print(f"    resposta: {(resp or '')[:90]!r}")
    if erro:
        print(f"    ERRO    : {erro}")
    print(f"    áudio   : {audio or '(não gravado)'} {f'({kb} KB)' if kb else ''}")
    if rota.get("duracao_s"):
        print(f"    roteador: {rota['duracao_s']}s")
    interessantes = {k: v for k, v in met.items() if isinstance(v, (int, float))}
    if interessantes:
        print("    tempos  : " + ", ".join(f"{k}={v}" for k, v in
                                           list(interessantes.items())[:6]))
    if rev:
        print(f"    OBSERVADOR: {obs}")
        if agc:
            print(f"       agente certo seria: {agc}")
        if trc:
            print(f"       transcrição certa : {trc!r}")

con.close()
print(f"\n({len(linhas)} registros; áudio em {DATA / 'gravacoes'})")
