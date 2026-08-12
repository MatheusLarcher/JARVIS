# JARVIS — Memória do projeto (ler antes de mexer)

> Atualizar ao fim de cada etapa: o que foi feito, decisões, arquivos, problemas, próximos passos.

## Estado atual (2026-07-31)

MVP COMPLETO e validado ponta a ponta por teste automatizado (`tests/test_audio_e2e.py`):
wake "Hey Jarvis" → ack local → "liga a luz da sala" → Nemotron transcreve → Intent Router
→ HA (mock) liga → resposta pronta da biblioteca → DONE → repouso. Sem LLM no caminho.

- **Ambiente:** conda env `jarvis` (Py 3.11), torch 2.11+cu128 (RTX 5050 ok), NeMo do git main
  (o do pip 2.7.3 NÃO carrega o modelo — falta `rnnt_bpe_models_prompt`).
- **Servidor:** porta 8040, log em `server/data/jarvis.log`. Quem sobe é o app da
  bandeja (supervisor: Ollama 11434, servidor 8040, voz 8041, revisão a cada 30s).
  Ele entra no boot só se você marcar "Iniciar com o Windows" na engrenagem — as
  tarefas agendadas foram removidas. Ver "Um auto-start só, marcado por você".
- **Web:** buildada em `apps/web/dist`, servida na raiz do 8040. Validada no browser.
- **Android:** `apps/android` (`:app` tablet+celular, `:wear` relógio; código comum em
  `apps/android/shared/java`). Release assinado em `releases/Jarvis.apk` e
  `releases/Jarvis-Watch.apk` (keystore `jarvis-release.keystore`; a senha fica fora do
  repositório — ver INSTALACAO.md).
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
- `server/watchdog.ps1` religa Ollama/servidor/voz/app que estiverem fora, mas **nada
  o agenda**: virou ferramenta manual. Quem vigia é o app, a cada 30s.

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

## Mover o projeto quebrou o auto-start inteiro (2026-08-03)

O projeto saiu de `~\Documents\GitHub\JARVIS` e foi pra `C:\GitHub\JARVIS`. Nada avisou.
Quatro coisas guardavam esse caminho por extenso e passaram a apontar pro vazio:

1. Tarefa **JARVIS Server** — última execução em 01/08 com resultado 1; desde então o
   servidor nunca mais subiu no logon.
2. Tarefa **JARVIS Watchdog** — mesma coisa, então a rede de segurança também caiu.
3. Fallback do token no `main.js` do app da bandeja.
4. `trocar_tokens.py`, que ainda por cima escrevia em `%APPDATA%\jarvis-desktop\` quando
   o Electron usa `%APPDATA%\JARVIS\` (a pasta vem do `productName`).

O 4 é o pior porque **falhava em silêncio**: a rotação de tokens de 02/08 não chegou no
app, ele continuou tentando entrar com o token velho e o servidor recusava com `4401`
(`conexão recusada: pc-matheus` no log). Pra quem estava na frente do PC, o JARVIS
simplesmente não respondia.

As duas tarefas foram criadas com `schtasks /TR "...\arquivo.vbs"`. **A barra invertida
antes da aspa final escapa a aspa**: o caminho e o `/RL LIMITED` viraram um argumento só
(`wscript.exe " C:\...\start_jarvis_hidden.vbs\ /RL LIMITED`). Usar
`Register-ScheduledTask`, que recebe o caminho como argumento, não tem esse problema.

**O que mudou.** O app da bandeja virou o **supervisor**: ele já entrava na chave `Run`
do Windows, e agora confere as portas 11434/8040/8041 no start e a cada 30 s, subindo o
que faltar (`garanteServicos` no `main.js`). Ninguém subia o Ollama antes — nem o
watchdog. A raiz do projeto é gravada no pacote pelo `sync-web` (`build/projeto.json`) e
o token passa a vir **sempre** do `devices.yml` dessa raiz, não só quando a cópia local
está vazia. Resultado: abrir o exe liga o JARVIS inteiro.

Armadilhas encontradas ao consertar:
- `.ps1` **sem BOM é lido como ANSI** pelo Windows PowerShell 5.1 — um "não" acentuado
  no script vira erro de parser. Por isso `watchdog.ps1` e `instalar_tarefas.ps1` são
  ASCII puro.
- `-RepetitionDuration ([TimeSpan]::MaxValue)` gera `P99999999DT23H59M59S`, que o
  agendador recusa ("valor fora do intervalo"). Omitir o parâmetro = repetição indefinida.
- Regravar tarefa que já existe criada por outro contexto exige **administrador**; criar
  tarefa nova, não. As duas antigas continuam lá, quebradas, até rodar
  `instalar_tarefas.ps1` elevado — o que não bloqueia nada, porque o app cobre.
- Filtrar processos por `CommandLine -like "*start_jarvis*"` pega **o próprio PowerShell**
  que roda o filtro (a string está na linha de comando dele). Excluir `$PID`.

## A voz clonada é lenta demais pra resposta ao vivo (2026-08-11)

Matheus: *"a voz tá demorando a ser construída com o tts q vc botou, preciso q seja
rápido"*.

Medido nesta placa, mesma frase de 7 palavras: Chatterbox **10,2 a 24,1 s**,
edge-tts **1,3 a 1,8 s** (1º áudio ~1,0 s). O RTF real é **3–5x**, não os 1,7–2,5
que estavam anotados no VOZ.md.

Descartado como causa, tudo medido:
- `cfg_weight` 0,5 / 0,3 / 0,0 — sem diferença (o CFG não é o gargalo);
- disputa de VRAM — descarregar o modelo do Ollama (7359 → 7280 MiB) não mudou nada;
- clock da GPU — estava em 2797 de 3090 MHz, não era a placa dormindo;
- streaming — o Chatterbox 0.1.7 **não tem** (`[m for m in dir(M) if 'stream' in m]`
  volta vazio), então não dá pra tocar antes de terminar de gerar.

É lentidão do modelo. As quatro defesas que já existiam (biblioteca, cache, aquecedor,
chunking) cobrem só o que **repete** — e a resposta que o modelo inventa na hora nunca
repete, então paga o preço inteiro toda vez.

Perguntei ao Matheus qual caminho seguir (trocar por XTTS-v2, usar edge-tts em tudo, ou
híbrido) e ele não respondeu em 7 min. Segui pelo **híbrido, que é o reversível**:
`tts.perfil_resposta: jarvis_edge` no settings.yml. Frase pronta continua na voz
clonada (já está em disco, toca instantânea); só a resposta livre troca de voz.
Apagar a linha volta tudo como era.

**Achado ao revisar as medições antigas:** os `tts_first_audio_ms` de ~1,7 s que eu
tinha registrado em 03/08 provavelmente **já eram edge-tts**, entrando pelo
`fallback` do perfil quando o serviço de voz falhava (`TTS clone falhou
(ConnectError) → usando voz de reserva`). Ou seja, a voz clonada já vinha falhando ao
vivo sem ninguém perceber — o fallback existe justamente pra não ficar mudo, e
escondeu o problema.

Pendente: XTTS-v2 num env isolado, medido antes de trocar, é o caminho pra ter a voz
clonada **e** velocidade.

## O back roda dentro do app (2026-08-08)

Pedido do Matheus: *"o back tem q ficar dentro do exe, não quero q apareça cmd dele"*.

**Embutir de verdade não cabe:** medido, o env `jarvis` tem **6,23 GB**, o
`jarvis-tts` **5,18 GB**, e os modelos ocupam **69,7 GB** em `D:\ai-cache`. Um exe
com tudo dentro passaria de 11 GB e ainda não resolveria os modelos. O exe segue com
78 MB usando os envs conda da máquina — mesma escolha que ele já tinha feito no
`english_teach` quando mostrei os números.

**O que dava pra resolver, e foi resolvido:** o console. A cadeia era
`wscript → cmd → start_jarvis.bat → python`, com o reinício feito por
`timeout /t 5 /nobreak` dentro do `.bat`. Cada elo é uma chance de janela aparecer.

Agora o Electron roda o `python.exe` **direto**: sem cmd, sem `.bat`, sem `.vbs`, e o
laço de reinício é JavaScript (`sobeServico`, com espera de 5 s e checagem da porta
antes de insistir). O env vai no `spawn` (`FOR_DISABLE_CONSOLE_CTRL_HANDLER`,
`HF_HOME`) e a saída dos processos é anexada aos mesmos `jarvis.log` / `voice.log`.

Ganhos além do console sumir:
- **cada serviço é independente** — nenhum sobe o outro, então some de vez a corrida
  que fazia duas cópias da voz disputarem a 8041;
- **o back é do app**: fechar o JARVIS fecha o back junto, com **zero órfãos**.
  Vale até em kill forçado, porque o Electron põe os filhos no mesmo *job object* —
  testado matando o `JARVIS.exe` com `Stop-Process -Force`.

Medido na partida a frio: `8040` e `8041` sobem, os dois `python.exe` aparecem com
`ParentProcessId = JARVIS.exe`, e a contagem de `cmd/wscript/timeout` fica em **0**
durante os 100 s de observação.

Os `.bat` continuam no repositório para subir o servidor na mão, e mantêm a trava de
duplicata.

## O "cmd de nobreak" piscando na tela (2026-08-08)

Sintoma do Matheus: **"tá aparecendo um cmd de nobreak toda hora"**. Era mesmo uma
janela `timeout /t 5 /nobreak`, e a árvore de processos entregou a causa:

```
cmd /c start_jarvis.bat      <- o app subiu o servidor
  └ cmd /c start_voice.bat   <- o .bat já sobe a voz junto     OK
cmd /c start_voice.bat       <- o app subiu a voz DE NOVO      bug
  └ timeout /t 5 /nobreak    <- a janela que aparecia
```

Bug meu, no `garanteServicos`: na subida a porta 8040 estava fechada, então o app
rodava o `.vbs` do servidor — **que sobe a voz junto**. Trinta segundos depois, a
revisão via o servidor no ar e a 8041 **ainda** fechada (o Chatterbox demora a
carregar) e subia uma segunda cópia da voz. A perdedora da porta morria na hora, o
`:loop` do `.bat` a reerguia, e a janela do `timeout` piscava a cada 5 s, pra sempre.

Três consertos, do mais específico ao mais geral:

1. Ao subir o servidor, o app marca a voz como "já subindo" — porque o
   `start_jarvis.bat` cuida dela.
2. `start_jarvis.bat` e `start_voice.bat` ganharam trava de duplicata: se a porta já
   tem dono, a cópia **sai** em vez de reiniciar pra sempre. É a rede de segurança
   que vale mesmo se alguém subir o `.bat` na mão.
3. A voz agora sobe por `start_voice_hidden.vbs`. O `windowsHide` do Node esconde o
   `cmd`, mas o `timeout.exe` de dentro do loop abre console próprio e aparece.

**Armadilha da trava:** a mensagem não podia ir pro `voice.log`. O serviço que está
no ar segura esse arquivo (`>> voice.log` no `.bat`), e a duplicata levava
"O arquivo já está sendo usado por outro processo" — saía com código 0 e **sem deixar
rastro**, o que me fez achar que a trava não tinha funcionado. Vai pro
`server/data/startup.log`, que ninguém segura.

Validado com partida a frio: os três serviços sobem, sobra **um** loop de cada e
**zero** `timeout.exe`, e o `startup.log` mostra as 3 duplicatas de corrida saindo
sozinhas.

> **Armadilha de diagnóstico que me pegou duas vezes nesta sessão:** contar processos
> com `Get-CimInstance ... CommandLine -match 'start_voice'` conta **o próprio
> PowerShell**, que tem essa string na linha de comando. Deu "6 loops de voz" quando
> havia 1. Sempre excluir `powershell.exe` (ou o `$PID`) do filtro.

## Um auto-start só, marcado por você (2026-08-04)

Sintoma do Matheus: **"quando inicia o pc, tá dando erro em um script jarvis"**.

Era a tarefa **"JARVIS Server"**, que ainda chamava
`wscript.exe "...\Documents\GitHub\JARVIS\server\start_jarvis_hidden.vbs"` — caminho
que deixou de existir quando o projeto mudou de pasta. O `wscript` não acha o arquivo
e abre uma **caixa de erro em todo boot**.

Levantando tudo, o JARVIS tinha **quatro** mecanismos de auto-start ao mesmo tempo:
as tarefas "JARVIS Server" e "JARVIS Watchdog", a chave `Run` do usuário e um atalho
`JARVIS.lnk` na pasta Inicializar. Os quatro foram removidos.

E havia um defeito que tornava a opção existente inútil: o `main.js` fazia
`app.setLoginItemSettings({ openAtLogin: true })` **a cada início**. Desmarcar
"Iniciar com o Windows" no menu da bandeja não colava — bastava reabrir o app pra
voltar sozinho.

Agora existe **uma** fonte de verdade: a opção "Iniciar com o Windows", na engrenagem
da janela e no menu da bandeja (as duas gravam no mesmo lugar). A escolha vai pro
`iniciarComWindows` do `config.json` e é aplicada com `setLoginItemSettings`. Sem
escolha salva, vale o que o Windows já tem registrado — ou seja, instalar não liga
nada por conta própria.

Coberto por `tests/test_iniciar_com_windows.py`, que clica na interface de verdade e
confere a chave `Run` **por fora do app** — marcar, desmarcar, marcar de novo — e
depois reinicia o app duas vezes pra provar que a escolha sobrevive.

### Bug achado durante esse teste: `log()` entrava em laço com o stdout fechado

O `console.log` do `log()` estava **fora** do `try`. Quando o app é aberto por um
terminal que fecha, escrever na saída dá `EPIPE`; como o
`process.on('uncaughtException')` chama esse mesmo `log()`, virava
`EPIPE → log → EPIPE`. Na prática o `desktop.log` enchia de stack trace e a janela se
recarregava no meio do uso — foi assim que o modal sumiu no primeiro teste. O
`console.log` agora tem o próprio `try`.

## Caça a bugs no caminho do pedido (2026-08-03)

Varredura do fluxo inteiro com o sistema no ar, medindo cada etapa pela telemetria.

**1. Histórico velho envenenava o prompt** (`memory/db.py::recent_history`). A consulta
pegava as últimas N trocas do device **sem filtro de tempo**. Perguntado "quem foi Santos
Dumont", o agente `conversa` respondeu falando de *"jantar"* e *"dispositivo web"* —
assunto de uma conversa de **10 horas antes**, injetada como "[conversa anterior]".
Corrigido com janela de tempo (`llm.historico_max_idade_min`, 10 min). Depois do
conserto a mesma pergunta responde `"Não sei."`, que é o comportamento honesto que o
prompt pede. Também economiza tokens, que é latência.

**2. O roteador rodava com temperatura padrão (~0.8).** Escolher agente é
CLASSIFICAÇÃO, não criatividade: a mesma frase caía em agentes diferentes a cada
tentativa ("põe um alarme" ora `sistema`, ora `conversa`). Isso ainda tornava qualquer
medição de acerto do roteador sem sentido — o `bench_roteador` variava por acaso.
`temperature: 0` deixou as 4 frases de teste 100% estáveis em 5 repetições.

**3. Nome de agente acentuado nunca casava.** O modelo escreve `AGENTE: avançado` e a
config chama `avancado`: caía sempre no casamento aproximado, marcava confiança baixa e
com isso **acordava o observador à toa** — outra chamada de LLM disputando a mesma GPU.
Corrigido comparando sem acento.

**4. O roteador gerava ~35 tokens de lixo depois da decisão.** A resposta útil é a
primeira linha; o resto era invenção jogada fora (`'AGENTE: conversa\nSanto Dumont
(1965-2013), conhecido como "Dino", era um compositor...'`). Resolvido com
`stop=["\n"]` e `max_tokens=16`.

**5. `ask_stream` não filtrava o ramo da resposta final** (`agents/agent.py`). O
`_FiltroPensamento` e o `_CortaResposta` só rodavam no ramo `partial`. Quando o evento
chega sem parcial — acontece depois de chamada de ferramenta — o texto ia CRU pra voz:
`<think>` falado em voz alta e limite de tamanho ignorado.

**6. `llama-server` órfão segurando VRAM.** Quando o `ollama.exe` morre, os
`llama-server.exe` filhos **sobrevivem**. Nesta placa de 8 GB um órfão de 1,1 GB deixou
a VRAM em 7463/8151 MiB. Como o watchdog reergue o ollama sempre que a porta cai, cada
reinício deixava mais um. O watchdog agora mata os órfãos (pai morto) antes de subir.

**7. `tests/test_ws_flow.py` e `test_tts_stream.py` quebravam na primeira linha** —
`Path` usado sem `from pathlib import Path`, desde o commit 5d0d12c (auditoria de
segurança). O `test_ws_flow.py` é um dos três testes que o INSTALACAO.md manda rodar.

### Onde o tempo vai, medido (fim da fala → primeira palavra da resposta)

| Etapa | Custo |
|---|---|
| Roteador (modelo pequeno) | ~1,06 s |
| Agente, 1º token | ~1,05–1,42 s |
| TTS, 1º áudio (voz clonada) | ~1,7–1,95 s |

**Toda chamada ao Ollama tem um piso de ~850 ms** que não é geração: medido pelo
`load_duration` da própria API, com o modelo residente (`ollama ps` confirma), contra
prompt_eval de 25 ms e eval de 25 ms. Não é VRAM (some com a placa em 6 GB/8 GB), não é
clock (2782 MHz), não muda com `keep_alive=30m` nem com os parâmetros da requisição.

**Mas ele paraleliza:** duas chamadas simultâneas terminam juntas em ~1,0 s; em
sequência custam 1,88 s. Como o desenho hoje é estritamente serial
(roteador → depois agente), o piso é pago **duas vezes**. Sobrepor as duas é o maior
ganho de latência disponível — e ainda não foi feito.

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
