// JARVIS desktop: fica só como ícone na bandeja; a janela com o reator aparece
// quando o wake word dispara e some quando volta ao repouso.
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage } = require('electron')
const fs = require('fs')
const net = require('net')
const path = require('path')
const { spawn } = require('child_process')

const DEVICE_ID = 'pc-matheus'
const DEFAULT_HOST = '127.0.0.1:8040'
const PORTA_SERVIDOR = 8040
const PORTA_VOZ = 8041
const PORTA_OLLAMA = 11434

let win = null
let tray = null
let hideTimer = null
let pinned = false      // aberto manualmente pela bandeja → não esconde sozinho
let processando = false // ouvindo/pensando/executando
let falando = false     // ainda tocando a resposta

if (!app.isPackaged) {
  // dev não briga com a instância instalada (userData separado)
  app.setPath('userData', path.join(require('os').tmpdir(), 'jarvis-desktop-dev'))
}
if (!app.requestSingleInstanceLock()) app.quit()

// log próprio: sem isto não dá pra saber por que o app não subiu no boot
const LOG_MAX_BYTES = 5 * 1024 * 1024
let logFile = null

// Guarda a volta anterior e recomeça. Sem teto, o arquivo cresce pra sempre:
// aqui um laço de EPIPE (ver o comentário no log()) deixou 312 MB de stack
// trace no disco, e mesmo sem laço um log 24/7 nunca para de crescer.
function giraSePreciso(arquivo) {
  try {
    if (fs.statSync(arquivo).size < LOG_MAX_BYTES) return
    fs.rmSync(arquivo + '.old', { force: true })
    fs.renameSync(arquivo, arquivo + '.old')
  } catch { }
}

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`
  try {
    if (!logFile) {
      logFile = path.join(app.getPath('userData'), 'desktop.log')
      giraSePreciso(logFile)
    }
    fs.appendFileSync(logFile, line)
    // um laço de erro enche o arquivo dentro da MESMA execução, então não dá
    // pra conferir só no start
    if (Math.random() < 0.01) giraSePreciso(logFile)
  } catch { }
  // O console.log PRECISA estar protegido. Se o app foi aberto por um terminal
  // que fechou, escrever na saída dá EPIPE — e como o handler de exceção lá
  // embaixo chama este mesmo log(), virava laço: EPIPE -> log -> EPIPE, enchendo
  // o arquivo e derrubando a janela no meio do uso.
  try { console.log(line.trim()) } catch { }
}
process.on('uncaughtException', (e) => log(`ERRO nao tratado: ${e && e.stack}`))
app.setAppUserModelId('com.larchertech.jarvis')

// Onde está o repositório do JARVIS. O app instalado precisa dele para ler o
// token e para subir o servidor — sem isto ele é só uma casca.
// Ordem: o que já foi salvo > variável de ambiente > o caminho gravado no build
// (sync-web) > o repo relativo, que é o caso do dev.
// Sem caminho absoluto chutado aqui: o do build é o que vale, e chute vira
// caminho da máquina de outra pessoa dentro do repositório.
function achaProjeto(cfg) {
  let doBuild = null
  try {
    doBuild = JSON.parse(fs.readFileSync(path.join(__dirname, 'build', 'projeto.json'), 'utf-8')).raiz
  } catch { }
  const candidatos = [
    cfg && cfg.projeto,
    process.env.JARVIS_HOME,
    doBuild,
    path.join(__dirname, '..', '..'),
  ]
  for (const c of candidatos) {
    if (!c) continue
    try {
      if (fs.existsSync(path.join(c, 'server', 'start_jarvis.bat')) &&
          fs.existsSync(path.join(c, 'config', 'settings.yml'))) return path.resolve(c)
    } catch { }
  }
  return null
}

function tokenDoDevices(raiz, device) {
  try {
    const yml = path.join(raiz, 'config', 'devices.yml')
    const devs = require('js-yaml').load(fs.readFileSync(yml, 'utf-8')).devices
    return (devs[device] || {}).token || null
  } catch { return null }
}

function readConfig() {
  // instalado: %APPDATA%/JARVIS/config.json (o nome vem do productName)
  const cfgPath = path.join(app.getPath('userData'), 'config.json')
  let cfg = { host: DEFAULT_HOST, device: DEVICE_ID, token: '' }
  try { cfg = { ...cfg, ...JSON.parse(fs.readFileSync(cfgPath, 'utf-8')) } } catch { }

  const raiz = achaProjeto(cfg)
  if (raiz) {
    cfg.projeto = raiz
    // O devices.yml é a FONTE DA VERDADE do token, sempre — não só quando falta.
    // Antes a cópia daqui só era preenchida se estivesse vazia, então uma rotação
    // de token deixava o app tentando entrar com o antigo e o servidor recusando
    // com 4401, sem nada indicando o motivo.
    const tok = tokenDoDevices(raiz, cfg.device)
    if (tok && tok !== cfg.token) {
      log(`token de ${cfg.device} atualizado a partir do devices.yml`)
      cfg.token = tok
    }
  }
  salvaConfig(cfg)
  return cfg
}

function salvaConfig(cfg) {
  try {
    fs.writeFileSync(path.join(app.getPath('userData'), 'config.json'),
                     JSON.stringify(cfg, null, 2))
  } catch { }
}

// ---------------------------------------------------------------------------
// Iniciar com o Windows: UMA fonte de verdade, escolhida por você.
//
// Antes eram quatro mecanismos ao mesmo tempo — duas tarefas agendadas, a chave
// Run e um atalho na pasta Inicializar. A tarefa "JARVIS Server" guardava o
// caminho do projeto por extenso; quando a pasta mudou, ela passou a chamar um
// .vbs inexistente e o wscript abria um ERRO DE SCRIPT em todo boot.
//
// Agora existe só o login item do app. Ligar o JARVIS é abrir o app, e o app
// sobe servidor, voz e Ollama (ver garanteServicos).
// ---------------------------------------------------------------------------
function autostartLigado(cfg) {
  // sem escolha salva, vale o que o Windows já tem registrado
  if (typeof cfg.iniciarComWindows === 'boolean') return cfg.iniciarComWindows
  return app.getLoginItemSettings().openAtLogin
}

function aplicaAutostart(ligar) {
  try {
    app.setLoginItemSettings({ openAtLogin: !!ligar })
  } catch (e) {
    log(`nao consegui mudar o iniciar-com-o-Windows: ${e && e.message}`)
  }
  return app.getLoginItemSettings().openAtLogin
}

function defineAutostart(cfg, ligar) {
  cfg.iniciarComWindows = !!ligar
  salvaConfig(cfg)
  const real = aplicaAutostart(ligar)
  log(`iniciar com o Windows: ${real ? 'ligado' : 'desligado'}`)
  return real
}

// ---------------------------------------------------------------------------
// Serviços: o app da bandeja é quem garante que o JARVIS inteiro esteja no ar.
// Ele já entra na inicialização do Windows, então abrir o app = ligar tudo.
// ---------------------------------------------------------------------------
function portaAberta(porta, timeout = 800) {
  return new Promise((resolve) => {
    const s = new net.Socket()
    let pronto = false
    const fim = (ok) => { if (!pronto) { pronto = true; s.destroy(); resolve(ok) } }
    s.setTimeout(timeout)
    s.once('connect', () => fim(true))
    s.once('timeout', () => fim(false))
    s.once('error', () => fim(false))
    s.connect(porta, '127.0.0.1')
  })
}

function roda(cmd, args) {
  try {
    const p = spawn(cmd, args, { detached: true, stdio: 'ignore', windowsHide: true })
    p.unref()
    return true
  } catch (e) {
    log(`nao consegui rodar ${cmd}: ${e && e.message}`)
    return false
  }
}

function ollamaExe() {
  const local = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Ollama', 'ollama.exe')
  return fs.existsSync(local) ? local : 'ollama'
}

// carrega os modelos: dar tempo antes de tentar subir de novo
const ESPERA_SUBIDA_MS = 120000
const subindo = {}

function jaSubindo(chave) {
  const agora = Date.now()
  if (subindo[chave] && agora - subindo[chave] < ESPERA_SUBIDA_MS) return true
  subindo[chave] = agora
  return false
}

async function garanteServicos(cfg) {
  const raiz = cfg.projeto
  const estado = {
    ollama: await portaAberta(PORTA_OLLAMA),
    servidor: await portaAberta(PORTA_SERVIDOR),
    voz: await portaAberta(PORTA_VOZ),
  }
  if (!raiz) {
    // sem o cooldown isto escreveria no log a cada 30s, pra sempre
    if (!estado.servidor && !jaSubindo('sem-projeto')) {
      log('servidor fora do ar e nao achei o projeto (defina JARVIS_HOME ou o ' +
          'campo "projeto" no config.json) — nao da pra subir sozinho')
    }
    return estado
  }

  if (!estado.ollama && !jaSubindo('ollama')) {
    log('Ollama fora do ar; subindo')
    roda(ollamaExe(), ['serve'])
  }
  if (!estado.servidor && !jaSubindo('servidor')) {
    log('servidor fora do ar; subindo (leva ~1min carregando os modelos)')
    roda('wscript.exe', [path.join(raiz, 'server', 'start_jarvis_hidden.vbs')])
    // O start_jarvis.bat sobe a VOZ junto. Sem marcar isso aqui, a revisão de
    // 30s depois via o servidor no ar e a 8041 ainda fechada (o modelo demora a
    // carregar) e subia uma SEGUNDA cópia da voz. A perdedora da porta morria,
    // o `:loop` do .bat a reerguia, e um `timeout /t 5 /nobreak` piscava na tela
    // a cada 5 segundos, pra sempre.
    jaSubindo('voz')
  } else if (estado.servidor && !estado.voz && !jaSubindo('voz')) {
    log('servico de voz fora do ar; subindo')
    roda('wscript.exe', [path.join(raiz, 'server', 'start_voice_hidden.vbs')])
  }
  return estado
}

function posicaoInicial(cfg) {
  const { width } = screen.getPrimaryDisplay().workAreaSize
  const padrao = { x: Math.round(width / 2 - 230), y: 120 }
  const salva = cfg.janela
  if (!salva || typeof salva.x !== 'number') return padrao
  // se o monitor mudou, a posição salva pode ter ficado fora da tela
  const cabe = screen.getAllDisplays().some(d =>
    salva.x + 200 > d.bounds.x && salva.x + 260 < d.bounds.x + d.bounds.width &&
    salva.y + 60 > d.bounds.y && salva.y + 60 < d.bounds.y + d.bounds.height)
  return cabe ? salva : padrao
}

function createWindow(cfg) {
  const pos = posicaoInicial(cfg)
  win = new BrowserWindow({
    width: 460,
    height: 520,
    x: pos.x,
    y: pos.y,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      backgroundThrottling: false, // mic continua ouvindo com a janela escondida
      // a config vai pro preload por argumento (a página é local)
      additionalArguments: [
        '--jarvis-config=' + Buffer.from(JSON.stringify(cfg)).toString('base64'),
      ],
    },
  })
  win.setAlwaysOnTop(true, 'screen-saver')

  // Interface EMPACOTADA no app: abre na hora, mesmo com o servidor ainda
  // subindo (ele demora ~1min carregando os modelos). O WebSocket reconecta
  // sozinho quando o servidor ficar pronto.
  const page = path.join(__dirname, 'build', 'web', 'index.html')
  if (fs.existsSync(page)) {
    win.loadFile(page)
  } else {
    win.loadURL(`http://${cfg.host}/?desktop=1&device=${cfg.device}&token=${encodeURIComponent(cfg.token)}`)
  }

  win.on('close', (e) => { e.preventDefault(); win.hide() })

  // clicou fora → fica translúcida; clicou nela → volta ao normal
  win.on('blur', () => aplicaOpacidade())
  win.on('focus', () => aplicaOpacidade())
  win.on('show', () => aplicaOpacidade(false))

  // guarda onde você deixou a janela (senão ela volta pro centro toda vez)
  let salvarTimer = null
  win.on('moved', () => {
    clearTimeout(salvarTimer)
    salvarTimer = setTimeout(() => {
      const [x, y] = win.getPosition()
      salvaConfig({ ...cfg, janela: { x, y } })
    }, 600)
  })
  win.webContents.on('before-input-event', (_e, input) => {
    if (input.key === 'Escape') win.hide()
  })
  let reloadTimer = null
  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    log(`falha ao carregar (${code} ${desc}); tentando de novo`)
    clearTimeout(reloadTimer)
    reloadTimer = setTimeout(() => {
      if (fs.existsSync(page)) win.loadFile(page)
      else if (url) win.loadURL(url)
    }, 3000)
  })
  win.webContents.on('render-process-gone', (_e, details) => {
    log(`renderer morreu (${details.reason}); recarregando`)
    setTimeout(() => win.reload(), 1000)
  })
}

function ocupado() {
  return pinned || processando || falando
}

// ---- transparência: sai da frente quando você está usando outra coisa ----
const OPACIDADE = {
  focado: 1.0,      // você clicou nele
  atendendo: 0.92,  // sem foco, mas está te respondendo
  parado: 0.28,     // sem foco e ocioso: dá pra ler o que está atrás
}
let fadeTimer = null

function opacidadeAlvo() {
  if (!win) return 1
  if (win.isFocused()) return OPACIDADE.focado
  if (processando || falando) return OPACIDADE.atendendo
  return OPACIDADE.parado
}

function aplicaOpacidade(suave = true) {
  if (!win) return
  clearInterval(fadeTimer)
  const alvo = opacidadeAlvo()
  if (!suave) { win.setOpacity(alvo); return }
  // transição curta pra não "piscar" na tela
  fadeTimer = setInterval(() => {
    if (!win || win.isDestroyed()) return clearInterval(fadeTimer)
    const atual = win.getOpacity()
    const passo = 0.08
    if (Math.abs(alvo - atual) <= passo) {
      win.setOpacity(alvo)
      clearInterval(fadeTimer)
    } else {
      win.setOpacity(atual + Math.sign(alvo - atual) * passo)
    }
  }, 16)
}

function showReactor() {
  clearTimeout(hideTimer)
  if (win && !win.isVisible()) win.showInactive() // sem roubar o foco do que você faz
  aplicaOpacidade()
}

// Só some quando REALMENTE terminou: enquanto estiver ouvindo, pensando,
// executando ou falando a resposta, a janela fica na tela.
function scheduleHide() {
  clearTimeout(hideTimer)
  if (ocupado()) return
  hideTimer = setTimeout(() => {
    if (win && !ocupado()) win.hide()
  }, 3000)
}

// estado dos serviços mostrado na bandeja (sem isto, servidor fora do ar é
// indistinguível de "ninguém falou com ele")
let estadoServicos = { ollama: false, servidor: false, voz: false }

function atualizaMenu(cfg) {
  if (!tray) return
  const marca = (ok) => (ok ? 'no ar' : 'fora do ar')
  const tudo = estadoServicos.servidor && estadoServicos.voz && estadoServicos.ollama
  tray.setToolTip(tudo
    ? 'JARVIS — dizer "Jarvis" ou clicar pra falar'
    : 'JARVIS — subindo os serviços...')
  tray.setContextMenu(Menu.buildFromTemplate([
    {
      label: 'Mostrar Jarvis', click: () => {
        pinned = true
        clearTimeout(hideTimer)
        win.show()
      },
    },
    {
      label: 'Iniciar com o Windows', type: 'checkbox',
      checked: autostartLigado(cfg),
      // a mesma opção da engrenagem: as duas gravam no config.json
      click: (item) => { defineAutostart(cfg, item.checked); atualizaMenu(cfg) },
    },
    { type: 'separator' },
    { label: `Servidor (${cfg.host}): ${marca(estadoServicos.servidor)}`, enabled: false },
    { label: `Voz: ${marca(estadoServicos.voz)}`, enabled: false },
    { label: `Ollama: ${marca(estadoServicos.ollama)}`, enabled: false },
    {
      label: 'Verificar agora',
      click: async () => { estadoServicos = await garanteServicos(cfg); atualizaMenu(cfg) },
    },
    { type: 'separator' },
    { label: 'Sair', click: () => { win.destroy(); app.quit() } },
  ]))
}

function buildTray(cfg) {
  tray = new Tray(nativeImage.createFromPath(path.join(__dirname, 'build', 'tray.png')))
  atualizaMenu(cfg)
  tray.on('click', () => {
    if (win.isVisible()) { pinned = false; win.hide() }
    else { pinned = true; win.show() }
  })
}

app.whenReady().then(() => {
  const cfg = readConfig()
  log(`iniciando (empacotado=${app.isPackaged}) servidor=${cfg.host} device=${cfg.device} ` +
      `token=${cfg.token ? 'ok' : 'AUSENTE'} projeto=${cfg.projeto || 'NAO ACHEI'}`)
  // mic sem prompt (app confiável local)
  const ses = require('electron').session.defaultSession
  ses.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === 'media'))
  createWindow(cfg)
  buildTray(cfg)
  // NÃO forçar mais o auto-start aqui. Antes isto religava `openAtLogin: true`
  // a cada início, então desmarcar a opção não colava: bastava reabrir o app pra
  // ela voltar sozinha. Agora quem manda é a escolha do usuário, guardada no
  // config.json e aplicada por aplicaAutostart().
  aplicaAutostart(autostartLigado(cfg))

  // sobe o que estiver faltando e continua vigiando: o app é o supervisor do
  // JARVIS, não só a janela dele
  const vigia = async () => {
    estadoServicos = await garanteServicos(cfg)
    atualizaMenu(cfg)
  }
  vigia()
  setInterval(vigia, 30000)

  ipcMain.on('jarvis-wake', () => { processando = true; showReactor() })
  ipcMain.on('jarvis-state', (_e, state) => {
    if (state === 'IDLE') {
      processando = false
      scheduleHide()         // só esconde se também não estiver falando
      aplicaOpacidade()      // terminou: pode ficar translúcida de novo
    } else {
      processando = true     // LISTENING/THINKING/EXECUTING/DONE/ERROR
      showReactor()
    }
  })
  // enquanto está falando a resposta, segura a janela na tela
  ipcMain.on('jarvis-speaking', (_e, on) => {
    falando = !!on
    if (on) showReactor()
    else { scheduleHide(); aplicaOpacidade() }
  })
  ipcMain.on('jarvis-pin', (_e, on) => {
    pinned = on
    if (on) { clearTimeout(hideTimer); if (!win.isVisible()) win.show() }
    else scheduleHide()
  })
  ipcMain.on('jarvis-hide', () => {
    // fechar aqui = recolher pra bandeja (o JARVIS continua ouvindo)
    pinned = false
    clearTimeout(hideTimer)
    if (win) win.hide()
  })
  ipcMain.on('jarvis-quit', () => { win.destroy(); app.quit() })
  // opção "Iniciar com o Windows" da engrenagem
  ipcMain.handle('jarvis-autostart-get', () => autostartLigado(cfg))
  ipcMain.handle('jarvis-autostart-set', (_e, ligar) => {
    const real = defineAutostart(cfg, ligar)
    atualizaMenu(cfg)          // mantém a bandeja igual à engrenagem
    return real
  })
  ipcMain.handle('jarvis-is-visible', () => !!win && win.isVisible())
  ipcMain.on('jarvis-focus', () => { if (win) win.focus() })
  ipcMain.handle('jarvis-window-info', () => ({
    visivel: !!win && win.isVisible(),
    focada: !!win && win.isFocused(),
    opacidade: win ? Math.round(win.getOpacity() * 100) / 100 : null,
    processando, falando, pinned,
  }))

  // validação (debug): JARVIS_DEBUG_SHOT=arquivo.png captura a janela no wake;
  // com JARVIS_DEBUG_SHOW=1 mostra e captura logo após carregar
  if (process.env.JARVIS_DEBUG_SHOT) {
    const shot = (delay) => setTimeout(async () => {
      const img = await win.webContents.capturePage()
      fs.writeFileSync(process.env.JARVIS_DEBUG_SHOT, img.toPNG())
    }, delay)
    ipcMain.on('jarvis-wake', () => shot(1200))
    if (process.env.JARVIS_DEBUG_SHOW) {
      win.webContents.on('did-finish-load', () => { win.showInactive(); shot(2500) })
    }
  }
  // JARVIS_DEBUG_QUIT=1: abre o modal e aciona o botão de fechar (valida preload+IPC)
  if (process.env.JARVIS_DEBUG_QUIT) {
    win.webContents.on('did-finish-load', () => {
      setTimeout(() => win.webContents.executeJavaScript(
        'document.querySelector(".gear")?.click(); ' +
        'setTimeout(() => document.querySelector(".btn.danger")?.click(), 800)'), 4000)
    })
  }
})

app.on('window-all-closed', () => { /* vive na bandeja */ })
