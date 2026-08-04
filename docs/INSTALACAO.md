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
- Auto-start: opção **"Iniciar com o Windows"** na engrenagem do app (o app sobe o
  resto). Log em `server/data/jarvis.log`.

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
Build release assinado. O keystore (`apps/android/jarvis-release.keystore`) e a senha
**não** vão pro repositório — a senha fica em `config/.env` como `KEYSTORE_PASSWORD`
ou você digita na hora. Sem eles dá pra gerar um debug normalmente.

```
cd apps\android
.\gradlew.bat assembleRelease
```

APKs prontos ficam em `releases/Jarvis.apk` e `releases/Jarvis-Watch.apk`.

## Desktop (PC de bandeja)

### Gerar o instalador

```
gerar_exe.bat            usa a versão que está no package.json
gerar_exe.bat 0.2.0      grava essa versão antes de gerar
```

Dois cliques resolvem. O script faz a cadeia inteira: instala o que faltar
(interface e app), builda a interface, copia ela pra dentro do app (`sync-web`)
e roda o electron-builder. No fim deixa o arquivo pronto em
`releases\JARVIS-Desktop-Setup.exe` (~78 MB) e diz o caminho na tela.

Se der erro, ele para na hora e mostra qual etapa quebrou — não segue gerando
um .exe pela metade. A primeira execução demora bem mais (baixa o Electron,
~200 MB).

### Detalhes

`apps/desktop` (Electron). Dev: `npm install && npm start` (usa o token do
`config/devices.yml` do repo). Por baixo do `gerar_exe.bat`, o passo do
instalador é `npm run dist` → `dist/JARVIS Setup <versão>.exe`
(cópia em `releases/JARVIS-Desktop-Setup.exe`). Instala em
`%LOCALAPPDATA%\Programs\jarvis-desktop\`, registra auto-start no logon e guarda a config em
`%APPDATA%\JARVIS\config.json` (host/device/token/projeto — a pasta usa o `productName`).

**O app é o supervisor do JARVIS, não só a janela dele.** Ao abrir, ele confere as
portas 11434 (Ollama), 8040 (servidor) e 8041 (voz) e sobe o que estiver faltando;
depois repete a checagem a cada 30 s. Como ele entra sozinho na inicialização do
Windows, ligar o PC (ou abrir o exe) liga o JARVIS inteiro. O menu da bandeja mostra
o estado dos três e tem "Verificar agora".

Para isso ele precisa saber onde está o repositório. A raiz é gravada no pacote
(`build/projeto.json`, escrito pelo `sync-web`) e pode ser trocada pelo campo
`projeto` do `config.json` ou pela variável `JARVIS_HOME`. **O token vem sempre do
`devices.yml`** dessa raiz, a cada início — antes a cópia local só era preenchida
quando estava vazia, então uma rotação de token deixava o app tentando entrar com o
antigo e apanhando `4401` sem nenhuma pista do motivo.
Uso: ícone fica oculto na bandeja; falar "Jarvis" abre a janela do reator.
A janela é **arrastável por qualquer ponto vazio** (não tem barra de título) e
**lembra onde você deixou** (posição em `config.json`, com checagem de monitor pra
não abrir fora da tela). O **X** no canto superior direito recolhe pra bandeja — o
JARVIS continua ouvindo. ESC e o clique na bandeja também escondem; o menu da
bandeja tem "Iniciar com o Windows" e "Sair" (esse sim encerra).
A janela nunca some sozinha enquanto está ouvindo, pensando, executando ou falando.

**Transparência**: quando você clica em outra janela, ela fica bem translúcida
(opacidade 0,28) pra não atrapalhar a leitura do que está atrás; ao clicar nela volta
a ficar opaca. Se o JARVIS estiver te respondendo, ela sobe pra 0,92 mesmo sem foco —
senão você não conseguiria ler a resposta. Os valores estão em `OPACIDADE`, no
`apps/desktop/main.js`.
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

**Uma camada só, e quem liga é você:** a opção **"Iniciar com o Windows"**, na
engrenagem da janela (o menu da bandeja tem a mesma). Marcada, ela registra o app
no login do Windows; o app abre junto com o PC e **sobe Ollama, servidor e voz**,
revisando a cada 30 s. Desmarcada, nada do JARVIS entra no boot.

A escolha fica em `iniciarComWindows`, no `config.json` do app, e é aplicada com
`app.setLoginItemSettings`. Nem o instalador nem o app ligam isso por conta
própria.

> **Antes eram quatro mecanismos ao mesmo tempo** — as tarefas agendadas "JARVIS
> Server" e "JARVIS Watchdog", a chave `Run` e um atalho na pasta Inicializar. As
> tarefas guardavam **caminho absoluto**: quando o projeto saiu de
> `~\Documents\GitHub\JARVIS`, a "JARVIS Server" passou a chamar um `.vbs` que não
> existia e o `wscript` abria uma **caixa de erro em todo boot**. Pior, o app
> regravava `openAtLogin: true` a cada início, então desmarcar não colava.
> Tudo isso foi removido em 04/08/2026 e trocado por esta opção única.

O `server/watchdog.ps1` continua no repositório, mas **nada o agenda**: virou
ferramenta manual, para reerguer os serviços sem passar pelo app.

> Armadilha: não crie essas tarefas com `schtasks /TR "...\arquivo.vbs"`. A barra
> invertida antes da aspa final escapa a aspa, e o caminho engole o `/RL LIMITED`
> virando um argumento só. Foi assim que as duas quebraram. O script usa
> `Register-ScheduledTask`, que recebe o caminho como argumento.

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
