// Captura do microfone → PCM int16 16kHz em frames de 80ms (1280 amostras).
// Aceita VÁRIOS microfones: cada um vira um MediaStreamSource ligado no mesmo
// AudioWorkletNode — o Web Audio soma as fontes num único sinal.

const WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buf = []
    this.acc = 0
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (!ch) return true
    const ratio = sampleRate / 16000
    for (let i = 0; i < ch.length; i++) {
      this.acc += 1
      if (this.acc >= ratio) {
        this.acc -= ratio
        const v = Math.max(-1, Math.min(1, ch[i]))
        this.buf.push(v < 0 ? v * 32768 : v * 32767)
        if (this.buf.length >= 1280) {
          this.port.postMessage(new Int16Array(this.buf))
          this.buf = []
        }
      }
    }
    return true
  }
}
registerProcessor('pcm-capture', PcmCapture)
`

// deviceIds: [] → microfone padrão; [id1, id2, ...] → todos misturados
export async function startMic(onFrame, onLevel, deviceIds = []) {
  const wanted = deviceIds.length ? deviceIds : [null]
  const streams = []
  for (const id of wanted) {
    try {
      streams.push(await navigator.mediaDevices.getUserMedia({
        audio: {
          ...(id ? { deviceId: { exact: id } } : {}),
          channelCount: 1, echoCancellation: true, noiseSuppression: true,
        },
      }))
    } catch { /* mic pode ter sido desplugado; segue com os outros */ }
  }
  if (!streams.length) throw new Error('nenhum microfone disponível')

  const ctx = new AudioContext()
  await ctx.resume()
  const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
  await ctx.audioWorklet.addModule(url)
  const node = new AudioWorkletNode(ctx, 'pcm-capture')
  node.port.onmessage = (e) => {
    const pcm = e.data
    if (onLevel) {
      let sum = 0
      for (let i = 0; i < pcm.length; i += 4) sum += Math.abs(pcm[i])
      onLevel(Math.min(1, (sum / (pcm.length / 4)) / 6000))
    }
    onFrame(pcm.buffer)
  }
  for (const s of streams) ctx.createMediaStreamSource(s).connect(node)
  return {
    ctx,
    labels: streams.map(s => s.getAudioTracks()[0]?.label || '?'),
    stop: () => {
      streams.forEach(s => s.getTracks().forEach(t => t.stop()))
      ctx.close()
    },
  }
}

// Player: acks pré-carregados em memória + áudios de resposta por URL.
// setOutput(sinkId) troca o dispositivo de saída (AudioContext.setSinkId).
export function createPlayer() {
  const ctx = new AudioContext()
  const acks = []

  async function setOutput(sinkId) {
    try {
      if (ctx.setSinkId) await ctx.setSinkId(sinkId || '')
    } catch { /* dispositivo sumiu → fica no padrão */ }
  }

  async function preloadAcks(list) {
    acks.length = 0
    for (const a of list) {
      try {
        const buf = await (await fetch(a.url)).arrayBuffer()
        acks.push(await ctx.decodeAudioData(buf))   // mp3 ou wav, o decoder resolve
      } catch { /* segue com os que carregarem */ }
    }
  }

  function playBuffer(audioBuf) {
    const src = ctx.createBufferSource()
    src.buffer = audioBuf
    src.connect(ctx.destination)
    src.start()
    return new Promise(res => { src.onended = res })
  }

  function playAck() {
    if (!acks.length) return Promise.resolve()
    ctx.resume()
    return playBuffer(acks[Math.floor(Math.random() * acks.length)])
  }

  async function playUrl(url) {
    ctx.resume()
    const buf = await (await fetch(url)).arrayBuffer()
    return playBuffer(await ctx.decodeAudioData(buf))
  }

  // Fila de pedaços: a resposta chega picada (o Jarvis fala enquanto o LLM
  // escreve) e precisa tocar na ordem, sem buracos nem sobreposição.
  const fila = { proximo: 0, pendentes: new Map(), tocando: false, onIdle: null }

  async function enqueue(seq, url) {
    if (!url) return
    ctx.resume()
    // baixa e decodifica em paralelo; a ORDEM é garantida na hora de tocar
    const p = fetch(url).then(r => r.arrayBuffer()).then(b => ctx.decodeAudioData(b))
    fila.pendentes.set(seq, p)
    drenar()
  }

  async function drenar() {
    if (fila.tocando) return
    fila.tocando = true
    try {
      while (fila.pendentes.has(fila.proximo)) {
        const p = fila.pendentes.get(fila.proximo)
        fila.pendentes.delete(fila.proximo)
        fila.proximo++
        try { await playBuffer(await p) } catch { /* pedaço falhou: segue */ }
      }
    } finally {
      fila.tocando = false
      if (!fila.pendentes.size && fila.onIdle) fila.onIdle()
    }
  }

  function resetQueue() {
    fila.proximo = 0
    fila.pendentes.clear()
  }

  return {
    preloadAcks, playAck, playUrl, setOutput, enqueue, resetQueue,
    setOnIdle: (f) => { fila.onIdle = f },
    falando: () => fila.tocando || fila.pendentes.size > 0,
    resume: () => ctx.resume(),
  }
}
