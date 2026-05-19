import { useCallback, useEffect, useRef } from "react"

const CYAN = { r: 0, g: 212, b: 255 }
const VIOLET = { r: 123, g: 47, b: 255 }

function pickColor(i) {
  return i % 3 === 0 ? VIOLET : CYAN
}

function createParticles(count, width, height) {
  return Array.from({ length: count }, (_, i) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.35,
    vy: (Math.random() - 0.5) * 0.35,
    r: 1.2 + Math.random() * 1.8,
    color: pickColor(i),
  }))
}

export function LoginParticleCanvas() {
  const canvasRef = useRef(null)
  const particlesRef = useRef([])
  const frameRef = useRef(0)
  const sizeRef = useRef({ w: 0, h: 0, count: 48 })

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const { w, h } = sizeRef.current
    const particles = particlesRef.current
  const linkDist = w < 640 ? 95 : 130

    ctx.clearRect(0, 0, w, h)

    for (const p of particles) {
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > w) p.vx *= -1
      if (p.y < 0 || p.y > h) p.vy *= -1
    }

    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i]
        const b = particles[j]
        const dx = a.x - b.x
        const dy = a.y - b.y
        const dist = Math.hypot(dx, dy)
        if (dist < linkDist) {
          const alpha = (1 - dist / linkDist) * 0.35
          ctx.strokeStyle = `rgba(0, 212, 255, ${alpha})`
          ctx.lineWidth = 0.6
          ctx.beginPath()
          ctx.moveTo(a.x, a.y)
          ctx.lineTo(b.x, b.y)
          ctx.stroke()
        }
      }
    }

    for (const p of particles) {
      const { r, g, b } = p.color
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.85)`
      ctx.shadowBlur = 12
      ctx.shadowColor = `rgba(${r}, ${g}, ${b}, 0.9)`
      ctx.fill()
      ctx.shadowBlur = 0
    }

    frameRef.current = requestAnimationFrame(draw)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    const resize = () => {
      const parent = canvas.parentElement
      const w = parent?.clientWidth || window.innerWidth
      const h = parent?.clientHeight || window.innerHeight
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      const ctx = canvas.getContext("2d")
      if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      sizeRef.current = { w, h, count: w < 640 ? 28 : 52 }
      particlesRef.current = createParticles(sizeRef.current.count, w, h)
    }

    resize()
    window.addEventListener("resize", resize)
    frameRef.current = requestAnimationFrame(draw)

    return () => {
      window.removeEventListener("resize", resize)
      cancelAnimationFrame(frameRef.current)
    }
  }, [draw])

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-[1]"
      aria-hidden
    />
  )
}
