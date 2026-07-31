// Reator arc: desenho em canvas, uma animação por estado.
// Estados: IDLE (pulso lento), LISTENING (reage ao volume), THINKING (anéis girando),
// EXECUTING (fluxo de energia), DONE (verde discreto), ERROR (vermelho temporário).

const CYAN = [33, 212, 243]
const GREEN = [72, 226, 155]
const RED = [255, 82, 82]

export function createReactor(canvas) {
  const ctx = canvas.getContext('2d')
  let state = 'IDLE'
  let level = 0            // volume 0..1 (LISTENING)
  let stateT = 0           // tempo desde a troca de estado
  let raf = 0
  let last = performance.now()
  let colorMix = 0         // 0 = ciano, 1 = cor do estado especial

  function setState(s) {
    if (s !== state) { state = s; stateT = 0 }
  }
  function setLevel(v) { level = Math.min(1, Math.max(0, v)) }

  function mix(a, b, t) { return a.map((v, i) => Math.round(v + (b[i] - v) * t)) }
  function rgba(c, a) { return `rgba(${c[0]},${c[1]},${c[2]},${a})` }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    stateT += dt
    const t = now / 1000

    const dpr = window.devicePixelRatio || 1
    const size = Math.min(canvas.clientWidth, canvas.clientHeight)
    if (canvas.width !== size * dpr) { canvas.width = size * dpr; canvas.height = size * dpr }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, size, size)

    const cx = size / 2, cy = size / 2
    const R = size * 0.32

    let target = 0
    let special = CYAN
    if (state === 'DONE') { special = GREEN; target = Math.max(0, 1 - stateT / 1.6) }
    if (state === 'ERROR') { special = RED; target = Math.max(0, 1 - stateT / 1.6) }
    colorMix += (target - colorMix) * Math.min(1, dt * 6)
    const C = mix(CYAN, special, colorMix)

    // intensidade base por estado
    let glow = 0.35 + 0.08 * Math.sin(t * 0.9)                    // IDLE: pulso lento
    if (state === 'LISTENING') glow = 0.75 + level * 0.5
    if (state === 'THINKING') glow = 0.7 + 0.12 * Math.sin(t * 3)
    if (state === 'EXECUTING') glow = 0.85 + 0.15 * Math.sin(t * 6)
    if (state === 'DONE' || state === 'ERROR') glow = 0.9

    // halo
    const halo = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 2.1)
    halo.addColorStop(0, rgba(C, 0.16 * glow))
    halo.addColorStop(0.55, rgba(C, 0.05 * glow))
    halo.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = halo
    ctx.fillRect(0, 0, size, size)

    // núcleo
    const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.55)
    core.addColorStop(0, rgba([220, 250, 255], 0.9 * glow))
    core.addColorStop(0.35, rgba(C, 0.55 * glow))
    core.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = core
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.55, 0, Math.PI * 2); ctx.fill()

    // anel principal
    ctx.lineWidth = Math.max(2, size * 0.008)
    ctx.strokeStyle = rgba(C, 0.85 * glow)
    ctx.shadowColor = rgba(C, 0.9)
    ctx.shadowBlur = size * 0.02 * glow
    const breathe = state === 'LISTENING' ? level * size * 0.012 : Math.sin(t * 0.9) * size * 0.004
    ctx.beginPath(); ctx.arc(cx, cy, R + breathe, 0, Math.PI * 2); ctx.stroke()

    // segmentos internos (10 arcos)
    const segSpin = state === 'THINKING' ? t * 2.2 : state === 'EXECUTING' ? t * 4 : t * 0.15
    ctx.lineWidth = Math.max(2, size * 0.014)
    for (let i = 0; i < 10; i++) {
      const a0 = segSpin + (i / 10) * Math.PI * 2
      ctx.strokeStyle = rgba(C, (0.25 + 0.55 * ((i % 3) / 2)) * glow)
      ctx.beginPath(); ctx.arc(cx, cy, R * 0.78, a0, a0 + Math.PI * 0.13); ctx.stroke()
    }

    // anel externo fino girando ao contrário
    const spin2 = state === 'THINKING' ? -t * 1.4 : -t * 0.1
    ctx.lineWidth = Math.max(1, size * 0.004)
    ctx.strokeStyle = rgba(C, 0.5 * glow)
    for (let i = 0; i < 3; i++) {
      const a0 = spin2 + (i / 3) * Math.PI * 2
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.22, a0, a0 + Math.PI * 0.5); ctx.stroke()
    }

    // EXECUTING: partículas fluindo pra fora
    if (state === 'EXECUTING') {
      for (let i = 0; i < 14; i++) {
        const p = ((t * 0.6 + i / 14) % 1)
        const ang = (i / 14) * Math.PI * 2 + t * 0.5
        const r = R * (0.6 + p * 0.9)
        ctx.fillStyle = rgba(C, (1 - p) * 0.7)
        ctx.beginPath()
        ctx.arc(cx + Math.cos(ang) * r, cy + Math.sin(ang) * r, size * 0.004, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    ctx.shadowBlur = 0
    raf = requestAnimationFrame(frame)
  }

  raf = requestAnimationFrame(frame)
  return { setState, setLevel, destroy: () => cancelAnimationFrame(raf) }
}
