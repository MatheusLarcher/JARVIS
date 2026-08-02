# JARVIS — Memória do projeto (ler antes de mexer)

> Atualizar ao fim de cada etapa: o que foi feito, decisões, arquivos, problemas, próximos passos.

## Estado atual (2026-07-31)

MVP COMPLETO e validado ponta a ponta por teste automatizado (`tests/test_audio_e2e.py`):
wake "Hey Jarvis" → ack local → "liga a luz da sala" → Nemotron transcreve → Intent Router
→ HA (mock) liga → resposta pronta da biblioteca → DONE → repouso. Sem LLM no caminho.

- **Ambiente:** conda env `jarvis` (Py 3.11), torch 2.11+cu128 (RTX 5050 ok), NeMo do git main
  (o do pip 2.7.3 NÃO carrega o modelo — falta `rnnt_bpe_models_prompt`).
- **Servidor:** porta 8040, auto-start via tarefa "JARVIS Server" (ONLOGON,
  `server/start_jarvis_hidden.vbs` → `start_jarvis.bat` com loop watchdog, log em
  `server/data/jarvis.log`).
- **Web:** buildada em `apps/web/dist`, servida na raiz do 8040. Validada no browser.
- **Android:** `apps/android` (`:app` tablet+celular, `:wear` relógio; código comum em
  `apps/android/shared/java`). Release assinado em `releases/Jarvis.apk` e
  `releases/Jarvis-Watch.apk` (keystore `jarvis-release.keystore`, senha `jarvis2026`).
  App validado no emulador (setup → conexão → ambient → tap-to-talk → estados → reconexão).
- **LLM:** DeepSeek via ADK+LiteLlm funcionando (chave em `config/.env`), com tool de luz.
- **Desktop (bandeja):** `apps/desktop` (Electron). Tray oculto + mic em background; a janela
  (card 460x520 frameless/transparente, mesma UI web com `?desktop=1&device=pc-matheus`)
  aparece no wake (`showInactive`, sem roubar foco) e some 3s após IDLE; ESC/clique na bandeja
  também controla. Instalador NSIS em `releases/JARVIS-Desktop-Setup.exe`; instalado em
  `%LOCALAPPDATA%\Programs\jarvis-desktop\JARVIS.exe`, login item automático. Config em
  `%APPDATA%\jarvis-desktop\config.json` (token cai pro devices.yml do repo — dev por
  __dirname, instalado por ~/Documents/GitHub/JARVIS). Validado: EXE instalado conecta
  como pc-matheus; wake acústico REAL não foi testável aqui (saída padrão = Astro A50,
  o som de teste não passou pelo mic) — testar falando de verdade.
- **Config de áudio (2026-07-31):** modal na UI web (engrenagem discreta) com multi-mic
  (checkboxes; várias fontes somadas no mesmo AudioWorklet), saída via setSinkId e
  "Fechar o JARVIS" (IPC quit, só no desktop). Janela do PC = rgba(0,5,8,0.84) translúcida.
  `jarvis-pin` (IPC) segura a janela aberta enquanto o modal estiver na tela. Labels dos
  devices só aparecem onde a permissão de mic foi concedida (no Electron sempre; no
  browser depende). Dev do Electron usa userData em %TEMP%\jarvis-desktop-dev pra não
  brigar com a instância instalada (cache lock = exit -1 imediato).

## Voz clonada (2026-07-31)

Voz do JARVIS = clonagem por referência (Chatterbox multilíngue, GPU). Detalhes em
[VOZ.md](VOZ.md). Serviço na 8041, env `jarvis-tts` separado. Biblioteca inteira regerada
com `--verify` (14/14 com WER 0.00). Similaridade de locutor: clonada 0.58–0.76 vs voz
antiga (edge-tts) 0.45.

Aprendizados:
- `VoiceEncoder()` puro = pesos ALEATÓRIOS → similaridade falsa de 1.000 pra tudo. Usar
  `model.ve` (encoder treinado de dentro do Chatterbox).
- Chatterbox pina torch 2.6; instalar torch cu128 POR CIMA (aviso do pip é esperado).
  Instalação interrompida corrompe o sympy — limpar `~*` do site-packages e reinstalar.
- torchaudio novo exige torchcodec pra salvar → usar `soundfile`.
- Frase muito curta ("Sim?") sai ininteligível às vezes → `build_library.py --verify`
  gera N tomadas e escolhe pela transcrição do próprio STT.
- A mesma frase em dois intents ("Pronto.") compartilha o hash do cache: sem reuso, a
  segunda geração sobrescrevia a tomada boa da primeira.
- RTF ~4 (lento) → biblioteca pré-gerada + cache + `tts/warmer.py` (mantém a frase da hora
  atual sempre pronta, e só roda quando ninguém está falando — ver `jarvis/activity.py`).

## Wake word "Jarvis" + comando na mesma frase (2026-07-31)

Reescrita do `audio/pipeline.py`: a palavra-chave agora é reconhecida na TRANSCRIÇÃO
(`wake_word.engine: stt`), não por modelo de wake word. Fases IDLE → SCANNING → COMMAND,
com pre-roll de 1s pra não perder o começo da frase. Eventos `wake` (acende) e `ack`
(toca "Sim?") são SEPARADOS — quem emenda o comando não ouve o "Sim?" por cima.
Match por distância de edição (`audio/wakeword.py`) porque o STT escreve "jarves"/"javis".
Latência medida: reator acende ~1,1s depois de começar a falar.

Bugs encontrados e corrigidos nessa rodada (todos reais, pegos no E2E):
- **STT não é thread-safe**: duas conexões transcrevendo juntas (o app da bandeja com mic
  real + o teste) devolviam transcrição VAZIA. Corrigido com `threading.Lock` no
  `NemotronStt.transcribe`.
- Alimentar o pre-roll com `feed()` disparava transcrição DENTRO do event loop e travava o
  servidor (keepalive ping timeout). Criado `SttStream.prime()`, que só acumula.
- Na fase COMMAND o silêncio pós-"Jarvis" encerrava a captura antes da pessoa falar →
  só encerrar por silêncio depois que houve fala (`_speech_seen`).
- Ruído solto acionava o STT à toa → exigir fala contínua (`vad.min_speech_ms`, 240ms).

## "Falo Jarvis e não abre" + erro ao ligar a máquina (2026-08-01)

Três causas independentes, todas confirmadas com medição (não chute):

1. **Microfone MUDO era a causa principal.** O padrão do Windows é o headset
   Astro A50; com ele na base, capta silêncio digital absoluto (-91 dB medido com
   `ffmpeg volumedetect`). Os outros mics ouvem bem (NVIDIA Broadcast -13 dB pico,
   Notebook Realtek -22 dB). Corrigido com **watchdog de microfone** no app: 15s sem
   sinal → troca sozinho pro próximo e salva a preferência. Cuidado com o limiar:
   `getByteTimeDomainData` tem piso de quantização de 1/128 = 0.0078, então mic morto
   NÃO dá zero — usar limiar 0.006 sobre o nível do worklet (que é int16 e dá 0 real).
2. **`forrtl: error (200): program aborting due to window-CLOSE event`** — runtime
   Fortran da Intel (dentro de numpy/scipy) mata o processo quando o console recebe
   evento de fechar/logoff. Era o erro ao ligar o PC. Corrigido com
   `FOR_DISABLE_CONSOLE_CTRL_HANDLER=1` nos `.bat`.
3. **App da bandeja carregava a UI DO SERVIDOR** — no boot o servidor ainda estava
   subindo (~1min de modelo), o load falhava e o retry usava `getURL()` (vazio após
   falha), deixando o app órfão. Agora a interface é **empacotada no app**
   (`sync-web.js` copia `apps/web/dist` → `apps/desktop/build/web`, Vite com
   `base: './'`) e só o WebSocket depende do servidor.

Descoberta importante do teste acústico: pelo alto-falante, o STT transcreve "Jarvis"
como **"já fiz"** (duas palavras). O matcher ganhou comparação **fonética** (v↔f,
z↔s, h mudo, dígrafos) e teste de **bigramas colados** — "já fiz"→"jafis" vs
"jarfis" = 1 edição. Falso positivo evitado exigindo ≥5 letras pra tolerar 2 edições
("já vi" não dispara).

Infra de diagnóstico criada (usar SEMPRE antes de chutar):
- `GET /api/audio/debug` — rms/VAD por dispositivo, direto do pipeline.
- `window.__jarvisDiag()` no app (via CDP) — mic em uso, frames, pico, prefs.
- `tests/diag_microfones.py` — mede todos os mics tocando som pelo alto-falante.
- `tests/test_mic_real.py` — E2E acústico REAL (toca no alto-falante via CDP+setSinkId,
  confere em `/api/metrics/recent`). Resultado: ouviu "liga a luz da sala", 2,3s.
- Tarefa **JARVIS Watchdog** (5 em 5 min) religa servidor/voz/app que estiverem fora.

Armadilha de teste: `Get-Process JARVIS` NÃO pega o app em dev (lá o processo chama
`electron.exe`) — matar só o JARVIS.exe deixa a instância antiga viva e o
singleInstanceLock derruba a nova, fazendo parecer que a correção não funcionou.
Filtrar por `Path` contendo o projeto (e nunca matar o Electron do agent-code).

## STT híbrido + TTS em streaming + janela (2026-08-01)

- **STT agora é híbrido** (`stt/hibrido.py`): Nemotron nas parciais (reator acende em
  ~570 ms) + Whisper large-v3-turbo na final (WER 0.000 até com ruído, contra 0.062 do
  Nemotron). Benchmark em `tests/bench_stt.py`, números em [STT.md](STT.md).
- **TTS em streaming** (`tts/chunker.py` + `dialog._falar_em_stream`): consome o LLM em
  stream e fala a partir de ~3 palavras; pedaços crescem até 14. O device toca em fila
  por `seq`. Antes: 40 s de silêncio. Agora: fala quase imediata.
- **"Um momento." pré-gerado** ao cair no LLM (o 1º token do DeepSeek demora ~6 s).
- **Janela do PC** só some quando não está processando NEM falando (flags separadas
  `processando`/`falando` em `main.js`; evento `speaking` pelo preload).

Armadilhas descobertas aqui (todas custaram tempo):
- Carregar Nemotron e Whisper EM PARALELO quebra o import de `transformers`
  ("cannot import name 'AutoModel'") — carregar sequencial.
- NeMo precisa de `transformers` 4.x; com 5.x nem importa.
- O LLM entrega token a token e **parte palavras** ("del"+"imit"+"ada"): o chunker só
  corta em limite de palavra real, usando posições do texto original (usar
  `" ".join(palavras)` para calcular o corte desalinha os índices com o buffer).
- `document.visibilityState` do Chromium NÃO muda quando a janela Electron é escondida
  (com `backgroundThrottling: false`) — testar visibilidade perguntando ao main process
  (`win.isVisible()` via `ipcMain.handle`).
- No teste da janela, o app está ouvindo a sala de verdade e um barulho acorda o JARVIS
  no meio da medição — o teste desliga o WebSocket do app durante a checagem.
- Benchmark de STT com a GPU ocupada faz o Whisper cair pra CPU (45 s/frase vs 0,7 s).

## Bateria de testes de velocidade (2026-08-02) — ver [DESEMPENHO.md](DESEMPENHO.md)

Números completos e como repetir estão em DESEMPENHO.md. O essencial:

- **STT passou a ser UM modelo: whisper `small` com initial_prompt.** Ele gera as
  próprias parciais (`whisper_parciais: true`). Motivos medidos: o `large-v3-turbo`
  leva **14,7s/frase nesta GPU** (sem kernel otimizado; na CPU são 4,7s) e o
  Nemotron reconhece o nome em só 2/8 áudios difíceis contra 8/8 do small+prompt.
  Não vale manter 2 modelos: o small é tão rápido quanto o "rápido" (0,12 x 0,10s).
- **`initial_prompt` é o que ensina o nome "Jarvis"** ao modelo; sem ele sai
  "Já Luiz"/"Jairus". Custa ~0 no small (mas custa MUITO no turbo).
- **`think=False` é obrigatório no Qwen3.x** — senão a resposta vem VAZIA
  (ele gasta tudo pensando). `/no_think` no prompt NÃO resolve; tem que ser
  parâmetro (o LiteLLM aceita `think=False` ou `extra_body`).
- **A GPU dormindo custava 2s por pergunta**: cai pra 225 MHz (P8) quando ociosa.
  `keep_alive` não resolve (o modelo continua carregado, é a placa). Solução:
  `despertar_gpu()` disparado no wake, acordando LLM e voz em paralelo enquanto o
  usuário ainda fala. Ganho medido: 2,4s -> 0,35s no primeiro token.
- Prompt gordo custa caro em modelo pequeno: histórico foi limitado a 2 trocas
  truncadas (`llm.historico_trocas` / `historico_max_chars`).

Resultado final: comando da casa executa **0,14s depois que você para de falar**;
reator acende em 0,48s (enquanto ainda fala). O que sobra pesado é a síntese de
voz da resposta longa do LLM (~1,2x tempo real).

Armadilha de medição: benchmark com a GPU disputada mente feio — o mesmo
large-v3-turbo marcou 0,28s numa medição suja e 14,7s numa limpa. Sempre parar
os serviços antes de medir modelo.

## LLM local + nome "Jarvis" na transcrição (2026-08-01)

**LLM trocado para `ollama_chat/qwen3.5:0.8b`** (local, 1 GB) a pedido do Matheus.
`api_base` aponta pro Ollama; `no_think: true` desliga o raciocínio do Qwen3.x e há
um `_FiltroPensamento` no stream removendo `<think>...</think>` (com tag partida
entre pedaços). Alternativa de nuvem comentada no settings.

**A demora do LLM NÃO era o modelo.** Medições:
- DeepSeek direto: 0,96s até a 1ª palavra; ADK por cima: +0,2s.
- Mas pelo caminho do JARVIS dava 5,46s **na primeira pergunta** e 0,84s da segunda
  em diante — era o agente sendo CONSTRUÍDO na 1ª chamada. Corrigido com
  `agents.agent.aquecer()` chamado no lifespan (monta o agente + abre conexão).
- Qwen3-1.7B local (4 bits, 1,26 GB): 0,41s mas erra fatos ("Santos Dumont foi um
  escritor francês"). Qwen3-4B não chegou a ser medido.

**Transcrição: o problema é o nome próprio.** No log real o STT escreve
`Já, Luiz` / `Jairus` / `Já vi` / `Já Ravid` / `já abriu` no lugar de "Jarvis".
Duas correções:
1. `whisper.py` passa `initial_prompt` + `hotwords` com o nome e o vocabulário da
   casa (`_hotwords_padrao()`), pro modelo saber que "Jarvis" existe;
2. `wakeword.py` aceita variante FRACA do nome só quando o resto da frase é um
   comando conhecido (`_parece_keyword` + `_eh_comando`) — assim "Já, Luiz. Acende
   a luz da sala" funciona e a TV falando "já vi esse filme" não acorda o JARVIS.

Falta medir (a GPU está ocupada com o treino do Matheus): velocidade real do
qwen3.5:0.8b e o Canary como alternativa de STT.

## Janela do PC: arrastar, ocultar e transparência (2026-08-01)

- Arrasta por qualquer ponto vazio (`-webkit-app-region: drag` no `.stage.desktop`);
  os controles precisam de `no-drag` senão param de receber clique.
- Botão X recolhe pra bandeja (IPC `jarvis-hide`), não encerra.
- Posição salva em `config.json` (evento `moved`, com debounce) e restaurada checando
  se ainda cabe em algum monitor.
- **Opacidade por foco** (`main.js → OPACIDADE`): 1.0 focada, 0.92 sem foco mas
  respondendo, 0.28 sem foco e parada. Transição suave por `setInterval`.

Armadilha nos testes de janela: abrir outro app NÃO garante troca de foco a tempo —
o teste ficava reportando `focada: True` e falhando à toa. Só ficou confiável com
`Start-Process -PassThru` + `WScript.Shell.AppActivate($p.Id)` em loop, e esperando o
foco mudar de verdade antes de medir. Para saber o estado real da janela existe o IPC
`jarvis-window-info` (visível/focada/opacidade/processando/falando).

## Disco C: encheu (2026-08-01)

O C: chegou a **0 GB livres** — isso corrompeu downloads de modelos (chatterbox `ve.pt`,
parakeet, whisper) e a instalação do `transformers`, causando erros que pareciam de
código. O cache do HuggingFace (50 GB) foi movido para `D:\ai-cache\huggingface` e
`HF_HOME` está setado na conta do usuário E nos dois `.bat` (sem isso o cache volta pro
C: e baixa tudo de novo). C: ficou com ~65 GB livres.

## Multi-agente: roteador + especialistas + observador (2026-08-02) — ver [AGENTES.md](AGENTES.md)

Decisão em três camadas, da mais barata pra mais cara: **Intent Router (regex, 0ms) →
roteador `qwen3.5:0.8b` (~0,35s) → agente especialista**. Agentes: `casa`, `sistema`,
`conversa` e `avancado` (GPT-5.6 Luna, nuvem opcional). Cada interação vira **registro**
(WAV + transcrição + rota + resposta) e o **observador** relê só o que deu sinal de
problema. Validado com voz real ponta a ponta (`tests/test_agentes_e2e.py`, 4/4) e
14/14 de acerto de destino em `tests/bench_roteador.py`.

Bugs reais achados e corrigidos nesta etapa:

- **`aquecer()` do agente falhava calado** desde que `max_tokens` entrou em `_extras_llm`:
  `acompletion(..., max_tokens=1, **extras)` = "multiple values for keyword argument".
  Resultado: a primeira pergunta voltava a custar ~4,5s. Regra: `max_tokens` sempre
  DENTRO do dict (`{**_extras_llm(cfg), "max_tokens": N}`). O mesmo padrão estava no
  observador.
- **Whisper alucinando o próprio `initial_prompt`** em silêncio ("falando com falando com
  o jarvis f"). Como o prompt tem "Jarvis" dentro, passava pelo wake word e virou um
  pedido fantasma que ACIONOU UM AGENTE. Filtro `WhisperStt._eco()` (comparação por
  palavra, não por substring — substring não pega o truncado).
- **`pedido_repetido` comparava a interação com ela mesma** (a checagem roda depois de
  gravar): 5 de 5 interações acionaram o observador no primeiro teste real. Corrigido com
  `ignorar_id`.
- **Modelo pequeno respondendo a pergunta ANTERIOR**: o pedido atual ficava colado no fim
  do histórico sem marcação. Agora vai como `PEDIDO AGORA: ...` + "Responda APENAS a este
  pedido".
- **Roteador inventando fato** ("aumenta o volume" → explicação falsa) e **falando o molde
  do prompt em voz alta** (`<uma frase curta>`). Trava no servidor: resposta direta só pra
  papo social + filtro de lixo. Cumprimento virou intent local com áudio pronto.
- `library.pick()` devolvia None pra intent sem wav gerado e o JARVIS ficava **mudo**;
  agora cai no TTS com uma das frases do `responses.yml`.
- `test_audio_e2e.py` rodava inteiro ao ser importado por outro teste → guarda
  `if __name__ == "__main__"`.

Achados da revisão de código da mesma etapa (todos corrigidos e validados):

- **A janela do PC ficava PRESA na tela depois de toda resposta pronta.** O device liga
  "estou falando" no `speak` de seq 0 e só desliga no `speak_end` — e o caminho da
  biblioteca ("Pronto.", "Bom dia.") nunca mandava `speak_end`. Bug pré-existente que os
  cumprimentos novos escancararam. Agora `_fim_da_fala()` fecha TODOS os caminhos
  (`tests/test_fim_da_fala.py` cobre os 7; provado no EXE instalado com
  `tests/test_janela_destrava.py`).
- **O registro segurava o microfone.** WAV + 2 commits do SQLite rodavam antes de
  `pipeline.set_idle()`, com o pipeline em BUSY: dava pra falar e ele não ouvir. Agora o
  PCM é capturado na hora e o resto vai pra `asyncio.create_task`.
- **`aquecer()` preparava o agente errado.** Como quem atende agora é sempre um
  especialista, cada um era montado a frio (Agent + Runner + `load_toolsets()`) DENTRO do
  event loop na primeira vez que era escolhido. Agora aquece os 4 no start, em thread.
- **`avancado` era oferecido sem a chave da nuvem**: numa máquina sem `config/.env` (que é
  gitignored), toda pergunta difícil morria em erro de autenticação engolido e voltava
  como "não entendi", sem pista nenhuma. `nuvem_disponivel()` agora exige a chave, e o
  agente some da lista sem ela.
- **Áudio de fala DESCARTADA vazava pro registro seguinte**: conversa na sala sem chamar o
  JARVIS ficava guardada e era gravada como se fosse o pedido seguinte. O áudio só é
  publicado quando a fala vira pedido (`_publicar_audio`).
- Buffer de gravação era `np.concatenate` a cada frame de 80ms (~150 cópias por fala, no
  event loop) → lista de pedaços + um concat no fim, e nem roda com `registro.ativo: false`.
- `registros` crescia pra sempre (só os WAV eram apagados) → `limpar_registros(corte)` no
  start; e o `rmdir` da pasta do dia estava DENTRO do `except StopIteration`, então um erro
  ali abortava a limpeza dos dias seguintes.
- `Registro.erro` nunca era preenchido → o gatilho `tarefa_falhou` do observador era letra
  morta. Agora skill que falha e agente mudo gravam o motivo.

Regra que ficou: **exemplos por agente são o que mais move a agulha** no roteador — com 2
exemplos "que temperatura está aqui" ia pro `sistema`; com 3, foi pro `casa`.

## Nuvem: `reasoning_effort: low` e o aquecimento da conexão (2026-08-02)

`low` é o mínimo que o `gpt-5.6-luna` aceita (`minimal`/`none` são recusados). Ganho real,
medido A/B **intercalado**: 1ª palavra em 0,93–1,08s contra 1,24–1,78s no `high`. O ADK
repassa o parâmetro (provado mandando um valor inválido: a chamada morre).

**A primeira medição estava errada** — não intercalada, sugeriu 2,7x de ganho quando o real
é ~0,3s. A API oscila muito; medir tudo de A e depois tudo de B faz a oscilação virar
"diferença". Vale pra qualquer benchmark contra API externa.

**O gargalo de verdade era a primeira chamada**: 5,57s contra 0,69s nas seguintes (DNS +
TLS + cliente do litellm), caindo justo na pergunta difícil. `aquecer()` agora abre a
conexão com o provedor no start; no servidor real a 1ª pergunta pra nuvem depois de
reiniciar caiu de 3,43s pra 1,74s.

Armadilha: aquecer com `max_tokens=1` **não funciona** em modelo de raciocínio — ele pensa
antes de escrever e estoura o limite ("Could not finish the message"). Usar ~32.

## Parakeet TDT v3 testado e descartado por ora (2026-08-02) — ver [STT.md](STT.md)

Medido com a GPU livre, mesmas 24 amostras: **velocidade empatada** (0,14s x 0,16s do
Whisper) e **pior no que decide** — escreve "Jarvis" em 11/24 contra 24/24, acorda o
assistente em 20/24 contra 24/24.

O motivo não é qualidade do modelo, é estrutural: o Whisper aceita `initial_prompt` +
`hotwords` (o que leva o small de 14/24 pra 24/24) e o Parakeet, sendo transducer, não tem
gancho de texto. O equivalente seria *word boosting* do NeMo — mas o NeMo instalado **não
expõe isso** no `decoding` (só `strategy, model_type, durations, greedy, beam`). Pelo NeMo
ele ainda ficou mais lento (0,42s) e pior (1/8).

Notas práticas:
- Precisa de `transformers >= 5.10`; o env `jarvis` está pinado em 4.x por causa do NeMo.
  Rodar no `jarvis-llm` (transformers 5.14).
- `ParakeetForTDT.generate()` devolve `ParakeetRNNTGenerateOutput(sequences, durations)`:
  passar o objeto inteiro pro `batch_decode` estoura com `'str' object cannot be
  interpreted as an integer`; e sem `skip_special_tokens=True` o texto vem com `<blank>`.
- A favor dele, e que continua valendo: **transducer não alucina em silêncio** como o
  Whisper (que já criou pedido fantasma repetindo o próprio prompt).

## Decisões e aprendizados importantes

- **Wake word e VAD são STATEFUL → uma instância POR CONEXÃO** (`AudioPipeline.init()`).
  Compartilhar entre devices corrompe o buffer temporal (bug real encontrado: o tablet
  streamando silêncio matava a detecção da outra conexão).
- Wake word roda no SERVIDOR (device fino); ack é wav local no device (SoundPool) → latência
  do wake→ack ≈ RTT da LAN. Modelo `hey_jarvis` do openWakeWord: score 0.99 com pronúncia
  inglesa, ~0.03 com TTS PT-BR falando "Hey Jarvis" — em teste, gerar o áudio de wake com voz
  `en-US-*`. Threshold 0.4.
- Nemotron 3.5: `transcribe()` devolve `Hypothesis` e anexa tag `<pt-PT>` — removida por regex
  no engine. Estratégia atual = transcrição incremental (parcial a cada 0.8s); cache-aware
  streaming nativo fica como evolução.
- STT final ≈ 300ms na GPU; latência pós-fala ≈ 1.1s (0.8s de silêncio do VAD + STT).
- torch instalado 2x: o `pip install torch` do requirements puxa CPU; forçar
  `--index-url .../cu128 --force-reinstall` DEPOIS.
- torchaudio.load exige torchcodec+ffmpeg shared no Windows → nos testes o decode de mp3 é
  via ffmpeg CLI (`-f s16le`).
- pip novo rejeita `#egg=nemo_toolkit[asr]` → usar `"nemo_toolkit[asr] @ git+..."`.
- Emulador Android acessa o host por `10.0.2.2`. adb fica em
  `C:\Users\mathe\AppData\Roaming\agent-code-desktop\android-sdk\platform-tools`.
- Lint fatal no wear release (`InvalidFragmentVersionForActivityResult`) → resolvido com
  `androidx.fragment:fragment-ktx:1.8.3` explícito.

## Pendências / próximos passos

- [ ] Conectar Home Assistant REAL (falta URL + token do Matheus; modo mock ativo).
- [ ] Testar o wake com a voz real do Matheus e calibrar (`fuzzy_max_edits`,
      `vad.min_speech_ms`). Observado no log: o app da bandeja com mic real chegou a
      registrar um "chamou: 'Jarvis.'" sem ninguém falar — se acontecer muito, subir
      `min_speech_ms` ou baixar `fuzzy_max_edits` pra 1.
- [ ] Instalar APK no tablet/celular/relógio reais (wear não foi testado em emulador Wear).
- [ ] Voz definitiva do TTS (hoje edge-tts AntonioNeural; ideia: Chatterbox/voz clonada).
- [ ] Cloudflare Tunnel `jarvis.larchertech.com` pra acesso externo.
- [ ] Wake word custom "Jarvis" PT-BR (treinar openWakeWord).
- [ ] Cache-aware streaming nativo do Nemotron (att_context_size) pra baixar a latência do parcial.
- [ ] GIF de demo no README.
- [ ] Contexto por GPS/Bluetooth/geofence (hoje: rede Wi-Fi + device_id + configuração manual).
- [ ] LoRA no `qwen3.5:0.8b` com os registros gravados, pra ele rotear melhor com o jeito
      do Matheus falar (o registro já guarda áudio + rota + correção do observador; falta
      juntar volume de dados de uso real).
- [ ] Ferramentas de verdade pro agente `sistema` (hoje ele só sabe dizer que não sabe).
- [ ] Tela pra ouvir/corrigir os registros (hoje só `tests/ver_registros.py` no terminal).
- [ ] **Cache do "Sim?" no Android ignora a troca de voz.** O servidor manda a URL com
      `?v=<mtime>`, mas `AudioEngine.kt` guarda o arquivo por NOME (`ack_$name`) e pula o
      download se já existir — trocar a voz não chega no celular/relógio. Achado na revisão
      de 02/08; não corrigido porque não dá pra validar sem o aparelho na mão. Correção:
      usar a URL inteira (ou o `v=`) na chave do arquivo em cache.

## Configurações que dependem do usuário

- URL + token do Home Assistant; entity_id reais das luzes e do sensor de temperatura.
- IP fixo/reserva DHCP do notebook na LAN (os apps apontam pra ele).
