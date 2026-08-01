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

## Configurações que dependem do usuário

- URL + token do Home Assistant; entity_id reais das luzes e do sensor de temperatura.
- IP fixo/reserva DHCP do notebook na LAN (os apps apontam pra ele).
