"""O observador: quando ele entra e o que ele anota.

Duas partes:
  - gatilho: só analisa o que deu sinal de problema (não pode analisar tudo);
  - análise: chama o modelo de verdade e grava a anotação no registro.

A parte da análise precisa da chave da nuvem (ou do Ollama no ar).
Uso: python tests/test_observador.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.agents import observador  # noqa: E402
from jarvis.memory.db import store  # noqa: E402
from jarvis.memory.registro import Registro  # noqa: E402

CASOS_GATILHO = [
    # (rota, erro, deve analisar?)
    ({"confianca": "alta"}, None, False),
    ({"confianca": "baixa"}, None, True),
    ({"confianca": "alta"}, "ferramenta falhou", True),
    ({}, None, False),
]


async def main():
    fails = 0
    await store.open()
    print(f"observador ativo: {observador.ativo()}")
    print(f"gatilhos: {sorted(observador._gatilhos_ligados())}\n")

    print("== gatilho ==")
    for rota, erro, esperado in CASOS_GATILHO:
        motivo = await observador.motivo_para_analisar("teste-obs", "frase nova",
                                                       rota, erro)
        ok = bool(motivo) == esperado
        fails += not ok
        print(("OK  " if ok else "FAIL"),
              f"rota={rota} erro={erro!r} -> {motivo}")

    # A checagem roda DEPOIS de gravar. Sem ignorar o próprio id, a interação
    # se compara com ela mesma e tudo vira "repetido" — foi o que aconteceu no
    # primeiro teste com voz real (5 de 5 interações caíram no observador).
    r = Registro("teste-obs-novo", "sess-obs")
    r.transcricao = "abre a janela do escritorio"
    r.agente = "casa"
    rid_unico = await store.salvar_registro(r)
    motivo = await observador.motivo_para_analisar(
        "teste-obs-novo", r.transcricao, {"confianca": "alta"}, None,
        registro_id=rid_unico)
    ok = motivo is None
    fails += not ok
    print(("OK  " if ok else "FAIL"),
          f"frase inédita não pode ser 'repetida' -> {motivo}")

    # agora sim: a MESMA frase de novo, num segundo registro
    r2 = Registro("teste-obs-novo", "sess-obs")
    r2.transcricao = r.transcricao
    r2.agente = "casa"
    rid2 = await store.salvar_registro(r2)
    motivo = await observador.motivo_para_analisar(
        "teste-obs-novo", r2.transcricao, {"confianca": "alta"}, None,
        registro_id=rid2)
    ok = motivo == "pedido_repetido"
    fails += not ok
    print(("OK  " if ok else "FAIL"), f"mesma frase de novo -> {motivo}")

    print("\n== análise de verdade (chama o modelo) ==")
    r2 = Registro("teste-obs", "sess-obs")
    r2.transcricao = "jarvis apaga a luz do quarto"
    r2.agente = "conversa"          # rota errada de propósito
    r2.resposta = "Não sei fazer isso."
    rid = await store.salvar_registro(r2)
    dados = await observador.analisar(rid, r2.transcricao, r2.agente,
                                      r2.resposta, "roteador_incerto")
    if dados:
        print(f"   observação: {dados.get('observacao')}")
        print(f"   agente correto sugerido: {dados.get('agente_correto')}")
        anotados = [x for x in await store.registros_para_revisar(50)
                    if x["id"] == rid]
        gravou = not anotados        # saiu da fila de "não revisados"
        print(("OK  " if gravou else "FAIL"), "anotação gravada no registro")
        fails += not gravou
        if dados.get("agente_correto") != "casa":
            print(f"   AVISO: sugeriu {dados.get('agente_correto')!r}, "
                  "eu esperava 'casa' (não reprova o teste, é julgamento do modelo)")
    else:
        print("   FALHOU: não analisou (chave da nuvem? Ollama no ar?)")
        fails += 1

    await store.close()
    print("\n" + ("TODOS OS TESTES PASSARAM" if fails == 0 else f"{fails} FALHAS"))
    sys.exit(1 if fails else 0)


asyncio.run(main())
