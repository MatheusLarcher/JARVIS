import React, { useEffect, useRef, useState } from 'react'
import { createPlayer, startMic } from './audio.js'
import { createReactor } from './reactor.js'

const params = new URLSearchParams(location.search)
// No app de bandeja a interface é local (file://) e o main process informa a
// configuração — assim a janela abre mesmo com o servidor ainda subindo.
const CFG = window.jarvisDesktop?.config || {}
const DESKTOP = CFG.desktop === true || params.get('desktop') === '1'
const DEVICE_ID = CFG.device || params.get('device') || localStorage.getItem('jarvis_device') || 'web-dev'
const TOKEN = CFG.token || params.get('token') || localStorage.getItem('jarvis_token') || 'tk_web_3Za5Xb7Vc9Td1Rf4Pg6Nh8Lj2'
// servidor: no navegador é a própria origem; no desktop vem da config
const SERVER = CFG.host || location.host
const HTTP = `http://${SERVER}`
const WS = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${SERVER}`

const loadAudioPrefs = () => {
  try { return JSON.parse(localStorage.getItem('jarvis_audio') || '{}') } catch { return {} }
}

// Abaixo disto o microfone está morto (headset na base, mudo no hardware).
// Sala silenciosa ainda passa bem deste valor; mic mudo fica no chão da escala.
const MIC_ALIVE_LEVEL = 0.006
const MIC_DEAD_AFTER_MS = 15000

export default function App() {
  const canvasRef = useRef(null)
  const reactorRef = useRef(null)
  const wsRef = useRef(null)
  const playerRef = useRef(null)
  const micRef = useRef(null)
  const [started, setStarted] = useState(false)
  const [online, setOnline] = useState(false)
  const [state, setState] = useState('IDLE')
  const [clock, setClock] = useState('')
  const [date, setDate] = useState('')
  const [temp, setTemp] = useState(null)
  const [heard, setHeard] = useState('')
  const [answer, setAnswer] = useState('')
  const [drift, setDrift] = useState([0, 0])
  const [showConfig, setShowConfig] = useState(false)
  const [devices, setDevices] = useState({ mics: [], outs: [] })
  const [prefs, setPrefs] = useState(loadAudioPrefs)   // { mics: [ids], output: id }
  const [micWarn, setMicWarn] = useState('')
  // vigia do microfone: headset na base/desligado fica MUDO e o Jarvis fica surdo
  const micWatch = useRef({ lastSignal: Date.now(), tried: [], current: null })

  // relógio + drift anti burn-in
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }))
      setDate(now.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' }))
    }
    tick()
    const t1 = setInterval(tick, 5000)
    const t2 = setInterval(() =>
      setDrift([(Math.random() - 0.5) * 16, (Math.random() - 0.5) * 10]), 60000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [])

  useEffect(() => {
    reactorRef.current = createReactor(canvasRef.current)
    return () => reactorRef.current?.destroy()
  }, [])

  useEffect(() => { reactorRef.current?.setState(state) }, [state])

  useEffect(() => { if (DESKTOP) begin() }, [])   // Electron: sem gesto do usuário

  async function refreshDevices() {
    const all = await navigator.mediaDevices.enumerateDevices()
    setDevices({
      mics: all.filter(d => d.kind === 'audioinput' && d.deviceId !== 'default' && d.deviceId !== 'communications'),
      outs: all.filter(d => d.kind === 'audiooutput' && d.deviceId !== 'communications'),
    })
  }

  async function startCapture(micIds) {
    micRef.current?.stop()
    micRef.current = null
    const w = micWatch.current
    w.lastSignal = Date.now()
    w.current = (micIds && micIds[0]) || null
    w.peak = 0
    w.frames = 0
    try {
      micRef.current = await startMic(
        (frame) => {
          if (wsRef.current?.readyState === 1) wsRef.current.send(frame)
          w.frames++
        },
        (lvl) => {
          reactorRef.current?.setLevel(lvl)
          w.peak = Math.max(w.peak, lvl)
          // ruído ambiente real sempre passa disto; microfone morto fica abaixo
          if (lvl > MIC_ALIVE_LEVEL) {
            w.lastSignal = Date.now()
            setMicWarn('')
          }
        },
        micIds || [],
      )
      w.label = micRef.current?.labels?.join(' + ') || 'padrão do sistema'
    } catch (e) {
      w.error = String(e)
      setAnswer('Sem acesso ao microfone')
    }
  }

  // janela de diagnóstico (usada pelos testes): window.__jarvisDiag()
  useEffect(() => {
    window.__jarvisDiag = () => ({
      ...micWatch.current,
      semSinalHa: Math.round((Date.now() - micWatch.current.lastSignal) / 1000),
      online, state, prefs,
    })
  })

  // Se o microfone ficar sem NENHUM sinal, troca sozinho pelo próximo da lista.
  useEffect(() => {
    if (!started) return
    const timer = setInterval(async () => {
      const w = micWatch.current
      if (Date.now() - w.lastSignal < MIC_DEAD_AFTER_MS) return

      const all = (await navigator.mediaDevices.enumerateDevices())
        .filter(d => d.kind === 'audioinput'
          && d.deviceId !== 'default' && d.deviceId !== 'communications')
      if (all.length < 2) return

      w.tried.push(w.current)
      const next = all.find(d => !w.tried.includes(d.deviceId))
        || all.find(d => d.deviceId !== w.current)
      if (!next) { w.tried = []; return }

      console.warn('microfone sem sinal; trocando para', next.label)
      setMicWarn(`microfone sem sinal — usando ${next.label}`)
      const p = { ...prefs, mics: [next.deviceId] }
      setPrefs(p)
      localStorage.setItem('jarvis_audio', JSON.stringify(p))
      await startCapture([next.deviceId])
    }, 5000)
    return () => clearInterval(timer)
  }, [started, prefs])

  async function begin() {
    setStarted(true)
    playerRef.current = createPlayer()
    if (prefs.output) playerRef.current.setOutput(prefs.output)
    connect()
    await startCapture(prefs.mics)
    refreshDevices()
  }

  function savePrefs(next) {
    setPrefs(next)
    localStorage.setItem('jarvis_audio', JSON.stringify(next))
    startCapture(next.mics)                    // reabre a captura com os mics escolhidos
    playerRef.current?.setOutput(next.output || '')
  }

  function connect() {
    const ws = new WebSocket(`${WS}/ws/${DEVICE_ID}?token=${TOKEN}`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws
    ws.onopen = () => {
      setOnline(true)
      ws.send(JSON.stringify({ type: 'hello', device_type: DESKTOP ? 'pc' : 'web', network: 'wifi-home' }))
    }
    ws.onclose = () => { setOnline(false); setState('IDLE'); setTimeout(connect, 2000) }
    ws.onmessage = async (e) => {
      if (typeof e.data !== 'string') return
      const msg = JSON.parse(e.data)
      if (msg.type === 'hello_ok') {
        // URLs do servidor: no desktop a página é local, então precisa do host
        playerRef.current?.preloadAcks(
          (msg.ack_sounds || []).map(a => ({ ...a, url: HTTP + a.url })))
      }
      else if (msg.type === 'wake') {
        setHeard(''); setAnswer('')
        playerRef.current?.resetQueue()       // nova pergunta, fila limpa
        window.jarvisDesktop?.wake()          // só acende o reator
      } else if (msg.type === 'ack') {
        playerRef.current?.playAck()          // "Sim?" local, sem rede nem LLM
      } else if (msg.type === 'state') {
        window.jarvisDesktop?.state(msg.state)
        setState(msg.state === 'IDLE' ? 'IDLE' : msg.state)
        if (msg.state === 'IDLE') setTimeout(() => { setHeard(''); setAnswer('') }, 4000)
      } else if (msg.type === 'stt_partial' || msg.type === 'stt_final') {
        setHeard(msg.text)
      } else if (msg.type === 'speak') {
        if (msg.seq === undefined) {
          // resposta curta, veio inteira
          setAnswer(msg.text || '')
          if (msg.audio_url) await playerRef.current?.playUrl(HTTP + msg.audio_url)
        } else {
          // resposta em pedaços: vai falando enquanto o resto ainda é escrito
          if (msg.seq === 0) {
            playerRef.current?.resetQueue()   // começo de uma nova resposta
            setAnswer(msg.text || '')
            window.jarvisDesktop?.speaking(true)
          } else {
            setAnswer(a => (a ? a + ' ' : '') + (msg.text || ''))
          }
          playerRef.current?.enqueue(msg.seq, msg.audio_url && HTTP + msg.audio_url)
        }
      } else if (msg.type === 'speak_end') {
        // avisa o app quando terminar de falar tudo (pra não sumir no meio)
        playerRef.current?.setOnIdle(() => window.jarvisDesktop?.speaking(false))
        if (!playerRef.current?.falando()) window.jarvisDesktop?.speaking(false)
      } else if (msg.type === 'ambient') {
        if (msg.temperature_c != null) setTemp(msg.temperature_c)
      }
    }
  }

  function openConfig() {
    refreshDevices()
    window.jarvisDesktop?.pin(true)
    setShowConfig(true)
  }
  function closeConfig() {
    window.jarvisDesktop?.pin(false)
    setShowConfig(false)
  }

  const idle = state === 'IDLE'
  return (
    <div className={'stage' + (DESKTOP ? ' desktop' : '')}>
      {!started && !DESKTOP && (
        <div className="tap-hint" onClick={begin}>
          <span>TOQUE PARA INICIAR O JARVIS</span>
        </div>
      )}
      <div className={'reactor-wrap' + (idle ? ' dim' : '')}>
        <canvas ref={canvasRef} className="reactor"
          style={{ width: 'min(72vmin, 560px)', height: 'min(72vmin, 560px)' }} />
      </div>
      <div className="transcript">
        {heard && <div>“{heard}”</div>}
        {answer && <div className="answer">{answer}</div>}
      </div>
      <div className={'hud' + (idle ? '' : ' dim')}
        style={{ '--drift-x': drift[0] + 'px', '--drift-y': drift[1] + 'px' }}>
        <div className="clock">{clock}</div>
        <div className="date">{date}</div>
        {temp != null && <div className="temp">{Number(temp).toFixed(1).replace('.', ',')} °C</div>}
      </div>
      <div className={'status-chip' + (online ? ' online' : '')}>
        <span className="dot" />{online ? 'ONLINE' : 'RECONECTANDO'}
      </div>
      {micWarn && <div className="mic-warn">{micWarn}</div>}
      {started && (
        <button className="gear" title="Configurações" onClick={openConfig}>⚙</button>
      )}
      {showConfig && (
        <ConfigModal devices={devices} prefs={prefs}
          onSave={(p) => { savePrefs(p); closeConfig() }}
          onClose={closeConfig} />
      )}
    </div>
  )
}

function ConfigModal({ devices, prefs, onSave, onClose }) {
  const [mics, setMics] = useState(prefs.mics || [])
  const [output, setOutput] = useState(prefs.output || '')
  const [levels, setLevels] = useState({})   // deviceId -> nível 0..1

  const toggleMic = (id) =>
    setMics(m => m.includes(id) ? m.filter(x => x !== id) : [...m, id])

  // mede todos os microfones ao vivo: um mudo aparece na hora
  useEffect(() => {
    let stop = false
    const cleanup = []
    ;(async () => {
      for (const d of devices.mics) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: { deviceId: { exact: d.deviceId } },
          })
          const ctx = new AudioContext()
          const an = ctx.createAnalyser()
          an.fftSize = 512
          ctx.createMediaStreamSource(stream).connect(an)
          const buf = new Uint8Array(an.fftSize)
          cleanup.push(() => { stream.getTracks().forEach(t => t.stop()); ctx.close() })
          const tick = () => {
            if (stop) return
            an.getByteTimeDomainData(buf)
            let peak = 0
            for (const v of buf) peak = Math.max(peak, Math.abs(v - 128) / 128)
            setLevels(l => ({ ...l, [d.deviceId]: peak }))
            setTimeout(tick, 120)
          }
          tick()
        } catch { /* dispositivo ocupado/indisponível */ }
      }
    })()
    return () => { stop = true; cleanup.forEach(f => f()) }
  }, [devices.mics])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-title">CONFIGURAÇÕES</div>

        <div className="modal-section">MICROFONES <span className="hint">(fale para ver a barrinha mexer; vários = escuta todos juntos)</span></div>
        <div className="modal-list">
          {devices.mics.map(d => {
            const lvl = levels[d.deviceId]
            const mudo = lvl !== undefined && lvl < 0.005
            return (
              <label key={d.deviceId} className="opt">
                <input type="checkbox" checked={mics.includes(d.deviceId)}
                  onChange={() => toggleMic(d.deviceId)} />
                <span className="opt-label">{d.label || 'Microfone'}</span>
                <span className="meter" title={mudo ? 'sem sinal' : 'captando'}>
                  <i style={{ width: `${Math.min(100, (lvl || 0) * 260)}%` }}
                    className={mudo ? 'dead' : ''} />
                </span>
              </label>
            )
          })}
          {!devices.mics.length && <div className="hint">nenhum microfone encontrado</div>}
        </div>

        <div className="modal-section">SAÍDA DE ÁUDIO</div>
        <select className="modal-select" value={output} onChange={e => setOutput(e.target.value)}>
          <option value="">Padrão do sistema</option>
          {devices.outs.map(d => (
            <option key={d.deviceId} value={d.deviceId}>{d.label || 'Saída'}</option>
          ))}
        </select>

        <div className="modal-actions">
          <button className="btn primary" onClick={() => onSave({ mics, output })}>Salvar</button>
          <button className="btn" onClick={onClose}>Cancelar</button>
          {window.jarvisDesktop && (
            <button className="btn danger" onClick={() => window.jarvisDesktop.quit()}>
              Fechar o JARVIS
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
