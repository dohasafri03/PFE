import { motion } from "framer-motion"
import { LoginParticleCanvas } from "./LoginParticleCanvas"
import loginBg from "@/assets/login-bg.png"

const HEX_POSITIONS = [
  { top: "8%", left: "6%", size: 72, delay: "0s" },
  { top: "18%", right: "8%", size: 56, delay: "1.2s" },
  { bottom: "22%", left: "12%", size: 64, delay: "0.6s" },
  { bottom: "12%", right: "14%", size: 80, delay: "1.8s" },
  { top: "42%", left: "4%", size: 48, delay: "2.4s" },
  { top: "55%", right: "5%", size: 52, delay: "0.9s" },
]

function Hexagon({ size }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className="text-[#7B2FFF]/25"
      aria-hidden
    >
      <polygon
        points="50,4 93,27 93,73 50,96 7,73 7,27"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <polygon
        points="50,18 78,34 78,66 50,82 22,66 22,34"
        fill="none"
        stroke="rgba(0,212,255,0.35)"
        strokeWidth="0.6"
      />
    </svg>
  )
}

export function LoginScene() {
  return (
    <motion.div className="pointer-events-none absolute inset-0 overflow-hidden bg-[#0A0A1A]">
      <motion.img
        src={loginBg}
        alt=""
        className="absolute inset-0 h-full w-full object-cover object-[72%_center] sm:object-[68%_center]"
        initial={{ opacity: 0, scale: 1.04 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, ease: "easeOut" }}
      />

      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-[#0A0A1A]/92 via-[#0A0A1A]/55 to-[#0A0A1A]/12"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1 }}
        aria-hidden
      />
      <motion.div
        className="absolute inset-0 bg-gradient-to-t from-[#0A0A1A]/50 via-transparent to-[#0A0A1A]/20"
        aria-hidden
      />

      <div className="absolute inset-0 login-animated-gradient opacity-40 mix-blend-screen" aria-hidden />

      <motion.div
        className="login-circuit-grid absolute inset-0"
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.28 }}
        transition={{ duration: 1.5 }}
        aria-hidden
      />

      {HEX_POSITIONS.map((h, i) => (
        <motion.div
          key={i}
          className="login-hex-pulse absolute"
          style={{
            top: h.top,
            left: h.left,
            right: h.right,
            bottom: h.bottom,
            animationDelay: h.delay,
          }}
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 + i * 0.08, duration: 0.8 }}
        >
          <Hexagon size={h.size} />
        </motion.div>
      ))}

      <LoginParticleCanvas />

      <motion.div
        className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#0A0A1A_65%)]"
        aria-hidden
      />
    </motion.div>
  )
}
