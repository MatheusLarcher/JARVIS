// JARVIS desktop: fica só como ícone na bandeja; a janela com o reator aparece
// quando o wake word dispara e some quando volta ao repouso.
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage } = require('electron')
const fs = require('fs')
const path = require('path')

const DEVICE_ID = 'pc-matheus'
const DEFAULT_HOST = '127.0.0.1:8040'

let win = null
let tray = null
let hideTimer = null
let pinned = false // aberto manualmente pela bandeja → não esconde sozinho

if (!app.isPackaged) {
  // dev não briga com a instância instalada (userData separado)
  app.setPath('userData', path.join(require('os').tmpdir(), 'jarvis-desktop-dev'))
}
if (!app.requestSingleInstanceLock()) app.quit()

// log próprio: sem isto não dá pra saber por que o app não subiu no boot
let logFile = null
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`
  try {
    if (!logFile) logFile = path.join(app.getPath('userData'), 'desktop.log')
    fs.appendFileSync(logFile, line)
  } catch { }
  console.log(line.trim())
}
process.on('uncaughtException', (e) => log(`ERRO nao tratado: ${e && e.stack}`))
app.setAppUserModelId('com.larchertech.jarvis')

function readConfig() {
  // instalado: %APPDATA%/jarvis-desktop/config.json | dev: lê o devices.yml do repo
  const cfgPath = path.join(app.getPath('userData'), 'config.json')
  let cfg = { host: DEFAULT_HOST, device: DEVICE_ID, token: '' }
  try { cfg = { ...cfg, ...JSON.parse(fs.readFileSync(cfgPath, 'utf-8')) } } catch { }
  if (!cfg.token) {
    // dev: yml relativo ao repo; instalado: procura o projeto no lugar padrão
    const candidates = [
      path.join(__dirname, '..', '..', 'config', 'devices.yml'),
      path.join(app.getPath('home'), 'Documents', 'GitHub', 'JARVIS', 'config', 'devices.yml'),
    ]
    for (const p of candidates) {
      try {
        const devs = require('js-yaml').load(fs.readFileSync(p, 'utf-8')).devices
        if (devs[cfg.device]) { cfg.token = devs[cfg.device].token; break }
      } catch { }
    }
  }
  try { fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2)) } catch { }
  return cfg
}

function createWindow(cfg) {
  const { width } = screen.getPrimaryDisplay().workAreaSize
  win = new BrowserWindow({
    width: 460,
    height: 520,
    x: Math.round(width / 2 - 230),
    y: 120,
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

function showReactor() {
  clearTimeout(hideTimer)
  if (win && !win.isVisible()) win.showInactive() // sem roubar o foco do que você faz
}

function scheduleHide() {
  clearTimeout(hideTimer)
  if (pinned) return
  hideTimer = setTimeout(() => { if (win && !pinned) win.hide() }, 3000)
}

function buildTray(cfg) {
  tray = new Tray(nativeImage.createFromPath(path.join(__dirname, 'build', 'tray.png')))
  tray.setToolTip('JARVIS — dizer "Hey Jarvis" ou clicar pra falar')
  const menu = Menu.buildFromTemplate([
    {
      label: 'Mostrar Jarvis', click: () => {
        pinned = true
        clearTimeout(hideTimer)
        win.show()
      },
    },
    {
      label: 'Iniciar com o Windows', type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked }),
    },
    { type: 'separator' },
    { label: `Servidor: ${cfg.host}`, enabled: false },
    { type: 'separator' },
    { label: 'Sair', click: () => { win.destroy(); app.quit() } },
  ])
  tray.setContextMenu(menu)
  tray.on('click', () => {
    if (win.isVisible()) { pinned = false; win.hide() }
    else { pinned = true; win.show() }
  })
}

app.whenReady().then(() => {
  const cfg = readConfig()
  log(`iniciando (empacotado=${app.isPackaged}) servidor=${cfg.host} device=${cfg.device} token=${cfg.token ? 'ok' : 'AUSENTE'}`)
  // mic sem prompt (app confiável local)
  const ses = require('electron').session.defaultSession
  ses.setPermissionRequestHandler((_wc, permission, cb) => cb(permission === 'media'))
  createWindow(cfg)
  buildTray(cfg)
  if (app.isPackaged && process.argv.indexOf('--no-autostart') === -1) {
    app.setLoginItemSettings({ openAtLogin: true })
  }

  ipcMain.on('jarvis-wake', showReactor)
  ipcMain.on('jarvis-state', (_e, state) => {
    if (state === 'IDLE') { if (!pinned) scheduleHide() }
    else showReactor()
  })
  ipcMain.on('jarvis-pin', (_e, on) => {
    pinned = on
    if (on) { clearTimeout(hideTimer); if (!win.isVisible()) win.show() }
    else scheduleHide()
  })
  ipcMain.on('jarvis-quit', () => { win.destroy(); app.quit() })

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
