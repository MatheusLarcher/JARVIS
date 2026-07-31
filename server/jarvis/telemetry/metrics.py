import json
import logging
import time

log = logging.getLogger("jarvis.telemetry")

STAGES = [
    "wake_word_ms", "audio_transport_ms", "stt_partial_ms", "stt_final_ms",
    "intent_ms", "llm_first_token_ms", "tool_execution_ms",
    "tts_first_audio_ms", "total_response_ms",
]


class Interaction:
    """Cronômetro de uma interação (do wake até a resposta tocando)."""

    def __init__(self, device_id: str, session_id: str):
        self.device_id = device_id
        self.session_id = session_id
        self.t0 = time.perf_counter()
        self.marks: dict[str, float] = {}

    def mark(self, stage: str):
        self.marks[stage] = round((time.perf_counter() - self.t0) * 1000, 1)

    def span(self, stage: str, start_stage: str | None = None):
        base = self.marks.get(start_stage, 0.0) if start_stage else 0.0
        self.marks[stage] = round((time.perf_counter() - self.t0) * 1000 - base, 1)

    def finish(self) -> dict:
        self.marks["total_response_ms"] = round((time.perf_counter() - self.t0) * 1000, 1)
        log.info("interacao %s %s | %s", self.device_id, self.session_id,
                 json.dumps(self.marks, ensure_ascii=False))
        return dict(self.marks)
