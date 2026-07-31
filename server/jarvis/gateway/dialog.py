"""Orquestra uma interação: transcrição final → intent → skill/agente → resposta falada."""
import logging

from ..agents import agent as adk_agent
from ..context.engine import context_engine
from ..intents.router import intent_router
from ..memory.db import store
from ..skills.registry import skill_for
from ..telemetry.metrics import Interaction
from ..tts.engine import tts
from ..tts.library import library

log = logging.getLogger("jarvis.dialog")


class DialogManager:
    """Um por conexão. `send` é a função async que manda JSON pro device."""

    def __init__(self, device_id: str, send):
        self.device_id = device_id
        self.send = send
        self.interaction: Interaction | None = None

    def start_interaction(self):
        ctx = context_engine.new_session(self.device_id)
        self.interaction = Interaction(self.device_id, ctx.session_id if ctx else "?")
        self.interaction.mark("wake_word_ms")

    async def _speak_library(self, intent: str) -> str | None:
        pick = library.pick(intent)
        if not pick:
            return None
        text, path = pick
        await self.send({"type": "speak", "text": text,
                         "audio_url": f"/audio/library/{intent}/{path.name}"})
        return text

    async def _speak_tts(self, text: str):
        path = await tts.get_or_synthesize(text)
        if self.interaction:
            self.interaction.mark("tts_first_audio_ms")
        if path:
            await self.send({"type": "speak", "text": text,
                             "audio_url": f"/audio/tts/{path.name}"})
        else:
            await self.send({"type": "speak", "text": text, "audio_url": None})

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
            answer = await adk_agent.ask(transcript, ctx)
            it.mark("llm_first_token_ms")
            if answer:
                response_text = answer
                await self._speak_tts(answer)
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
