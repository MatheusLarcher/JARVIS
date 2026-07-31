const { contextBridge, ipcRenderer } = require('electron')

// ponte mínima: a UI web avisa o main quando acordar / mudar de estado
contextBridge.exposeInMainWorld('jarvisDesktop', {
  wake: () => ipcRenderer.send('jarvis-wake'),
  state: (s) => ipcRenderer.send('jarvis-state', s),
  pin: (on) => ipcRenderer.send('jarvis-pin', !!on),   // modal aberto → não esconder
  quit: () => ipcRenderer.send('jarvis-quit'),
})
