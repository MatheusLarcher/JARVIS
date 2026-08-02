"""Orquestra uma interação: transcrição final → intent → skill/agente → resposta falada.

Ordem de decisão, do mais rápido pro mais caro:

  1. Intent Router local (regex, ~0ms) — comandos conhecidos da casa;
  2. Roteador (modelo pequeno) — responde trivialidade na hora OU escolhe o
     agente especialista;
  3. Agente especialista (agents/especialistas.py) — quem faz a tarefa.

Tudo que acontece aqui é guardado pelo registro (memory/registro.py).
"""
import asyncio
import logging

from ..agents import agent as adk_agent
from ..agents import observador
from ..agents import roteador as agent_roteador
from ..config import config
from ..context.engine import context_engine
from ..intents.router import intent_router
from ..memory import registro as reg
from ..memory.db import store
from ..skills.registry import skill_for
from ..telemetry.metrics import Interaction
from ..tts.chunker import Chunker
from ..tts.engine import tts
from ..tts.library import library

log = logging.getLogger("jarvis.dialog")


class DialogManager:
    """Um por conexão. `send` é a função async que manda JSON pro device."""

    def __init__(self, device_id: str, send, obter_audio=None):
        self.device_id = device_id
        self.send = send
        # devolve o PCM da última fala (o pipeline preenche); só pro registro
        self.obter_audio = obter_audio
        self.interaction: Interaction | None = None
        self.registro: reg.Registro | None = None
        self.transcript_atual = ""
        self._seq = 0
        self._falou = False

    def start_interaction(self):
        ctx = context_engine.new_session(self.device_id)
        self.interaction = Interaction(self.device_id, ctx.session_id if ctx else "?")
        self.interaction.mark("wake_word_ms")
        self.registro = reg.Registro(self.device_id, self.interaction.session_id)
        self._seq = 0          # a fila de áudio do device reinicia no seq 0
        self._falou = False

    def _proximo_seq(self) -> int:
        self._falou = True
        s = self._seq
        self._seq += 1
        return s

    async def _fim_da_fala(self):
        """Avisa que a resposta acabou — SEMPRE que algo foi falado.

        O device liga o "estou falando" no `seq 0` e só desliga no `speak_end`.
        Sem isto, uma resposta pronta da biblioteca ("Pronto.", "Bom dia.")
        deixava a janela do PC presa na tela, opaca, até a interação seguinte.
        """
        if self._falou:
            await self.send({"type": "speak_end", "seq": self._seq})
            self._falou = False

    async def _speak_library(self, intent: str) -> str | None:
        pick = library.pick(intent)
        if not pick:
            # sem wav pronto ainda: fala pelo TTS em vez de ficar mudo
            texto = library.texto_qualquer(intent)
            if texto:
                await self._speak_tts(texto)
            return texto
        text, path = pick
        # tudo que é falado numa interação entra na MESMA fila, em ordem
        await self.send({"type": "speak", "text": text,
                         "audio_url": library.url_de(path, f"/audio/library/{intent}"),
                         "seq": self._proximo_seq(), "ultimo": False})
        return text

    async def _speak_tts(self, text: str):
        """Fala um trecho; o device toca em fila, na ordem recebida."""
        path = await tts.get_or_synthesize(text)
        if self.interaction and "tts_first_audio_ms" not in self.interaction.marks:
            self.interaction.mark("tts_first_audio_ms")
        await self.send({"type": "speak", "text": text,
                         "audio_url": f"/audio/tts/{path.name}" if path else None,
                         "seq": self._proximo_seq(), "ultimo": False})

    async def _falar_em_stream(self, ctx, agente: str | None = None) -> str:
        """Gera a resposta do LLM e vai falando enquanto ela é escrita.

        A voz clonada é lenta (RTF ~4): esperar o texto inteiro faria a resposta
        demorar vários segundos. Aqui o primeiro pedaço já vira áudio assim que
        o LLM solta as primeiras palavras.
        """
        chunker = Chunker(
            primeiro=config.settings["tts"].get("stream_primeiras_palavras", 3),
            maximo=config.settings["tts"].get("stream_max_palavras", 14),
        )
        completo = []

        async for novo in adk_agent.ask_stream(self.transcript_atual, ctx, agente):
            if self.interaction and "llm_first_token_ms" not in self.interaction.marks:
                self.interaction.mark("llm_first_token_ms")
            completo.append(novo)
            for pedaco in chunker.feed(novo):
                await self._speak_tts(pedaco)

        for pedaco in chunker.flush():
            await self._speak_tts(pedaco)
        return "".join(completo).strip()

    async def on_final(self, transcript: str):
        it = self.interaction or Interaction(self.device_id, "?")
        it.mark("stt_final_ms")
        ctx = context_engine.get(self.device_id)
        await self.send({"type": "stt_final", "text": transcript})

        match = intent_router.match(transcript)
        it.mark("intent_ms")
        handler, intent_id, response_text = "local", None, None
        erro = None

        if match:
            intent_id = match.intent_id
            skill = skill_for(intent_id)
            if skill:
                await self.send({"type": "state", "state": "EXECUTING"})
                result = await skill.handle(intent_id, match.slots, ctx)
                it.mark("tool_execution_ms")
                if result.response_intent:
                    response_text = await self._speak_library(result.response_intent)
                    if response_text is None and result.response_text:
                        response_text = result.response_text
                        await self._speak_tts(response_text)
                elif result.response_text:
                    response_text = result.response_text
                    await self._speak_tts(response_text)
                if not result.ok:
                    erro = result.error or f"skill {intent_id} falhou"
                await self._fim_da_fala()
                await self.send({"type": "state", "state": "DONE" if result.ok else "ERROR"})
            else:
                match = None  # intent sem skill → agente

        agente_usado = None
        rota = {}
        if not match:
            handler = "agent"
            await self.send({"type": "state", "state": "THINKING"})
            # o LLM demora alguns segundos pro primeiro token; um "um momento"
            # pronto entra na hora e tira a sensação de travado
            await self._speak_library("thinking")

            decisao, t_rota = await agent_roteador.decidir(transcript)
            it.mark("roteador_ms")
            rota = decisao.para_dict()
            rota["duracao_s"] = round(t_rota, 3)

            if decisao.resposta:
                # trivialidade: o próprio roteador já respondeu, sem chamar agente
                handler = "roteador"
                response_text = decisao.resposta
                await self._speak_tts(response_text)
                await self._fim_da_fala()
                await self.send({"type": "state", "state": "DONE"})
            else:
                agente_usado = decisao.agente
                self.transcript_atual = transcript
                answer = await self._falar_em_stream(ctx, agente_usado)
                if answer:
                    response_text = answer
                    await self._fim_da_fala()
                    await self.send({"type": "state", "state": "DONE"})
                else:
                    erro = f"agente {agente_usado} não respondeu"
                    response_text = await self._speak_library("not_understood")
                    await self._fim_da_fala()
                    await self.send({"type": "state", "state": "ERROR"})

        metrics = it.finish()
        await store.log_interaction(self.device_id, it.session_id, transcript,
                                    intent_id, handler, response_text, metrics)
        self._registrar(transcript, agente_usado or handler, rota,
                        response_text, metrics, erro)
        self.interaction = None

    def _registrar(self, transcript, agente, rota, resposta, metrics, erro=None):
        """Guarda áudio + decisão pra aprender depois, FORA do caminho da resposta.

        Gravar o WAV e dar dois commits no SQLite aqui dentro segurava o
        pipeline em BUSY — ou seja, o microfone ficava surdo até terminar.
        O PCM é pego agora (senão a fala seguinte sobrescreve) e o resto vai
        pra uma tarefa em segundo plano.
        """
        r, self.registro = self.registro, None
        if r is None or not reg.ativo():
            return
        r.transcricao = transcript
        r.agente = agente
        r.rota = rota
        r.resposta = resposta or ""
        r.metricas = metrics
        r.erro = erro
        pcm = self.obter_audio() if self.obter_audio else None
        asyncio.create_task(self._gravar_registro(r, pcm))

    async def _gravar_registro(self, r, pcm):
        try:
            if pcm is not None and len(pcm):
                r.audio_path = await asyncio.to_thread(reg.salvar_audio, pcm,
                                                       r.session_id)
            registro_id = await store.salvar_registro(r)
            await self._observar(registro_id, r)
        except Exception:
            log.exception("não consegui registrar a interação")

    async def _observar(self, registro_id, r):
        """Manda o observador olhar — em segundo plano, sem segurar a resposta."""
        if not registro_id or not observador.ativo():
            return
        motivo = await observador.motivo_para_analisar(
            self.device_id, r.transcricao, r.rota, r.erro, registro_id)
        if not motivo:
            return
        asyncio.create_task(observador.analisar(
            registro_id, r.transcricao, r.agente, r.resposta, motivo))

    async def on_timeout(self):
        """Ninguém falou nada aproveitável depois do wake."""
        await self.send({"type": "state", "state": "IDLE"})
        self.interaction = None
        self.registro = None
