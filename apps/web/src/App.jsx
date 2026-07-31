import React, { useEffect, useRef, useState } from 'react'
import { createPlayer, startMic } from './audio.js'
import { createReactor } from './reactor.js'

const params = new URLSearchParams(location.search)
// modo desktop: janela Electron da bandeja — auto-inicia e avisa o main pra mostrar/esconder
const DESKTOP = params.get('desktop') === '1'
const DEVICE_ID = params.get('device') || localStorage.getItem('jarvis_device') || 'web-dev'
const TOKEN = params.get('token') || localStorage.getItem('jarvis_token') || 'tk_web_3Za5Xb7Vc9Td1Rf4Pg6Nh8Lj2'

const loadAudioPrefs = () => {
  try { return JSON.parse(localStorage.getItem('jarvis_audio') || '{}') } catch { return {} }
}

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
    try {
      micRef.current = await startMic(
        (frame) => { if (wsRef.current?.readyState === 1) wsRef.current.send(frame) },
        (lvl) => reactorRef.current?.setLevel(lvl),
        micIds || [],
      )
    } catch {
      setAnswer('Sem acesso ao microfone')
    }
  }

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
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/${DEVICE_ID}?token=${TOKEN}`)
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
      if (msg.type === 'hello_ok') playerRef.current?.preloadAcks(msg.ack_sounds || [])
      else if (msg.type === 'wake') {
        setHeard(''); setAnswer('')
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
        setAnswer(msg.text || '')
        if (msg.audio_url) await playerRef.current?.playUrl(msg.audio_url)
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

  const toggleMic = (id) =>
    setMics(m => m.includes(id) ? m.filter(x => x !== id) : [...m, id])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-title">CONFIGURAÇÕES</div>

        <div className="modal-section">MICROFONES <span className="hint">(vários = escuta todos juntos; nenhum = padrão do sistema)</span></div>
        <div className="modal-list">
          {devices.mics.map(d => (
            <label key={d.deviceId} className="opt">
              <input type="checkbox" checked={mics.includes(d.deviceId)}
                onChange={() => toggleMic(d.deviceId)} />
              <span>{d.label || 'Microfone'}</span>
            </label>
          ))}
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
