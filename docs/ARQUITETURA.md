# JARVIS — Arquitetura

## Visão geral

O notebook Windows é o **servidor central** (roda 24h). Todos os dispositivos (tablet, celular,
watch, PC, carro) são **clientes finos**: capturam áudio, mostram o reator e tocam respostas.
Toda a inteligência (wake word, STT, intents, contexto, agente, TTS, casa) roda no servidor.

```text
Tablet / Celular / Watch / PC / Carro
        │  WebSocket (JSON + frames PCM binários) pela LAN
        ▼
Device Gateway (FastAPI + WebSocket)  ──────  auth por token de dispositivo
        ▼
Audio Pipeline (por sessão de dispositivo)
  ├─ openWakeWord "hey jarvis"  → evento wake → device acende reator + toca ack LOCAL
  ├─ Silero VAD                 → início/fim de fala, corta silêncio
  └─ Nemotron 3.5 ASR streaming → parciais + transcrição final (PT-BR)
        ▼
Context Engine  (device_id, cômodo, rede, local, horário, sessão)
        ▼
Intent Router local (regras PT-BR + slots)
  ├─ intent conhecido → Skill direto (ex.: Home Assistant liga luz)  [SEM LLM]
  └─ desconhecido     → Agente Google ADK (LiteLLM) → ferramentas/MCP
        ▼
Response Library (áudios prontos por intent, variação aleatória)
  └─ frase inédita → TTS (com cache por hash)
        ▼
Resposta volta pro MESMO dispositivo que iniciou (roteável no futuro)
```

## Decisões-chave

| Decisão | Escolha | Motivo |
|---|---|---|
| Wake word | **reconhecida na própria transcrição** (`wake_word.engine: stt`) | A palavra é só "Jarvis" e o comando pode vir na MESMA frase ("Jarvis, liga a luz"). O VAD acusa fala → o STT transcreve com pre-roll → a parcial contendo "Jarvis" acende o reator na hora e o resto da frase vira o comando. Comparação por distância de edição, porque o STT escreve "jarves"/"javis". openWakeWord (`hey_jarvis`) segue ativo em paralelo como atalho instantâneo. |
| Ack instantâneo | Wavs de confirmação **baixados e cacheados no device** no registro | `wake` acende o reator; `ack` toca o "Sim?" local (zero rede/LLM/TTS). São eventos separados de propósito: quem emenda "Jarvis, liga a luz" numa frase só **não** ouve o "Sim?" atravessado — o Jarvis já responde o comando. |
| Voz | **clonada por referência** (Chatterbox multilíngue na GPU, serviço à parte na 8041) | Ver [VOZ.md](VOZ.md). Geração é lenta (RTF ~4), então biblioteca pré-gerada + cache + aquecedor cobrem o uso normal. |
| Áudio | PCM 16 kHz mono 16-bit, frames binários de 80ms via WebSocket | Simples, latência baixa na LAN; WebRTC descartado no MVP (complexidade sem ganho em rede local). |
| STT | `nvidia/nemotron-3.5-asr-streaming-0.6b` (NeMo, cache-aware, GPU) | Streaming real (chunks 80–1120ms), 40 idiomas incl. PT. Abstração `SttEngine`; fallbacks: Parakeet TDT (transformers) e faster-whisper. |
| TTS | Interface `TtsEngine` + cache por hash(frase+voz). MVP: edge-tts `pt-BR-AntonioNeural` (perfil `jarvis_br`) | Voz definitiva vem depois; cache e biblioteca prontos independem do motor. |
| LLM | Google ADK + `LiteLlm` (provedor trocável via config) | Nunca acoplar a um provedor. Default: DeepSeek. |
| Casa | Home Assistant via REST/WS local + camada `house/<cômodo>/<dispositivo>` | Controle 100% local. |
| Banco | SQLite (`server/data/jarvis.db`) | Projeto local, sem infra extra. Memória curta (sessão) separada da persistente. |
| Segurança | Token por dispositivo (`config/devices.yml`), obrigatório no WS/REST | Externo futuramente via Cloudflare Tunnel (`jarvis.larchertech.com`); LAN tem prioridade. |

## Portas

| Serviço | Porta |
|---|---|
| Servidor JARVIS (API + WS + web buildada) | **8040** |
| Vite dev (só desenvolvimento) | 8042 |

## Protocolo WebSocket (`/ws/{device_id}?token=...`)

Mensagens JSON (texto) + frames de áudio (binário PCM).

Device → servidor: `hello` (device_type, contexto), `context` (rede/local/cômodo), `audio` (binário),
`mic_state`, `ping`.
Servidor → device: `wake` (acende reator + ack local), `state` (LISTENING/THINKING/EXECUTING/DONE/ERROR),
`stt_partial`, `stt_final`, `speak` (url do áudio + texto), `ambient` (hora/temperatura), `pong`.

## Estados da interface

`IDLE → LISTENING → THINKING → EXECUTING → DONE/ERROR → IDLE`

## Estrutura

```text
server/           backend Python (FastAPI)
apps/
  desktop/        PC (Electron de bandeja: tray oculto + janela do reator no wake)
  jarvis/
    gateway/      WS + REST + auth
    audio/        pipeline, VAD, wake word
    stt/          engines (nemotron, fallbacks)
    tts/          engines + cache + response library
    context/      Context Engine
    intents/      router + definições YAML
    agents/       ADK + LiteLLM
    skills/       skills locais (luz, hora, temperatura…)
    home_assistant/
    memory/       SQLite, sessões, histórico
    telemetry/    métricas de latência por etapa
  data/           db, cache TTS, biblioteca de áudio
  android/        tablet + celular (Kotlin, módulos compartilhados)
  wear/           Wear OS
  web/            React/Vite (navegador + renderer do desktop)
config/           settings.yml, devices.yml, intents/, house.yml
docs/
tests/
```

## Desktop (PC de bandeja)

O app Electron (`apps/desktop`) não tem UI própria: carrega a web servida pelo servidor com
`?desktop=1&device=pc-matheus&token=...`. O main process só cuida de: ícone na bandeja,
mic em background (`backgroundThrottling: false`), mostrar a janela no `wake` (IPC via
preload, `showInactive` pra não roubar foco) e escondê-la 3s depois do estado `IDLE`.
Melhoria visual na web = melhora no desktop sem reinstalar.

## Métricas (telemetria local)

`wake_word_ms, audio_transport_ms, stt_partial_ms, stt_final_ms, intent_ms,
llm_first_token_ms, tool_execution_ms, tts_first_audio_ms, total_response_ms`
— logadas por interação e gravadas no SQLite.
