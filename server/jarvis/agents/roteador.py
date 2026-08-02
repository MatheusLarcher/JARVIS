"""O primeiro a te atender: decide o que fazer com o que você falou.

Ele é pequeno e rápido de propósito. Faz só duas coisas:
  - responde na hora o que é trivial ("que horas são", "só um momento");
  - ou escolhe QUAL agente cuida do pedido.

Não tenta resolver tarefa: quem faz é o agente escolhido.

Formato da resposta dele é propositalmente burro (uma linha), porque modelo
pequeno erra JSON e formatos aninhados. Se vier qualquer coisa fora do padrão,
cai no agente de conversa — nunca trava.
"""
import logging
import re
import time

from ..config import config
from ..intents.router import normalize

log = logging.getLogger("jarvis.roteador")

PADRAO_AGENTE = re.compile(r"agente\s*[:=]\s*([a-zà-ú_]+)", re.IGNORECASE)
PADRAO_RESPOSTA = re.compile(r"resposta\s*[:=]\s*(.+)", re.IGNORECASE | re.DOTALL)

# Responder direto SÓ vale pra papo social. Um modelo de 0.8b, deixado solto,
# inventa fato com a maior naturalidade — no teste ele respondeu "aumenta o
# volume" com uma explicação falsa em vez de mandar pro agente do sistema.
SOCIAL = re.compile(
    r"^(oi|ola|opa|e ai|salve|bom dia|boa tarde|boa noite|tudo bem|tudo bom|"
    r"obrigad[oa]|brigad[oa]|valeu|vlw|tchau|falou|ate mais|ate logo|beleza)\b")

# o modelo pequeno às vezes devolve o próprio molde ("<uma frase curta>") ou
# uma sobra de formatação — isso não pode virar áudio
LIXO = re.compile(r"[<>{}\[\]]|^\s*(resposta|agente)\s*$", re.IGNORECASE)

SEM_VALOR = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "que",
             "um", "uma", "me", "meu", "minha", "pra", "para", "por", "no",
             "na", "em", "com", "eh", "se", "ao", "aos", "esta", "estao"}


class Decisao:
    def __init__(self, agente: str | None = None, resposta: str | None = None,
                 confianca: str = "alta", motivo: str = "", bruto: str = ""):
        self.agente = agente
        self.resposta = resposta
        self.confianca = confianca
        self.motivo = motivo
        self.bruto = bruto

    def para_dict(self) -> dict:
        return {"agente": self.agente, "resposta_direta": bool(self.resposta),
                "confianca": self.confianca, "motivo": self.motivo,
                "bruto": self.bruto[:200]}

    def __repr__(self):
        return (f"Decisao(agente={self.agente!r}, "
                f"resposta={'sim' if self.resposta else 'não'}, "
                f"confianca={self.confianca})")


def agentes_disponiveis() -> list[dict]:
    """Lista da config, tirando os que dependem da nuvem se ela não der pra usar.

    "Não der pra usar" inclui ligada mas SEM a chave no ambiente — oferecer o
    agente nesse caso faria toda pergunta difícil morrer em erro de
    autenticação e voltar como "não entendi".
    """
    from .especialistas import nuvem_disponivel

    nuvem_ok = nuvem_disponivel()[0] is not None
    lista = []
    for a in config.settings.get("agentes", {}).get("lista", []):
        if a.get("requer_nuvem") and not nuvem_ok:
            continue
        lista.append(a)
    return lista


def pode_responder_direto(transcricao: str) -> bool:
    """Só papo social. Qualquer coisa com fato, estado ou ação vai pro agente."""
    return bool(SOCIAL.match(normalize(transcricao or "")))


def _palavras(texto: str) -> set[str]:
    return {p for p in normalize(texto or "").split()
            if len(p) > 2 and p not in SEM_VALOR}


def palpite_por_palavras(transcricao: str, agentes: list[dict]) -> str | None:
    """Rede de segurança sem LLM: escolhe o agente pelas palavras em comum com
    a descrição e os exemplos dele. Usado quando o modelo não deu uma decisão
    aproveitável — é instantâneo e não erra pra pior que o acaso."""
    minhas = _palavras(transcricao)
    if not minhas:
        return None
    melhor, pontos_melhor = None, 0
    for a in agentes:
        texto = " ".join([a.get("descricao", "")] + list(a.get("exemplos") or []))
        pontos = len(minhas & _palavras(texto))
        if pontos > pontos_melhor:
            melhor, pontos_melhor = a["nome"], pontos
    return melhor


def _instrucao(agentes: list[dict]) -> str:
    linhas = [f"- {a['nome']}: {a['descricao']}" for a in agentes]
    exemplos = []
    for a in agentes:
        # os exemplos são o que mais move a agulha num modelo pequeno; vale o
        # custo dos tokens a mais (medido: sem o 3º, "temperatura" ia pro
        # agente errado)
        for ex in (a.get("exemplos") or [])[:3]:
            exemplos.append(f'"{ex}" -> AGENTE: {a["nome"]}')
    return (
        "Você é o JARVIS. Sua única tarefa agora é decidir o que fazer com o "
        "pedido do Matheus, em português do Brasil.\n\n"
        "Se for só cumprimento ou agradecimento, responda direto:\n"
        "RESPOSTA: <uma frase curta>\n\n"
        "Em TODO o resto — qualquer ação, informação, estado ou pergunta — "
        "você NÃO responde: escolhe um agente e escreve:\n"
        "AGENTE: <nome>\n\n"
        "Nunca invente informação. Na dúvida, escolha um agente.\n\n"
        "Agentes disponíveis:\n" + "\n".join(linhas) + "\n\n"
        "Exemplos:\n" + "\n".join(exemplos) + "\n\n"
        "Responda APENAS com uma dessas duas linhas, nada mais."
    )


def interpretar(texto: str, agentes: list[dict]) -> Decisao:
    """Lê a saída do modelo pequeno e transforma numa decisão utilizável."""
    nomes = {a["nome"] for a in agentes}
    bruto = (texto or "").strip()

    m = PADRAO_AGENTE.search(bruto)
    if m:
        escolhido = m.group(1).strip().lower()
        if escolhido in nomes:
            return Decisao(agente=escolhido, motivo="escolha explícita", bruto=bruto)
        # falou um nome que não existe: aproveita se for parecido com algum
        for nome in nomes:
            if nome.startswith(escolhido[:4]) or escolhido.startswith(nome[:4]):
                return Decisao(agente=nome, confianca="baixa",
                               motivo=f"nome inválido ({escolhido}), aproximei",
                               bruto=bruto)
        return Decisao(agente=None, confianca="baixa",
                       motivo=f"agente inexistente: {escolhido}", bruto=bruto)

    m = PADRAO_RESPOSTA.search(bruto)
    if m:
        resposta = m.group(1).strip().strip('"')
        if resposta and not LIXO.search(resposta) and len(resposta) > 2:
            return Decisao(resposta=resposta, motivo="respondeu direto", bruto=bruto)
        if resposta:
            return Decisao(agente=None, confianca="baixa",
                           motivo="resposta era molde/lixo", bruto=bruto)

    # veio fora do formato: se citou o nome de um agente, usa; senão desiste
    minusculo = bruto.lower()
    for nome in nomes:
        if nome in minusculo:
            return Decisao(agente=nome, confianca="baixa",
                           motivo="formato inesperado, achei o nome no texto",
                           bruto=bruto)
    return Decisao(agente=None, confianca="baixa",
                   motivo="não entendi a decisão", bruto=bruto)


async def decidir(transcricao: str) -> tuple[Decisao, float]:
    """Devolve a decisão e quanto tempo levou."""
    from litellm import acompletion

    from .agent import _extras_llm

    agentes = agentes_disponiveis()
    cfg = config.settings["llm"]
    modelo = config.settings.get("agentes", {}).get("roteador", {}).get(
        "modelo") or cfg["model"]
    extras = {**_extras_llm(cfg), "max_tokens": 40}

    t0 = time.perf_counter()
    try:
        r = await acompletion(
            model=modelo,
            messages=[{"role": "system", "content": _instrucao(agentes)},
                      {"role": "user", "content": transcricao}],
            **extras)
        texto = (r.choices[0].message.content or "")
    except Exception as e:
        log.warning("roteador falhou (%s); mandando pra conversa", e)
        return Decisao(agente=_padrao(agentes), confianca="baixa",
                       motivo=f"erro no roteador: {type(e).__name__}"), \
            time.perf_counter() - t0

    decisao = interpretar(texto, agentes)

    if decisao.resposta and not pode_responder_direto(transcricao):
        # ele tentou responder algo que não é papo: descarta e manda pro agente
        log.info("recusei resposta direta (%r): não é social", decisao.resposta[:60])
        decisao.resposta = None
        decisao.confianca = "baixa"
        decisao.motivo = "quis responder sozinho um pedido que não é social"

    if decisao.agente is None and decisao.resposta is None:
        decisao.agente = (palpite_por_palavras(transcricao, agentes)
                          or _padrao(agentes))       # nunca trava
        if decisao.confianca == "alta":
            decisao.confianca = "baixa"

    log.info("rota: %s (%.2fs) %s", decisao, time.perf_counter() - t0, decisao.motivo)
    return decisao, time.perf_counter() - t0


def _padrao(agentes: list[dict]) -> str:
    nomes = [a["nome"] for a in agentes]
    return "conversa" if "conversa" in nomes else (nomes[0] if nomes else "conversa")
