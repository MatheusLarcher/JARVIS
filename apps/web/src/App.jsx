import React, { useEffect, useRef, useState } from 'react'
import { createPlayer, startMic } from './audio.js'
import { createReactor } from './reactor.js'

const params = new URLSearchParams(location.search)
// modo desktop: janela Electron da bandeja — auto-inicia e avisa o main pra mostrar/esconder
const DESKTOP = params.get('desktop') === '1'
const DEVICE_ID = params.get('device') || localStorage.getItem('jarvis_device') || 'web-dev'
const TOKEN = params.get('token') || localStorage.getItem('jarvis_token') || 'tk_web_3Za5Xb7Vc9Td1Rf4Pg6Nh8Lj2'

export default function App() {
  const canvasRef = useRef(null)
  const reactorRef = useRef(null)
  const wsRef = useRef(null)
  const playerRef = useRef(null)
  const [started, setStarted] = useState(false)
  const [online, setOnline] = useState(false)
  const [state, setState] = useState('IDLE')
  const [clock, setClock] = useState('')
  const [date, setDate] = useState('')
  const [temp, setTemp] = useState(null)
  const [heard, setHeard] = useState('')
  const [answer, setAnswer] = useState('')
  const [drift, setDrift] = useState([0, 0])

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

  async function begin() {
    setStarted(true)
    playerRef.current = createPlayer()
    connect()
    try {
      await startMic(
        (frame) => { if (wsRef.current?.readyState === 1) wsRef.current.send(frame) },
        (lvl) => reactorRef.current?.setLevel(lvl),
      )
    } catch {
      setAnswer('Sem acesso ao microfone')
    }
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/${DEVICE_ID}?token=${TOKEN}`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws
    ws.onopen = () => {
      setOnline(true)
      ws.send(JSON.stringify({ type: 'hello', device_type: 'web', network: 'wifi-home' }))
    }
    ws.onclose = () => { setOnline(false); setState('IDLE'); setTimeout(connect, 2000) }
    ws.onmessage = async (e) => {
      if (typeof e.data !== 'string') return
      const msg = JSON.parse(e.data)
      if (msg.type === 'hello_ok') playerRef.current?.preloadAcks(msg.ack_sounds || [])
      else if (msg.type === 'wake') {
        setHeard(''); setAnswer('')
        window.jarvisDesktop?.wake()
        playerRef.current?.playAck()          // resposta local instantânea
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
    </div>
  )
}
