# JARVIS — Arquitetura

![Como o JARVIS funciona hoje](diagrama.png)

> O desenho acima é gerado: a fonte é [`diagrama/diagrama.html`](diagrama/diagrama.html).
> Mexeu nele? Rode `python docs/diagrama/gerar.py` pra atualizar o PNG.

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
Intent Router local (regras PT-BR + slots)          [SEM LLM, ~0ms]
  ├─ intent conhecido → Skill direto (luz, hora, temperatura, cumprimento)
  └─ desconhecido     ▼
Roteador (modelo pequeno local)                     [~0,35s]
  ├─ papo social      → responde ele mesmo
  └─ qualquer outra coisa → escolhe UM agente
        ▼
Agente especialista (Google ADK + LiteLLM) → ferramentas/MCP
  casa | sistema | conversa | avancado (nuvem)
        ▼
Response Library (áudios prontos por intent, variação aleatória)
  └─ frase inédita → TTS (com cache por hash)
        ▼
Resposta volta pro MESMO dispositivo que iniciou (roteável no futuro)
        │
        └─▶ Registro (áudio + decisão) ─▶ Observador, só quando deu sinal de
                                          problema (fora do caminho da resposta)
```

## Camadas de decisão

A ordem é sempre da mais barata pra mais cara. Medido nesta máquina:

| Camada | Custo | O que resolve |
|---|---|---|
| Intent Router (regex) | ~0 ms | luz, hora, temperatura, cumprimento, agradecimento |
| Roteador (`qwen3.5:0.8b` local) | 0,31–0,53 s | escolhe o agente; responde papo social |
| Agente local (ADK) | +0,3 s pro 1º token | casa, sistema, conversa |
| Agente da nuvem (GPT-5.6 Luna, `reasoning_effort: low`) | ~1 s pro 1º token | `avancado`: pedidos difíceis |

Em 14 frases de teste, 6 foram resolvidas sem LLM nenhum e o destino ficou
certo em 14/14 (`tests/bench_roteador.py`).

### Por que o roteador não responde qualquer coisa

Um modelo de 0.8b solto inventa fato com naturalidade: perguntado "aumenta o
volume", devolveu uma explicação falsa em vez de mandar pro agente; e num teste
chegou a falar em voz alta o próprio molde do prompt (`<uma frase curta>`).
Por isso a resposta direta dele é aceita **só** em papo social, validada no
servidor (`roteador.pode_responder_direto`) e não na confiança do modelo.
Cumprimento, aliás, nem chega até ele: vira intent local com áudio pronto.

Quando a decisão sai inaproveitável, o servidor escolhe o agente por palavras em
comum com a descrição/exemplos dele (`palpite_por_palavras`) — instantâneo, sem
LLM. **Nunca** trava.

## Decisões-chave

| Decisão | Escolha | Motivo |
|---|---|---|
| Wake word | **reconhecida na própria transcrição** (`wake_word.engine: stt`) | A palavra é só "Jarvis" e o comando pode vir na MESMA frase ("Jarvis, liga a luz"). O VAD acusa fala → o STT transcreve com pre-roll → a parcial contendo "Jarvis" acende o reator na hora e o resto da frase vira o comando. Comparação por distância de edição, porque o STT escreve "jarves"/"javis". openWakeWord (`hey_jarvis`) segue ativo em paralelo como atalho instantâneo. |
| Ack instantâneo | Wavs de confirmação **baixados e cacheados no device** no registro | `wake` acende o reator; `ack` toca o "Sim?" local (zero rede/LLM/TTS). São eventos separados de propósito: quem emenda "Jarvis, liga a luz" numa frase só **não** ouve o "Sim?" atravessado — o Jarvis já responde o comando. |
| Voz | **clonada por referência** (Chatterbox multilíngue na GPU, serviço à parte na 8041) | Ver [VOZ.md](VOZ.md). Geração é lenta (RTF ~4), então biblioteca pré-gerada + cache + aquecedor cobrem o uso normal. |
| Áudio | PCM 16 kHz mono 16-bit, frames binários de 80ms via WebSocket | Simples, latência baixa na LAN; WebRTC descartado no MVP (complexidade sem ganho em rede local). |
| STT | `nvidia/nemotron-3.5-asr-streaming-0.6b` (NeMo, cache-aware, GPU) | Streaming real (chunks 80–1120ms), 40 idiomas incl. PT. Abstração `SttEngine`; fallbacks: Parakeet TDT (transformers) e faster-whisper. |
| TTS | Interface `TtsEngine` + cache por hash(frase+voz). MVP: edge-tts `pt-BR-AntonioNeural` (perfil `jarvis_br`) | Voz definitiva vem depois; cache e biblioteca prontos independem do motor. |
| LLM | Google ADK + `LiteLlm` (provedor trocável via config) | Nunca acoplar a um provedor. Local: `ollama_chat/qwen3.5:0.8b`. Nuvem opcional: `openai/gpt-5.6-luna`. |
| Agentes | **um roteador pequeno + especialistas** (`agentes.lista` no settings.yml) | Cada agente tem só o prompt e as ferramentas do assunto dele — prompt curto é resposta rápida, e dá pra trocar o modelo de um sem mexer nos outros. Adicionar agente = uma entrada no YAML + as ferramentas em `especialistas.FERRAMENTAS`. |
| Nuvem | opcional (`nuvem.ativo`) | Com `false` o sistema roda 100% local e o agente `avancado` some da lista sozinho — nada sai da máquina. |
| Registro | áudio WAV + decisão de cada interação (`registro.guardar_dias`) | É a base pra melhorar depois: dá pra ouvir onde ele errou **com a sua voz**, e vira material de treino. Limpeza automática no start. |
| Observador | roda **depois** da resposta, só em `roteador_incerto`, `pedido_repetido` ou `tarefa_falhou` | Analisar tudo custaria API à toa e não acrescenta: o que interessa é onde deu errado. Nunca entra no caminho da resposta. |
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
    agents/       roteador, especialistas, observador (ADK + LiteLLM)
    skills/       skills locais (luz, hora, temperatura, cumprimento…)
    home_assistant/
    memory/       SQLite, sessões, histórico, registro (áudio + decisão)
    telemetry/    métricas de latência por etapa
  data/           db, cache TTS, biblioteca de áudio, gravacoes/ (registro)
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
