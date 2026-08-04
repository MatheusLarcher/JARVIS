# Referência — tudo o que existe no sistema

Mapa completo: cada módulo, cada opção de configuração, cada teste e cada
script. Se você quer entender **como** funciona, comece por
[ARQUITETURA.md](ARQUITETURA.md) e [AGENTES.md](AGENTES.md); aqui é o
inventário de **o que** existe.

O que ainda não existe está em [ROADMAP.md](ROADMAP.md).

---

## 1. Módulos do servidor (`server/jarvis/`)

### Entrada e infraestrutura

| Arquivo | O que faz |
|---|---|
| `app.py` | Monta o FastAPI, sobe tudo no start (banco, casa, modelos, aquecimento dos agentes, limpeza dos registros antigos) e serve a web buildada na raiz. |
| `config.py` | Lê `config/*.yml` e o `.env`. Expõe `config.settings`, `config.devices`, `config.intents`, `config.house`, `config.responses`. Também define `ROOT` e `DATA_DIR`. |
| `activity.py` | Marca quando há uma interação em andamento. O aquecedor de TTS consulta isso pra não disputar a GPU enquanto você fala. |

### Gateway (porta de entrada dos aparelhos)

| Arquivo | O que faz |
|---|---|
| `gateway/ws.py` | WebSocket `/ws/{device_id}?token=`. Valida o token, cria um `AudioPipeline` e um `DialogManager` por conexão, recebe áudio binário e JSON, e manda hora/temperatura a cada 60s. |
| `gateway/dialog.py` | O cérebro da conversa: recebe a transcrição final e percorre as camadas de decisão (regra local → roteador → agente), fala a resposta e dispara o registro. |
| `gateway/rest.py` | Endpoints HTTP: áudios da biblioteca e do cache TTS, `/api/status`, `/api/audio/debug`. |

### Áudio (ouvir)

| Arquivo | O que faz |
|---|---|
| `audio/pipeline.py` | Máquina de estados por conexão (IDLE → SCANNING → COMMAND → BUSY): VAD, pre-roll, transcrição parcial sem travar, fim de fala, e a gravação da fala pro registro. |
| `audio/wakeword.py` | Reconhece "Jarvis" mesmo mal transcrito (distância de edição + trocas v/f, z/s) e separa o comando que veio na mesma frase. |

### Transcrição

| Arquivo | O que faz |
|---|---|
| `stt/base.py` | Interface `SttEngine` / `SttStream` e a `factory()` que escolhe pelo `stt.engine`. |
| `stt/whisper.py` | **O que roda hoje.** faster-whisper `small` com `initial_prompt` + `hotwords`; gera parciais e final. Filtra o eco do próprio prompt. |
| `stt/nemotron.py` | Nemotron 3.5 ASR streaming (NeMo). Rápido, mas erra o nome — fica como alternativa. |
| `stt/hibrido.py` | Nemotron nas parciais + Whisper na final. Carrega os dois em sequência (em paralelo o import quebra). |
| `stt/dummy.py` | Devolve texto fixo. Pra testar o fluxo sem GPU. |

### Decisão

| Arquivo | O que faz |
|---|---|
| `intents/router.py` | Regex normalizada (sem acento) sobre a transcrição → intent + slots. Custo zero. |
| `agents/roteador.py` | O modelo pequeno que escolhe o agente. Trava a resposta direta em papo social e tem o palpite por palavras como rede de segurança. |
| `agents/especialistas.py` | Constrói e cacheia um agente ADK por assunto, com o prompt e as ferramentas de cada um. Também decide se a nuvem está disponível. |
| `agents/agent.py` | O streaming do ADK (`ask_stream`), o filtro de `<think>`, o corte na primeira frase, o aquecimento e o `despertar_gpu()`. |
| `agents/observador.py` | Relê depois, em segundo plano, só o que deu sinal de problema. |

### Ação

| Arquivo | O que faz |
|---|---|
| `skills/base.py` | `Skill` e `SkillResult` (ok, texto ou intent de resposta, erro). |
| `skills/registry.py` | Mapa intent → skill. É aqui que se registra uma skill nova. |
| `skills/lights.py` | Liga/desliga luz, resolvendo o cômodo pelo contexto quando você não diz. |
| `skills/info.py` | Hora e temperatura. |
| `skills/social.py` | Cumprimento, agradecimento e despedida — com saudação pela hora do dia. |
| `home_assistant/client.py` | Fala com o Home Assistant (ou simula, no modo `mock`) e traduz cômodo → `entity_id`. |
| `mcp/loader.py` | Carrega os servidores MCP habilitados em `config/mcp.yml` como ferramentas do agente. |

### Voz (falar)

| Arquivo | O que faz |
|---|---|
| `tts/engine.py` | Sintetiza com cache por hash da frase; perfis `clone` (serviço na 8041) e `edge`, com fallback. |
| `tts/library.py` | Frases prontas por intent, com variação. URL versionada pelo mtime pra trocar a voz invalidar o cache do aparelho. |
| `tts/chunker.py` | Corta a resposta do LLM em pedaços (3 palavras no começo, crescendo até 14) pra começar a falar antes do texto acabar. |
| `tts/warmer.py` | Mantém pronta a frase da hora atual, e só trabalha quando ninguém está falando. |
| `voice_service/service.py` | Serviço separado (env `jarvis-tts`, porta 8041) com o Chatterbox e a voz clonada. |

### Memória e contexto

| Arquivo | O que faz |
|---|---|
| `memory/db.py` | SQLite: `interactions`, `registros`, `memory_kv`, `device_state`. Histórico curto, registro e limpeza. |
| `memory/registro.py` | Grava o WAV da fala e monta o registro da interação. |
| `context/engine.py` | Quem é o aparelho, em que cômodo, em que rede, que sessão. |
| `telemetry/metrics.py` | Marca o tempo de cada etapa e fecha a conta no fim da interação. |

---

## 2. Configuração (`config/`)

| Arquivo | Pra quê |
|---|---|
| `settings.yml` | Todos os parâmetros do sistema (detalhado abaixo). |
| `devices.yml` | Aparelhos e tokens. **Não vai pro git** — modelo em `devices.example.yml`. |
| `.env` | Chaves de API. **Não vai pro git** — modelo em `.env.example`. |
| `house.yml` | Cômodos, dispositivos, `entity_id` e os lugares (casa/empresa) por rede Wi-Fi. |
| `intents/core.yml` | Os comandos resolvidos por regra, com os padrões e os slots. |
| `responses.yml` | As frases prontas de cada intent (viram wav pelo `build_library.py`). |
| `mcp.yml` | Servidores MCP disponíveis pro agente. |

### `settings.yml` — todas as chaves

| Seção | Chave | O que muda |
|---|---|---|
| `server` | `host`, `port` | Onde o servidor escuta (padrão `0.0.0.0:8040`). |
| `audio` | `sample_rate`, `frame_ms` | Formato do áudio que os aparelhos mandam (16 kHz, 80 ms). |
| `wake_word` | `engine` | `stt` (o nome é achado na transcrição) ou `openwakeword`. |
| | `keyword`, `fuzzy_max_edits` | O nome e quanto erro de transcrição se aceita. |
| | `threshold`, `openwakeword_model` | Sensibilidade do atalho instantâneo. |
| | `refractory_s` | Ignora novos wakes por N segundos depois de um. |
| | `preroll_s` | Quanto de áudio ANTES da fala entra no reconhecimento. |
| | `followup_s` | Quanto espera pelo comando depois de você só chamar. |
| `vad` | `threshold`, `min_speech_ms` | Quanto de fala contínua conta como fala (evita transcrever ruído). |
| | `end_silence_s` | Silêncio que encerra a frase. |
| | `max_utterance_s` | Teto de tempo ouvindo. |
| `stt` | `engine` | `whisper` \| `hibrido` \| `nemotron` \| `dummy`. |
| | `whisper_model`, `whisper_compute_type`, `whisper_beam_size` | Tamanho e precisão do modelo. |
| | `whisper_parciais`, `whisper_intervalo_parcial` | Se o próprio Whisper gera as parciais e de quanto em quanto. |
| | `initial_prompt`, `hotwords` | Como o nome "Jarvis" é ensinado ao modelo. |
| | `language`, `device` | Idioma e GPU/CPU. |
| `tts` | `voice_profiles` | Perfis de voz (`clone` via serviço, `edge` como reserva). |
| | `default_profile`, `cache_dir`, `library_dir` | Voz padrão e onde ficam cache e frases prontas. |
| | `cache_warmer` | Manter a frase da hora sempre pronta. |
| | `stream_primeiras_palavras`, `stream_max_palavras` | Tamanho dos pedaços da fala em streaming. |
| `llm` | `model`, `api_base`, `api_key_env` | O modelo local (ou de nuvem) e como chegar nele. |
| | `no_think` | Desliga o "pensar antes de responder" dos Qwen3.x. |
| | `historico_trocas`, `historico_max_chars` | Quanto de conversa anterior entra no prompt. |
| | `max_tokens`, `max_frases`, `max_palavras` | Corte da resposta (garantido no servidor). |
| `agentes` | `roteador.modelo` | O modelo que decide a rota. |
| | `lista[]` | Cada agente: `nome`, `descricao`, `exemplos`, `requer_nuvem`. |
| `nuvem` | `ativo`, `modelo`, `api_key_env` | Provedor externo. Com `false`, roda 100% local. |
| | `reasoning_effort` | Quanto o modelo "pensa" antes de responder (`low` = mais rápido). |
| `registro` | `ativo`, `guardar_dias` | Se guarda áudio + decisão, e por quantos dias. |
| `observador` | `ativo`, `quando` | Quando o modelo esperto relê (`roteador_incerto`, `pedido_repetido`, `tarefa_falhou`). |
| `home_assistant` | `mode`, `url`, `token_env`, `temperature_entity` | Casa real ou simulada. |
| `telemetry` | `enabled` | Grava o tempo de cada etapa. |

---

## 3. Aplicativos (`apps/`)

| Pasta | O que é |
|---|---|
| `web/` | React + Vite. O reator, o modal de configuração (microfones, saída), o player em fila. Serve o navegador e é a interface do app de bandeja. |
| `desktop/` | Electron de bandeja. Ícone oculto, janela sem moldura que aparece no wake, arrastável, translúcida quando sem foco, com posição lembrada. |
| `android/app/` | Celular e tablet (Kotlin/Compose). Modo quadro na parede, tap-to-talk. |
| `android/wear/` | Wear OS. Microfone só sob demanda. |
| `android/shared/` | Código comum: `JarvisClient` (WS), `AudioEngine` (captura e ack local), `Reactor`, `Prefs`. |

---

## 4. Scripts

| Script | Pra quê |
|---|---|
| `gerar_exe.bat` | Gera o instalador do Windows num comando (na raiz do projeto). |
| `server/start_jarvis.bat` | Sobe servidor + voz, cada um com watchdog que reinicia sozinho. |
| `server/start_voice.bat` | Só o serviço de voz (8041). |
| `server/start_jarvis_hidden.vbs` | O mesmo, sem janela — é o que entra no auto-start do Windows. |
| `server/scripts/build_library.py` | Gera os wav das frases prontas (`--verify` confere pela transcrição). |
| `server/scripts/check_library.py` | Confere se a biblioteca está completa e íntegra. |
| `server/scripts/prepare_voice_ref.py` | Prepara o áudio de referência da voz clonada. |
| `server/scripts/trocar_tokens.py` | Roda tokens novos e atualiza a cópia guardada pelo app da bandeja. |
| `server/watchdog.ps1` | Confere Ollama, servidor, voz e app da bandeja; sobe o que estiver fora. **Nada o agenda** — é ferramenta manual, o app já vigia a cada 30 s. |
| `docs/diagrama/gerar.py` | Regera o diagrama do sistema (`docs/diagrama.png`). |

---

## 5. Testes (`tests/`, 49 arquivos)

`test_*` verificam comportamento, `bench_*` medem, `diag_*` investigam.

### Não precisam de nada (só Python)

| Teste | Cobre |
|---|---|
| `test_wakeword.py` | Reconhecer "Jarvis" mal transcrito, e não acordar à toa (27 casos). |
| `test_intents.py` | Regras locais, incluindo cumprimentos, e que elas não roubem pedidos reais. |
| `test_roteador.py` | A decisão nunca trava nem inventa agente. |
| `test_chunker.py` | Cortar a fala em pedaços sem quebrar palavra. |
| `test_corte_resposta.py` | O corte na primeira frase. |
| `test_filtro_pensamento.py` | Tirar `<think>` mesmo partido entre pedaços. |
| `test_eco_prompt.py` | O Whisper repetindo o próprio prompt não vira pedido. |
| `test_fim_da_fala.py` | Toda resposta falada termina com `speak_end` (7 caminhos). |

### Precisam do servidor no ar

| Teste | Cobre |
|---|---|
| `test_audio_e2e.py` | Fala sintetizada pelo WebSocket: wake → STT → intent → resposta. |
| `test_agentes_e2e.py` | Os 4 caminhos de decisão + o registro gravado no disco. |
| `test_ws_flow.py` | O protocolo do WebSocket. |
| `test_tts_stream.py` | A resposta chegando em pedaços, na ordem. |
| `test_ack_atualizado.py` | Trocar a voz invalida o cache do "Sim?". |
| `test_mic_real.py` | O fluxo pelo microfone de verdade. |

### App do PC (precisa do `--remote-debugging-port=9333`)

`test_janela_destrava.py`, `test_janela_arrastar.py`, `test_janela_posicao.py`,
`test_janela_transparencia.py`, `test_janela_desktop.py`,
`test_iniciar_com_windows.py` (clica na engrenagem e confere a chave `Run` do
Windows por fora do app — marcar, desmarcar e marcar de novo).

> Rode um de cada vez e **feche o modal** no fim: modal aberto deixa a janela
> "pinada" e o teste seguinte falha em "some depois que termina".

### Medições

| Bench | Mede |
|---|---|
| `bench_stt.py` | Modelos de transcrição: acerto do nome, erro no comando, s/frase. |
| `bench_roteador.py` | As duas camadas de decisão: acerto e custo. |
| `bench_llm.py`, `bench_pipeline.py` | LLM e pipeline completo. |
| `bench_nuvem_onde_vai_o_tempo.py` | `low` x `high` e o custo do ADK. |
| `bench_nuvem_primeira_chamada.py` | Quanto custa a primeira chamada fria. |
| `bench_nuvem_no_servidor.py` | A primeira pergunta difícil no servidor real. |
| `bench_whisper_*.py` | Tamanhos, latência e efeito do prompt. |
| `bench_instrucao.py` | Como o prompt do sistema afeta o tempo. |

### Diagnóstico

`diag_microfones.py` (qual mic escuta a sala), `diag_app_mic.py`,
`diag_gpu_ociosa.py` (a GPU dormindo custa segundos), `diag_whisper_gpu.py`,
`diag_llm_stream.py`, `diag_llm_tools.py`, `diag_ollama_nothink.py`,
`diag_ollama_keepalive.py`, `diag_think_vazando.py`, `diag_adk_overhead.py`,
`diag_parakeet.py`, `diag_parakeet_boost.py`.

E `ver_registros.py`, que mostra o que o JARVIS guardou de cada interação.

---

## 6. Documentação

| Doc | Assunto |
|---|---|
| [ARQUITETURA.md](ARQUITETURA.md) | Visão geral, camadas de decisão, decisões de projeto. |
| [AGENTES.md](AGENTES.md) | Roteador, agentes, registro e observador. |
| [STT.md](STT.md) | Transcrição: comparação de modelos e por que o Whisper. |
| [VOZ.md](VOZ.md) | Voz clonada, biblioteca e cache. |
| [DESEMPENHO.md](DESEMPENHO.md) | Todos os tempos medidos, etapa por etapa. |
| [API.md](API.md) | WebSocket e REST. |
| [INSTALACAO.md](INSTALACAO.md) | Como subir tudo, gerar APK e o instalador do Windows. |
| [GUIAS.md](GUIAS.md) | Como adicionar skill, aparelho, trocar modelo. |
| [SEGURANCA.md](SEGURANCA.md) | O que não pode ir pro git e o que fazer se vazar. |
| [ROADMAP.md](ROADMAP.md) | O que ainda não existe. |
| [MEMORIA.md](MEMORIA.md) | Diário do projeto: o que foi feito, o que quebrou e por quê. |
