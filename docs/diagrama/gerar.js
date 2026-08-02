// Rasteriza docs/diagrama/diagrama.html em docs/diagrama.png.
//
// Roda pelo Electron que já vem com o app de bandeja:
//     apps/desktop/node_modules/.bin/electron docs/diagrama
// (o gerar.py chama isso pra você)
//
// Por que Electron e não Chrome headless: nesta máquina o `--screenshot` do
// Chrome sai sem gerar nada e sem erro, e a porta de debug (--remote-debugging-
// port) nunca abre — nem com perfil novo. capturePage() do Electron é
// direto e não depende de porta nenhuma.
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const path = require('path')

const LARGURA = 1680
const ALTURA = 812
const ESCALA = 2                       // 2x = legível em tela grande
const HTML = path.join(__dirname, 'diagrama.html')
const SAIDA = path.join(__dirname, '..', 'diagrama.png')

app.disableHardwareAcceleration()

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: LARGURA, height: ALTURA, show: false,
    useContentSize: true,
    webPreferences: { offscreen: true, backgroundThrottling: false },
  })
  await win.loadFile(HTML)
  // deixa fonte, gradiente e emoji assentarem antes de capturar
  await new Promise(r => setTimeout(r, 1200))

  // capturePage() sozinho devolve o tamanho da JANELA, que o Windows limita
  // ao tamanho da tela (saía 1920 de largura em vez de 3360). Pelo debugger
  // dá pra fixar as medidas e a escala, independente do monitor.
  const dbg = win.webContents.debugger
  dbg.attach('1.3')
  await dbg.sendCommand('Emulation.setDeviceMetricsOverride', {
    width: LARGURA, height: ALTURA, deviceScaleFactor: ESCALA, mobile: false,
  })
  await new Promise(r => setTimeout(r, 400))
  const { data } = await dbg.sendCommand('Page.captureScreenshot', {
    format: 'png', captureBeyondViewport: true,
  })
  dbg.detach()

  const png = Buffer.from(data, 'base64')
  fs.writeFileSync(SAIDA, png)
  console.log(`${SAIDA}  (${Math.round(png.length / 1024)} KB, ` +
              `${LARGURA * ESCALA}x${ALTURA * ESCALA})`)
  win.destroy()
  app.quit()
}).catch(e => {
  console.error('falhou:', e.message)
  app.exit(1)
})
