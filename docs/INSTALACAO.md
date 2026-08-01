# Instalação e operação

## Servidor (notebook Windows)

- Conda env: `jarvis` (Python 3.11). Recriar do zero:
  ```
  conda create -y -n jarvis python=3.11
  conda run -n jarvis pip install -r server/requirements.txt
  conda run -n jarvis pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128 --force-reinstall
  conda run -n jarvis pip install "nemo_toolkit[asr] @ git+https://github.com/NVIDIA/NeMo.git@main"
  conda run -n jarvis pip install torchcodec soundfile librosa
  ```
- Segredos em `config/.env` (gitignorado): `DEEPSEEK_API_KEY`, `HA_TOKEN`.
- Gerar/atualizar a biblioteca de áudios: `python server/scripts/build_library.py`.
- Rodar: `server\start_jarvis.bat` (loop watchdog) ou `python server/run.py`.
- Auto-start: tarefa agendada **"JARVIS Server"** (ONLOGON, roda `start_jarvis_hidden.vbs`).
  Log em `server/data/jarvis.log`.

## Portas

| Serviço | Porta |
|---|---|
| API + WebSocket + web | 8040 |
| Vite dev (opcional) | 8042 |

Libere a 8040 no firewall do Windows pra rede privada se os aparelhos não conectarem.

## Web

`apps/web`: `npm install && npm run build` → o servidor serve `dist/` na raiz.
Dev: `npm run dev` (proxy pro 8040).

## Android / Wear

Projeto Gradle em `apps/android` (módulos `:app` e `:wear`).
Build release assinado (keystore `apps/android/jarvis-release.keystore`, senha `jarvis2026`):

```
cd apps\android
.\gradlew.bat assembleRelease
```

APKs prontos ficam em `releases/Jarvis.apk` e `releases/Jarvis-Watch.apk`.

## Desktop (PC de bandeja)

`apps/desktop` (Electron). Dev: `npm install && npm start` (usa o token do
`config/devices.yml` do repo). Instalador: `npm run dist` → `dist/JARVIS Setup 0.1.0.exe`
(cópia em `releases/JARVIS-Desktop-Setup.exe`). Instala em
`%LOCALAPPDATA%\Programs\jarvis-desktop\`, registra auto-start no logon e guarda a config em
`%APPDATA%\jarvis-desktop\config.json` (host/device/token — o token é preenchido sozinho a
partir do `devices.yml` se o projeto estiver em `~\Documents\GitHub\JARVIS`).
Uso: ícone fica oculto na bandeja; "Hey Jarvis" abre a janela do reator; ESC ou clique na
bandeja esconde; menu da bandeja tem "Iniciar com o Windows" e "Sair".
Engrenagem (canto superior esquerdo da janela) abre as configurações: escolher um ou
VÁRIOS microfones (todos capturam juntos — as fontes são somadas num único stream),
dispositivo de saída (`AudioContext.setSinkId`) e o botão "Fechar o JARVIS".
Preferências ficam no localStorage da UI (`jarvis_audio`).

## "O JARVIS não me ouve" — como diagnosticar

Ordem de checagem (do mais comum pro mais raro):

1. **O áudio está chegando no servidor?**
   ```
   curl http://127.0.0.1:8040/api/audio/debug
   ```
   - `rms_maximo` perto de 0 → **microfone mudo**. Foi o caso do headset Astro A50
     na base: o Windows mantém ele como microfone PADRÃO e ele não capta nada.
     O app troca sozinho depois de 15s sem sinal, mas dá pra escolher na engrenagem.
   - `vad_maximo` acima de 0.5 → o servidor reconhece como fala. Se chega som mas o
     VAD não sobe, o volume está baixo demais.
2. **Qual microfone o app está usando?** `python tests/diag_app_mic.py`
   (precisa do app com `--remote-debugging-port=9333`).
3. **Qual microfone escuta a sala?** `python tests/diag_microfones.py` mede todos.
4. **Teste ponta a ponta pelo microfone real:** `python tests/test_mic_real.py`.
5. **O que ele entendeu?** `server/data/jarvis.log` mostra `fala: '...'` de cada
   captura. Se aparecer o texto mas não reagir, o nome não foi reconhecido —
   veja `wake_word` em `config/settings.yml`.

## Se não subir sozinho ao ligar o PC

Três camadas, nessa ordem:

| Camada | O quê |
|---|---|
| Tarefa **JARVIS Server** (ONLOGON) | roda `start_jarvis.bat`, que abre o servidor e o serviço de voz, cada um com loop de reinício |
| Chave `Run` do usuário | abre o app da bandeja (`JARVIS.exe`) |
| Tarefa **JARVIS Watchdog** (a cada 5 min) | confere os três e religa o que estiver fora; log em `server/data/watchdog.log` |

Os `.bat` definem `FOR_DISABLE_CONSOLE_CTRL_HANDLER=1`: sem isso a runtime Fortran
que vem dentro do numpy/scipy **mata o processo** quando o console recebe evento de
fechar/logoff (`forrtl: error (200): program aborting due to window-CLOSE event`) —
era o erro que aparecia ao ligar a máquina.

## Testes

```
conda run -n jarvis python tests/test_intents.py     # unit: intents + skills (sem servidor)
conda run -n jarvis python tests/test_ws_flow.py     # gateway (servidor no ar)
conda run -n jarvis python tests/test_audio_e2e.py   # MVP completo por áudio sintético
```

## Acesso externo (futuro)

Cloudflare Tunnel → `jarvis.larchertech.com` apontando pra 8040. Os apps têm o host
configurável, então basta trocar o campo Servidor; a LAN continua tendo prioridade
(usar o IP local quando em casa).
