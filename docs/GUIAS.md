# Guias de extensão

## Adicionar uma Skill (comando local, sem LLM)

1. Declare o intent em `config/intents/*.yml` (regex sem acento; slots por grupo nomeado).
2. Crie a classe em `server/jarvis/skills/` herdando `Skill` (`base.py`), liste os intents
   em `intents` e implemente `handle()` retornando `SkillResult`
   (`response_intent` = áudio pronto da biblioteca, ou `response_text` = TTS dinâmico).
3. Registre a instância em `server/jarvis/skills/registry.py`.
4. Se criar respostas novas, adicione as frases em `config/responses.yml` e rode
   `python server/scripts/build_library.py`.
5. Teste em `tests/test_intents.py`.

## Adicionar um dispositivo

1. Nova entrada em `config/devices.yml` (id, type, token novo, default_room).
2. Instale o app correspondente e configure host/id/token na primeira tela.
3. Nada mais: o gateway aceita qualquer device do yml.

## Adicionar cômodo/lâmpada

`config/house.yml` → `house.<comodo>.luz_principal.entity_id`. Inclua o cômodo também no
regex `room` de `config/intents/core.yml` se quiser citá-lo por voz.

## Trocar o STT

Implemente `SttEngine`/`SttStream` em `server/jarvis/stt/`, registre em `factory()`
(`base.py`) e aponte `stt.engine` no `settings.yml`. O atual (`nemotron.py`) faz
transcrição incremental; dá pra evoluir pro cache-aware streaming nativo do NeMo
sem tocar no resto.

## Trocar o TTS / voz

Implemente `TtsEngine` em `server/jarvis/tts/engine.py`, registre em `_ENGINES` e crie um
perfil em `settings.yml → tts.voice_profiles`. Depois regenere a biblioteca
(`build_library.py` — apague `server/data/library` antes se quiser trocar a voz dos acks).
O cache é por hash(frase+perfil), então perfis convivem.

## Trocar o LLM

`settings.yml → llm.model` usa string do LiteLLM: `deepseek/deepseek-chat`,
`gemini/gemini-2.5-flash`, `anthropic/claude-sonnet-5`, `openai/gpt-...` etc.
Chave via variável em `config/.env` (o nome fica em `llm.api_key_env`).

## MCP

`config/mcp.yml` → `servers.<nome>` com `enabled: true`, `command`, `args`. Cada servidor
vira um `MCPToolset` do agente ADK (carregado em `server/jarvis/mcp/loader.py`).
Áudio NUNCA passa por MCP — só ferramentas.

## Home Assistant real

1. `config/.env`: `HA_TOKEN=<long-lived token>`.
2. `settings.yml → home_assistant`: `mode: real`, `url: http://IP-DO-HA:8123`,
   `temperature_entity: sensor.<seu_sensor>`.
3. Ajuste os `entity_id` em `config/house.yml`.
4. Reinicie o servidor e teste "liga a luz".

## Wake word

Padrão: `wake_word.engine: stt` — a palavra-chave é reconhecida na própria transcrição.
Fale **"Jarvis"** e, se quiser, emende o comando na mesma frase:

```
"Jarvis"                      → toca "Sim?" e fica ouvindo o comando
"Jarvis, liga a luz da sala"  → executa direto, sem o "Sim?" no meio
"Liga a luz da sala, Jarvis"  → também funciona (nome no fim)
```

Peças: `audio/wakeword.py` (match por distância de edição, tolera "jarves"/"javis") e
`audio/pipeline.py` (pre-roll + fases IDLE → SCANNING → COMMAND).

Ajustes em `config/settings.yml`:

| Chave | Pra quê |
|---|---|
| `wake_word.keyword` | trocar o nome do assistente |
| `wake_word.fuzzy_max_edits` | mais alto = reconhece mais fácil, mas dispara à toa |
| `wake_word.preroll_s` | quanto de áudio antes da fala entra no reconhecimento |
| `wake_word.followup_s` | quanto espera o comando depois do "Sim?" |
| `vad.min_speech_ms` | fala contínua mínima pra acionar o STT (filtra ruído) |

Teste sem microfone: `python tests/test_wakeword.py` (frases → comando extraído).

O openWakeWord (`hey_jarvis`) continua ligado em paralelo: dizer "Hey Jarvis" dispara pelo
caminho instantâneo. Pra usar só ele, `wake_word.engine: openwakeword`.
