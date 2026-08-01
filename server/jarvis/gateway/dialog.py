"""Orquestra uma interação: transcrição final → intent → skill/agente → resposta falada."""
import asyncio
import logging

from ..agents import agent as adk_agent
from ..config import config
from ..context.engine import context_engine
from ..intents.router import intent_router
from ..memory.db import store
from ..skills.registry import skill_for
from ..telemetry.metrics import Interaction
from ..tts.chunker import Chunker
from ..tts.engine import tts
from ..tts.library import library

log = logging.getLogger("jarvis.dialog")


class DialogManager:
    """Um por conexão. `send` é a função async que manda JSON pro device."""

    def __init__(self, device_id: str, send):
        self.device_id = device_id
        self.send = send
        self.interaction: Interaction | None = None
        self.transcript_atual = ""
        self._seq = 0

    def start_interaction(self):
        ctx = context_engine.new_session(self.device_id)
        self.interaction = Interaction(self.device_id, ctx.session_id if ctx else "?")
        self.interaction.mark("wake_word_ms")
        self._seq = 0          # a fila de áudio do device reinicia no seq 0

    def _proximo_seq(self) -> int:
        s = self._seq
        self._seq += 1
        return s

    async def _speak_library(self, intent: str) -> str | None:
        pick = library.pick(intent)
        if not pick:
            return None
        text, path = pick
        # tudo que é falado numa interação entra na MESMA fila, em ordem
        await self.send({"type": "speak", "text": text,
                         "audio_url": f"/audio/library/{intent}/{path.name}",
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

    async def _falar_em_stream(self, ctx) -> str:
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
        falou = False

        async for novo in adk_agent.ask_stream(self.transcript_atual, ctx):
            if self.interaction and "llm_first_token_ms" not in self.interaction.marks:
                self.interaction.mark("llm_first_token_ms")
            completo.append(novo)
            for pedaco in chunker.feed(novo):
                await self._speak_tts(pedaco)
                falou = True

        for pedaco in chunker.flush():
            await self._speak_tts(pedaco)
            falou = True

        if falou:
            await self.send({"type": "speak_end", "seq": self._seq})
        return "".join(completo).strip()

    async def on_final(self, transcript: str):
        it = self.interaction or Interaction(self.device_id, "?")
        it.mark("stt_final_ms")
        ctx = context_engine.get(self.device_id)
        await self.send({"type": "stt_final", "text": transcript})

        match = intent_router.match(transcript)
        it.mark("intent_ms")
        handler, intent_id, response_text = "local", None, None

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
                await self.send({"type": "state", "state": "DONE" if result.ok else "ERROR"})
            else:
                match = None  # intent sem skill → agente

        if not match:
            handler = "agent"
            await self.send({"type": "state", "state": "THINKING"})
            # o LLM demora alguns segundos pro primeiro token; um "um momento"
            # pronto entra na hora e tira a sensação de travado
            await self._speak_library("thinking")
            self.transcript_atual = transcript
            answer = await self._falar_em_stream(ctx)
            if answer:
                response_text = answer
                await self.send({"type": "state", "state": "DONE"})
            else:
                response_text = await self._speak_library("not_understood")
                await self.send({"type": "state", "state": "ERROR"})

        metrics = it.finish()
        await store.log_interaction(self.device_id, it.session_id, transcript,
                                    intent_id, handler, response_text, metrics)
        self.interaction = None

    async def on_timeout(self):
        """Ninguém falou nada aproveitável depois do wake."""
        await self.send({"type": "state", "state": "IDLE"})
        self.interaction = None
