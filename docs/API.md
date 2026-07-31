# API e protocolo

## WebSocket `/ws/{device_id}?token=...`

Autenticação: token do device (`config/devices.yml`). Token errado → handshake rejeitado (403).

**Binário (device → servidor):** PCM int16 little-endian, 16 kHz, mono, frames de 80ms
(1280 amostras = 2560 bytes).

**JSON device → servidor:**

| type | campos | uso |
|---|---|---|
| `hello` | `device_type`, `room?`, `network?` | primeiro pacote após conectar |
| `context` | `room?`, `network?`, `place?`, `gps?`, `bluetooth?` | atualização de contexto |
| `mic_open` | — | push-to-talk (watch/celular): ouvir sem wake word |
| `mic_close` | — | cancela a captura |
| `ping` | `ts` | keepalive |

**JSON servidor → device:**

| type | campos | uso |
|---|---|---|
| `hello_ok` | `context`, `ack_sounds[]` | confirma registro; device baixa e cacheia os acks |
| `wake` | — | wake word detectada → acender reator + tocar ack LOCAL |
| `state` | `state` = IDLE/LISTENING/THINKING/EXECUTING/DONE/ERROR | dirige a UI |
| `stt_partial` / `stt_final` | `text` | transcrição |
| `speak` | `text`, `audio_url` | resposta falada (URL relativa ao servidor) |
| `ambient` | `temperature_c` | hora/temperatura do modo repouso (a cada 60s) |
| `pong` | `ts` | resposta do ping |

## REST

| Rota | Descrição |
|---|---|
| `GET /api/status` | ok + devices online |
| `GET /api/metrics/recent?limit=N` | últimas interações com métricas de latência |
| `GET /audio/library/{intent}/{arquivo}` | áudios prontos |
| `GET /audio/tts/{arquivo}` | cache do TTS |
| `GET /` | web buildada |

## Métricas por interação

`wake_word_ms, stt_partial_ms, stt_final_ms, intent_ms, llm_first_token_ms,
tool_execution_ms, tts_first_audio_ms, total_response_ms` — logadas no console e
gravadas em `interactions.metrics_json` (SQLite `server/data/jarvis.db`).
