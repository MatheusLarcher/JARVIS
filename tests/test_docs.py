"""A documentação aponta pra coisas que existem de verdade?

Documento errado é pior que documento nenhum: manda a pessoa (ou eu, daqui a
um mês) pra um arquivo que não existe. Confere:
  - todo link markdown pra arquivo do projeto aponta pra algo real;
  - todo caminho de arquivo citado em crase (`server/...`, `tests/...`) existe.

Roda sem servidor e sem GPU.
Uso: python tests/test_docs.py
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOCS = [RAIZ / "README.md"] + sorted((RAIZ / "docs").glob("*.md"))

LINK = re.compile(r"\[[^\]]+\]\(([^)#]+?)(?:#[^)]*)?\)")
CAMINHO = re.compile(r"`((?:server|apps|config|tests|docs)/[\w./*-]+)`")

# citados de propósito sem existir no repo (o usuário cria, ou são gerados)
ESPERADOS_AUSENTES = {
    "config/.env",
    "config/devices.yml",
    "server/data/voice/jarvis_ref.wav",
    "server/data/gravacoes/",
    "apps/android/*.keystore",
    "apps/android/jarvis-release.keystore",
    "apps/web/dist",
    "server/data/jarvis.db",
    "server/data/tts_cache/",
}


def existe(caminho: str) -> bool:
    limpo = caminho.rstrip("/")
    if "*" in limpo:
        pai = Path(limpo).parent
        return (RAIZ / pai).exists()
    return (RAIZ / limpo).exists()


def main():
    problemas = []
    conferidos = {"links": 0, "caminhos": 0}
    for doc in DOCS:
        texto = doc.read_text(encoding="utf-8")
        rel = doc.relative_to(RAIZ).as_posix()

        for alvo in LINK.findall(texto):
            if alvo.startswith(("http://", "https://", "mailto:")):
                continue
            conferidos["links"] += 1
            destino = (doc.parent / alvo).resolve()
            if not destino.exists():
                problemas.append(f"{rel}: link quebrado -> {alvo}")

        for caminho in set(CAMINHO.findall(texto)):
            if caminho in ESPERADOS_AUSENTES or caminho.rstrip("/") in ESPERADOS_AUSENTES:
                continue
            conferidos["caminhos"] += 1
            if not existe(caminho):
                problemas.append(f"{rel}: caminho citado nao existe -> {caminho}")

    print(f"{len(DOCS)} documentos | {conferidos['links']} links | "
          f"{conferidos['caminhos']} caminhos citados\n")
    for p in problemas:
        print(f"  FALHA {p}")

    # o teste tem que estar OLHANDO alguma coisa: se as expressões pararem de
    # casar (mudou o formato do doc), ele passaria sempre sem conferir nada
    if conferidos["links"] < 20 or conferidos["caminhos"] < 20:
        print("  FALHA o teste quase não achou o que conferir — regex quebrada?")
        problemas.append("cobertura")

    print("\n" + ("DOCUMENTACAO CONSISTENTE" if not problemas
                  else f"{len(problemas)} PROBLEMAS"))
    sys.exit(1 if problemas else 0)


main()
