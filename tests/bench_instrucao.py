"""Qual instrução faz o modelo pequeno responder curto SEM falar das regras.

O qwen3.5:0.8b estava repetindo o próprio prompt na resposta ("sem adições
desnecessárias como Claro"). Instrução longa e cheia de "não faça X" confunde
modelo pequeno. Aqui medimos tamanho da resposta e se ela vaza a instrução.

Uso: python tests/bench_instrucao.py     (env jarvis)
"""
import asyncio
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from jarvis.config import config  # noqa: E402

PERGUNTAS = [
    "quem foi santos dumont",
    "qual a capital da australia",
    "o que e um buraco negro",
    "quantos minutos tem duas horas e meia",
]

# palavras que denunciam o modelo comentando as próprias regras
VAZAMENTOS = ["frase", "palavra", "resposta é direta", "sem adições", "markdown",
              "emoji", "instru", "regra", "conciso", "curta"]

INSTRUCOES = {
    "atual (longa)": (
        "Você é o JARVIS, assistente pessoal do Matheus, em português do Brasil. "
        "REGRA MAIS IMPORTANTE: responda em UMA única frase curta, de no máximo "
        "20 palavras. Nunca escreva mais de uma frase. "
        "Sua resposta é falada em voz alta, então: sem markdown, sem listas, "
        "sem emojis, sem repetir a pergunta, sem saudação, sem 'Claro' e sem "
        "explicar o que você vai fazer. Diga só a resposta, direto. "
        "Se não souber, diga apenas que não sabe, em poucas palavras."),
    "curta positiva": (
        "Você é o JARVIS, assistente do Matheus. "
        "Responda em uma frase curta, em português do Brasil."),
    "curtíssima": "Responda em uma frase curta, em português.",
    "com exemplo": (
        "Você é o JARVIS, assistente do Matheus. Responda em português, "
        "sempre em uma frase curta.\n"
        "Exemplo:\nPergunta: quem foi Pelé\nResposta: Pelé foi um jogador "
        "brasileiro, considerado o melhor de todos os tempos."),
}


async def responde(instrucao: str, pergunta: str) -> str:
    from litellm import acompletion

    from jarvis.agents.agent import _extras_llm
    cfg = config.settings["llm"]
    r = await acompletion(
        model=cfg["model"],
        messages=[{"role": "system", "content": instrucao},
                  {"role": "user", "content": pergunta}],
        **_extras_llm(cfg))
    return (r.choices[0].message.content or "").strip()


async def main():
    print(f"modelo: {config.settings['llm']['model']}\n")
    print(f"{'instrução':18s} {'palavras':>9s} {'frases':>7s} {'vaza regra':>11s}")
    for nome, instrucao in INSTRUCOES.items():
        tamanhos, frases, vazou = [], [], 0
        exemplos = []
        for p in PERGUNTAS:
            texto = await responde(instrucao, p)
            tamanhos.append(len(texto.split()))
            frases.append(max(1, texto.count(".") + texto.count("!") + texto.count("?")))
            if any(v in texto.lower() for v in VAZAMENTOS):
                vazou += 1
            exemplos.append(texto)
        print(f"{nome:18s} {statistics.median(tamanhos):>9.0f} "
              f"{statistics.median(frases):>7.0f} {vazou:>7d}/{len(PERGUNTAS)}")
        print(f"      ex: {exemplos[1][:110]!r}", flush=True)


asyncio.run(main())
