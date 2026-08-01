const { contextBridge, ipcRenderer } = require('electron')

// Config injetada pelo main via argumento (--jarvis-config=<json em base64>).
// A interface é local, então ela precisa saber onde está o servidor.
function readConfig() {
  const arg = process.argv.find(a => a.startsWith('--jarvis-config='))
  if (!arg) return { desktop: true }
  try {
    return { desktop: true, ...JSON.parse(Buffer.from(arg.split('=')[1], 'base64').toString()) }
  } catch {
    return { desktop: true }
  }
}

contextBridge.exposeInMainWorld('jarvisDesktop', {
  config: readConfig(),
  wake: () => ipcRenderer.send('jarvis-wake'),
  state: (s) => ipcRenderer.send('jarvis-state', s),
  pin: (on) => ipcRenderer.send('jarvis-pin', !!on),   // modal aberto → não esconder
  quit: () => ipcRenderer.send('jarvis-quit'),
})
