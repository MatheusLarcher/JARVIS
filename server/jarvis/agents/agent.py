"""Agente Google ADK — fallback quando o Intent Router não conhece o pedido.

LLM via LiteLlm (provedor trocável em config/settings.yml → llm.model).
Ferramentas: controle da casa e informações; MCPs entram aqui no futuro
(jarvis/mcp/ → MCPToolset do ADK).
"""
import asyncio
import logging
import time

from ..config import config
from ..context.engine import DeviceContext
from ..home_assistant.client import ha, resolve_light_entity
from ..mcp.loader import load_toolsets
from ..memory.db import store

log = logging.getLogger("jarvis.agent")

_runner = None
_session_service = None
APP = "jarvis"


async def _tool_controlar_luz(acao: str, comodo: str) -> dict:
    """Liga ou desliga a luz de um cômodo. acao: 'ligar' ou 'desligar'. comodo: sala, quarto, escritorio."""
    entity = resolve_light_entity(comodo)
    if not entity:
        return {"ok": False, "erro": f"cômodo desconhecido: {comodo}"}
    ok = await ha.call_service("light", "turn_on" if acao == "ligar" else "turn_off", entity)
    return {"ok": ok}


async def _tool_temperatura() -> dict:
    """Retorna a temperatura ambiente atual em graus Celsius."""
    return {"temperatura_c": await ha.temperature()}


def _extras_llm(cfg: dict) -> dict:
    """Parâmetros que vão junto em toda chamada ao modelo."""
    extras = {}
    if cfg.get("api_base"):
        # sem isto o LiteLLM tenta a nuvem em vez do Ollama local
        extras["api_base"] = cfg["api_base"]
    if cfg.get("no_think"):
        # o Qwen3.x gasta a resposta inteira "pensando" e devolve texto VAZIO;
        # medido: 3,39s e nada contra 0,29s com resposta
        extras["think"] = False
    if cfg.get("max_tokens"):
        # resposta curta também encurta a síntese de voz, que é o gargalo
        extras["max_tokens"] = int(cfg["max_tokens"])
    return extras


class _CortaResposta:
    """Corta a resposta na primeira frase.

    Modelo pequeno não obedece "responda em uma frase": ele se estende, comenta
    as próprias instruções ("sem adições desnecessárias como Claro") e cada
    palavra a mais vira segundos de fala. Aqui o corte é garantido, no servidor.

    Funciona no stream: assim que a primeira frase fecha, para de emitir.
    """

    FIM = ".!?…"

    def __init__(self, max_frases: int = 1, max_palavras: int = 25):
        self.max_frases = max_frases
        self.max_palavras = max_palavras
        self.frases = 0
        self.palavras = 0
        self.encerrado = False

    def feed(self, texto: str) -> str:
        if self.encerrado or not texto:
            return ""
        saida = []
        for ch in texto:
            saida.append(ch)
            if ch.isspace():
                self.palavras += 1
                if self.palavras >= self.max_palavras:
                    # estourou o tamanho: fecha a frase aqui mesmo
                    self.encerrado = True
                    return "".join(saida).rstrip() + "."
            if ch in self.FIM:
                self.frases += 1
                if self.frases >= self.max_frases:
                    self.encerrado = True
                    return "".join(saida)
        return "".join(saida)


class _FiltroPensamento:
    """Tira o raciocínio (<think>...</think>) do texto que vai virar fala.

    Os Qwen3.x às vezes "pensam em voz alta" mesmo com /no_think, e isso não
    pode ser falado. Funciona no stream, sem esperar a resposta fechar.
    """

    ABRE, FECHA = "<think>", "</think>"

    def __init__(self):
        self.pensando = False
        self.pendente = ""      # pedaço de tag que pode ter vindo partido

    @staticmethod
    def _inicio_de_tag(buffer: str, tag: str) -> int:
        """Quantos caracteres do fim do buffer podem ser o começo da tag."""
        for n in range(min(len(tag) - 1, len(buffer)), 0, -1):
            if tag.startswith(buffer[-n:]):
                return n
        return 0

    def feed(self, texto: str) -> str:
        buffer = self.pendente + texto
        self.pendente = ""
        saida = []
        while buffer:
            alvo = self.FECHA if self.pensando else self.ABRE
            pos = buffer.find(alvo)
            if pos == -1:
                # a tag pode estar chegando partida: segura só esse pedacinho
                n = self._inicio_de_tag(buffer, alvo)
                if n:
                    self.pendente = buffer[-n:]
                    buffer = buffer[:-n]
                if not self.pensando:
                    saida.append(buffer)
                return "".join(saida)
            if not self.pensando:
                saida.append(buffer[:pos])
            buffer = buffer[pos + len(alvo):]
            self.pensando = not self.pensando
        return "".join(saida)


def _instrucao(llm_cfg: dict) -> str:
    texto = (
        "Você é o JARVIS, assistente pessoal do Matheus, em português do Brasil. "
        "REGRA MAIS IMPORTANTE: responda em UMA única frase curta, de no máximo "
        "20 palavras. Nunca escreva mais de uma frase. "
        "Sua resposta é falada em voz alta, então: sem markdown, sem listas, "
        "sem emojis, sem repetir a pergunta, sem saudação, sem 'Claro' e sem "
        "explicar o que você vai fazer. Diga só a resposta, direto. "
        "Se não souber, diga apenas que não sabe, em poucas palavras. "
        "Use as ferramentas quando o pedido envolver a casa."
    )
    # nos modelos Qwen3.x isto desliga o "pensar antes de responder"
    if llm_cfg.get("no_think"):
        texto += " /no_think"
    return texto


def _build():
    global _runner, _session_service
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    llm_cfg = config.settings["llm"]
    agent = Agent(
        name="jarvis",
        model=LiteLlm(model=llm_cfg["model"], **_extras_llm(llm_cfg)),
        description="JARVIS, assistente pessoal do Matheus.",
        instruction=_instrucao(llm_cfg),
        tools=[_tool_controlar_luz, _tool_temperatura, *load_toolsets()],
    )
    _session_service = InMemorySessionService()
    _runner = Runner(agent=agent, app_name=APP, session_service=_session_service)


async def aquecer():
    """Monta os agentes e abre a conexão com o provedor no start do servidor.

    Sem isto, a PRIMEIRA pergunta paga tudo isso e demora ~5,5s em vez de ~0,8s
    (medido em tests/diag_llm_stream.py). E como quem atende agora é sempre um
    especialista, aquecer só o agente antigo não adiantava nada: cada agente
    era montado a frio, dentro do event loop, na primeira vez que era escolhido.
    """
    try:
        from .especialistas import construir
        from .roteador import agentes_disponiveis
        for a in agentes_disponiveis():
            try:
                # montar agente do ADK é síncrono e pesado: fora do event loop
                await asyncio.to_thread(construir, a["nome"])
            except Exception as e:
                log.warning("não deu pra montar o agente '%s': %s", a["nome"], e)
        from litellm import acompletion
        cfg = config.settings["llm"]
        # max_tokens tem que ir DENTRO do dict: _extras_llm já traz o dele e
        # passar solto dá "multiple values for keyword argument" — o aquecimento
        # falhava calado e a 1a pergunta voltava a custar ~4,5s
        extras = {**_extras_llm(cfg), "max_tokens": 1}
        # com modelo local, esta chamada também tira o modelo do disco e o
        # deixa carregado — a primeira pergunta de verdade já sai rápida
        await acompletion(model=cfg["model"],
                          messages=[{"role": "user", "content": "oi"}], **extras)
        log.info("agente pronto (aquecido): %s", cfg["model"])
        await _aquecer_nuvem()
    except Exception as e:
        log.warning("não deu pra aquecer o agente agora: %s", e)


async def _aquecer_nuvem():
    """Abre a conexão com o provedor externo antes de alguém precisar dela.

    DNS + TLS + cliente do litellm custam caro na PRIMEIRA chamada: medido
    5,57s contra 0,69s nas seguintes (tests/bench_nuvem_primeira_chamada.py).
    Como a nuvem só atende pergunta difícil, isso caía justo na hora em que a
    pessoa mais espera resposta.
    """
    from .especialistas import nuvem_disponivel

    modelo, extras = nuvem_disponivel()
    if not modelo:
        return
    try:
        from litellm import acompletion
        # max_tokens=1 NÃO serve aqui: o modelo raciocina antes de escrever e
        # estoura o limite ("Could not finish the message"), aquecimento perdido
        await acompletion(model=modelo,
                          messages=[{"role": "user", "content": "diga oi"}],
                          max_tokens=32, **extras)
        log.info("nuvem pronta (aquecida): %s", modelo)
    except Exception as e:
        log.warning("não deu pra aquecer a nuvem: %s", e)


_ultimo_despertar = 0.0


async def despertar_gpu():
    """Tira a GPU do modo econômico assim que você chama o JARVIS.

    A placa cai pra 225 MHz quando fica parada e a primeira inferência paga o
    "acordar": medido 2,61s contra 0,80s com ela desperta. Como isso roda no
    wake, a GPU acorda enquanto você ainda está falando o comando — de graça.
    """
    global _ultimo_despertar
    agora = time.monotonic()
    if agora - _ultimo_despertar < 5:      # já acordou há pouco
        return
    _ultimo_despertar = agora
    async def llm():
        from litellm import acompletion
        cfg = config.settings["llm"]
        extras = {**_extras_llm(cfg), "max_tokens": 1}
        await acompletion(model=cfg["model"],
                          messages=[{"role": "user", "content": "oi"}], **extras)

    async def voz():
        import httpx
        url = config.settings["tts"]["voice_profiles"]["jarvis_br"].get("service_url")
        if url:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{url}/aquecer")

    # os dois usam a mesma GPU; acorda em paralelo e ignora falha
    await asyncio.gather(llm(), voz(), return_exceptions=True)


async def _montar_prompt(transcript: str, ctx: DeviceContext) -> str:
    """Prompt curto de propósito: em modelo pequeno, cada linha a mais atrasa
    a primeira palavra (medido: histórico gordo levou o tempo de 0,4s a 2,4s)."""
    cfg = config.settings["llm"]
    trocas = int(cfg.get("historico_trocas", 2))
    limite = int(cfg.get("historico_max_chars", 160))
    # conversa de horas atrás não é contexto, é ruído — ver db.recent_history
    idade = float(cfg.get("historico_max_idade_min", 10)) * 60

    history = (await store.recent_history(ctx.device_id, limit=trocas,
                                          max_idade_s=idade)) if trocas else []
    linhas = []
    for h in history:
        if not h["jarvis"]:
            continue
        resposta = h["jarvis"][:limite]
        linhas.append(f"Usuário: {h['user'][:limite]}\nJARVIS: {resposta}")
    hist_txt = "\n".join(linhas)
    # O pedido de AGORA precisa vir marcado. Sem isso ele ficava colado no fim
    # do histórico e o modelo pequeno respondia a pergunta ANTERIOR (o agente
    # "conversa", perguntado sobre o descobrimento do Brasil, falou de energia
    # solar — assunto da interação passada).
    return (
        f"[dispositivo={ctx.device_type}, local={ctx.place}, cômodo={ctx.room}]\n"
        + (f"[conversa anterior, só como contexto]\n{hist_txt}\n\n" if hist_txt else "")
        + f"PEDIDO AGORA: {transcript}\n"
        + "Responda APENAS a este pedido."
    )


async def ask_stream(transcript: str, ctx: DeviceContext, agente: str | None = None):
    """Roda o agente e vai entregando o texto conforme ele escreve.

    Isso é o que permite começar a falar antes do LLM terminar. Cada item é um
    trecho NOVO de texto (não o acumulado).

    `agente` escolhe um especialista (agents/especialistas.py); sem ele, usa o
    agente único de sempre.
    """
    global _runner
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.genai import types

    if agente:
        from .especialistas import construir
        runner, sessoes, app = (*construir(agente), f"jarvis_{agente}")
    else:
        if _runner is None:
            _build()
        runner, sessoes, app = _runner, _session_service, APP

    prompt = await _montar_prompt(transcript, ctx)
    session = await sessoes.create_session(app_name=app, user_id=ctx.user_id)
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    enviado = ""
    filtro = _FiltroPensamento()
    cfg_llm = config.settings["llm"]
    corte = _CortaResposta(int(cfg_llm.get("max_frases", 1)),
                           int(cfg_llm.get("max_palavras", 25)))
    try:
        async for event in runner.run_async(
                user_id=ctx.user_id, session_id=session.id, new_message=content,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE)):
            if not (event.content and event.content.parts):
                continue
            texto = "".join(p.text or "" for p in event.content.parts)
            if not texto:
                continue
            if getattr(event, "partial", False):
                # o LLM entrega token a token e um token pode ser só um pedaço
                # de palavra ("del"+"imit"+"ada") — nunca mexer no espaçamento
                novo = texto[len(enviado):] if texto.startswith(enviado) else texto
                if novo:
                    enviado += novo
                    limpo = corte.feed(filtro.feed(novo))
                    if limpo:
                        yield limpo
                    if corte.encerrado:
                        return          # já disse o que tinha que dizer
            elif event.is_final_response():
                # o final repete tudo: só emite o que faltou (comparação exata,
                # sem strip, pra não comer espaços e colar palavras)
                if texto.startswith(enviado):
                    resto = texto[len(enviado):]
                elif not enviado:
                    resto = texto
                else:
                    resto = ""
                if resto:
                    enviado += resto
                    # PRECISA passar pelo filtro e pelo corte também aqui. Quando
                    # o evento chega sem parcial (acontece depois de chamada de
                    # ferramenta), este ramo entregava o texto CRU: o <think> ia
                    # parar na voz e o limite de tamanho não valia.
                    limpo = corte.feed(filtro.feed(resto))
                    if limpo:
                        yield limpo
                    if corte.encerrado:
                        return
    except Exception:
        log.exception("agente falhou")
    finally:
        # sessão é descartável (histórico vem do SQLite); sem isso vaza memória no 24/7
        try:
            await sessoes.delete_session(app_name=app, user_id=ctx.user_id,
                                         session_id=session.id)
        except Exception:
            pass


async def ask(transcript: str, ctx: DeviceContext, agente: str | None = None) -> str | None:
    """Resposta completa (sem streaming) — usado em testes e como reserva."""
    partes = [p async for p in ask_stream(transcript, ctx, agente)]
    texto = "".join(partes).strip()
    return texto or None
