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
- [ ] Testar wake word com a voz real do Matheus e calibrar threshold.
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
