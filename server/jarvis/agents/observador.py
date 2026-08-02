"""O observador: olha o que deu errado e anota o porquê.

Ele NÃO está no caminho da resposta — roda depois, em segundo plano, e nunca
atrasa o JARVIS. Também não analisa tudo: só o que deu sinal de problema
(config `observador.quando`), pra não gastar API à toa.

O que ele produz vira anotação no registro (memory/db.py → tabela registros) e
é o material pra depois corrigir prompt, exemplos de rota ou treinar o modelo
pequeno com o seu jeito de falar.
"""
import json
import logging
import re

from ..config import config
from ..memory.db import store

log = logging.getLogger("jarvis.observador")

BASE = (
    "Você revisa interações de um assistente de voz doméstico chamado JARVIS, "
    "em português do Brasil. Recebe o que a pessoa falou (transcrito por "
    "reconhecimento de voz, pode ter erro), para onde o pedido foi e o que o "
    "assistente respondeu.\n\n"
    "Como o JARVIS decide, do mais rápido pro mais caro:\n"
    "1. regra local (destino 'local'): resolve na hora, sem modelo nenhum. "
    "É o MELHOR caminho — se o pedido foi resolvido assim e a resposta serve, "
    "está CERTO, não sugira agente;\n"
    "2. roteador (modelo pequeno): escolhe um dos agentes abaixo;\n"
    "3. agente escolhido: executa e responde.\n\n"
    "Agentes existentes (use só estes nomes): {agentes}\n\n"
    "Responda SOMENTE um JSON assim:\n"
    '{{"agente_correto": "<nome ou null>", "transcricao_correta": "<texto ou null>", '
    '"observacao": "<uma frase sobre o que deu errado e o que fazer>"}}\n\n'
    "Use null quando estiver certo. Seja concreto: 'devia ter ido pra casa, "
    "é comando de luz' vale mais que 'rota inadequada'."
)


def _instrucao() -> str:
    from .roteador import agentes_disponiveis
    nomes = ", ".join(f"{a['nome']} ({a['descricao']})"
                      for a in agentes_disponiveis())
    return BASE.format(agentes=nomes)


def ativo() -> bool:
    return bool(config.settings.get("observador", {}).get("ativo"))


def _gatilhos_ligados() -> set[str]:
    return set(config.settings.get("observador", {}).get("quando", []))


async def motivo_para_analisar(device_id: str, transcricao: str, rota: dict,
                               erro: str | None,
                               registro_id: int | None = None) -> str | None:
    """Por que esta interação merece uma olhada? None = não merece."""
    ligados = _gatilhos_ligados()
    if erro and "tarefa_falhou" in ligados:
        return "tarefa_falhou"
    if "roteador_incerto" in ligados and rota.get("confianca") == "baixa":
        return "roteador_incerto"
    if "pedido_repetido" in ligados and await store.pedido_repetido(
            device_id, transcricao, ignorar_id=registro_id):
        return "pedido_repetido"
    return None


def _extrair_json(texto: str) -> dict:
    """O modelo às vezes embrulha o JSON em ``` ou escreve algo antes."""
    m = re.search(r"\{.*\}", texto or "", re.DOTALL)
    if not m:
        return {}
    try:
        dados = json.loads(m.group(0))
        return dados if isinstance(dados, dict) else {}
    except json.JSONDecodeError:
        return {}


def _modelo_e_extras() -> tuple[str, dict]:
    """Preferência: nuvem (mais esperta). Sem nuvem, usa o modelo local."""
    from .especialistas import nuvem_disponivel

    modelo, extras = nuvem_disponivel()
    if modelo:
        return modelo, extras
    cfg = config.settings["llm"]
    from .agent import _extras_llm
    return cfg["model"], _extras_llm(cfg)


async def analisar(registro_id: int, transcricao: str, agente: str,
                   resposta: str, motivo: str) -> dict | None:
    """Roda o modelo e grava a anotação. Falha aqui nunca afeta o usuário."""
    if not ativo() or not registro_id:
        return None
    try:
        from litellm import acompletion

        modelo, extras = _modelo_e_extras()
        # max_tokens dentro do dict: se vier também nos extras, passar solto
        # quebra a chamada ("multiple values for keyword argument")
        extras = {**extras, "max_tokens": 300}
        destino = ("regra local (sem modelo)" if agente in ("local", "roteador")
                   else f"agente {agente}")
        pedido = (f"Motivo da revisão: {motivo}\n"
                  f"Pessoa falou: {transcricao!r}\n"
                  f"Foi para: {destino}\n"
                  f"JARVIS respondeu: {resposta!r}")
        r = await acompletion(
            model=modelo,
            messages=[{"role": "system", "content": _instrucao()},
                      {"role": "user", "content": pedido}], **extras)
        dados = _extrair_json(r.choices[0].message.content or "")
        if not dados.get("observacao"):
            return None
        await store.anotar_registro(
            registro_id,
            observacao=f"[{motivo}] {dados['observacao']}",
            agente_correto=dados.get("agente_correto") or None,
            transcricao_correta=dados.get("transcricao_correta") or None)
        log.info("observador (%s): %s", motivo, dados["observacao"][:100])
        return dados
    except Exception as e:
        log.warning("observador não conseguiu analisar: %s", e)
        return None
