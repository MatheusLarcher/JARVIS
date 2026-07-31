// Captura do microfone → PCM int16 16kHz em frames de 80ms (1280 amostras).
// Usa AudioWorklet com downsample linear da taxa do contexto pra 16k.

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

export async function startMic(onFrame, onLevel) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  })
  const ctx = new AudioContext()
  await ctx.resume()
  const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
  await ctx.audioWorklet.addModule(url)
  const src = ctx.createMediaStreamSource(stream)
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
  src.connect(node)
  return { ctx, stop: () => { stream.getTracks().forEach(t => t.stop()); ctx.close() } }
}

// Player: acks pré-carregados em memória + áudios de resposta por URL.
export function createPlayer() {
  const ctx = new AudioContext()
  const acks = []

  async function preloadAcks(list) {
    acks.length = 0
    for (const a of list) {
      try {
        const buf = await (await fetch(a.url)).arrayBuffer()
        acks.push(await ctx.decodeAudioData(buf))
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

  return { preloadAcks, playAck, playUrl, resume: () => ctx.resume() }
}
