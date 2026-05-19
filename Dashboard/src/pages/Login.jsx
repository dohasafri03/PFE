import React, { useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { login as apiLogin } from "@/services/api"
import { useAuth } from "@/context/AuthContext"
import { normalizeProfileSelection } from "@/lib/profile"
import { useTypingEffect } from "@/hooks/useTypingEffect"
import { LoginScene } from "@/components/login/LoginScene"
import { Loader2, User, Lock, Eye, EyeOff } from "lucide-react"
import logo from "@/assets/alexsys-logo.png"

const SUBTITLE = "Sign in to access your AI dashboard"

const PROFILE_BADGES = [
  { label: "GLOBAL", profile: "GLOBAL", sub_profile: "" },
  { label: "DATA", profile: "DATA", sub_profile: "" },
  { label: "AI", profile: "DATA", sub_profile: "AI" },
  { label: "CLOUD", profile: "CLOUD", sub_profile: "" },
  { label: "DEV", profile: "DEV", sub_profile: "" },
]

const badgeMotion = {
  hidden: { opacity: 0, y: 8, scale: 0.92 },
  show: (i) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { delay: 0.45 + i * 0.1, duration: 0.4, ease: [0.22, 1, 0.36, 1] },
  }),
}

const fadeUp = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, delay: 0.35 } },
}

export function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { setUser } = useAuth()

  const [profilePref, setProfilePref] = useState({ profile: "GLOBAL", sub_profile: "" })
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [fieldsReady, setFieldsReady] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [shakeKey, setShakeKey] = useState(0)

  const typedSubtitle = useTypingEffect(SUBTITLE, 28, true)
  const subtitleDone = typedSubtitle.length >= SUBTITLE.length
  const enableFields = () => setFieldsReady(true)
  const from = location.state?.from || "/"
  const hasError = Boolean(error)

  const isRoleActive = (r) => {
    const p = String(profilePref.profile || "").toUpperCase()
    const sp = String(profilePref.sub_profile || "").toUpperCase()
    return p === String(r.profile).toUpperCase() && sp === String(r.sub_profile || "").toUpperCase()
  }

  const inputBase =
    "login-input-focus h-[52px] w-full rounded-xl border bg-[rgba(255,255,255,0.05)] text-base text-white outline-none transition-all duration-200 placeholder:text-gray-500 [&:-webkit-autofill]:[-webkit-text-fill-color:rgb(255_255_255)] [&:-webkit-autofill]:shadow-[inset_0_0_0px_1000px_rgb(10_10_26/0.95)]"

  const onSubmit = async (e) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const res = await apiLogin(username, password)
      const rawProfile = res?.profile || res?.role || profilePref.profile
      const rawSub = res?.sub_profile ?? profilePref.sub_profile
      const sel = normalizeProfileSelection({ profile: rawProfile, sub_profile: rawSub })
      const profile = sel.profile
      const sub_profile = sel.sub_profile
      try {
        localStorage.setItem("marche_ai_profile", profile)
        if (sub_profile) localStorage.setItem("marche_ai_sub_profile", sub_profile)
        else localStorage.removeItem("marche_ai_sub_profile")
      } catch (_) {}

      setUser({
        username: res.username || username,
        display_name: res.display_name || res.username || username,
        role: res.role || "Admin",
        profile,
        sub_profile,
        avatar_url: res.avatar_url || "",
      })
      navigate(from, { replace: true })
    } catch (err) {
      const msg = err && typeof err === "object" && "message" in err ? String(err.message || "") : ""
      const lower = msg.toLowerCase()
      const looksLikeInvalid =
        lower.includes("invalid credentials") ||
        lower.includes("401") ||
        (lower.includes('"detail"') && lower.includes("invalid"))

      setShakeKey((k) => k + 1)
      if (looksLikeInvalid) {
        setError("Identifiants incorrects. Vérifiez votre nom d'utilisateur et votre mot de passe.")
      } else if (msg) {
        setError(msg)
      } else {
        setError("Connexion impossible. Réessayez dans quelques instants.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      className="relative flex min-h-screen min-w-0 items-center justify-center overflow-x-hidden bg-[#0A0A1A] p-4 sm:p-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <LoginScene />

      <motion.div
        key={shakeKey}
        className={[
          "login-card-scan relative z-10 w-[94%] max-w-[520px] overflow-hidden rounded-[24px] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] p-8 backdrop-blur-xl sm:w-[92%] sm:p-10 md:max-w-[560px] md:p-11",
          hasError ? "login-shake" : "",
        ].join(" ")}
        style={{
          boxShadow:
            "0 25px 50px rgba(0,0,0,0.5), 0 0 80px rgba(123,47,255,0.15)",
        }}
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      >
        {/* Header */}
        <div className="flex flex-col items-center text-center">
          <motion.img
            src={logo}
            alt="Alexsys Solutions"
            className="h-14 w-14 rounded-xl ring-1 ring-white/10 sm:h-16 sm:w-16"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.15, duration: 0.5 }}
          />
          <motion.p
            className="mt-4 text-sm font-medium tracking-wide text-gray-500"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
          >
            Alexsys Solutions
          </motion.p>
          <motion.h1
            className="mt-3 text-3xl font-bold text-white sm:text-[2rem]"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25, duration: 0.5 }}
          >
            Welcome back
          </motion.h1>
          <motion.p
            className="mt-3 min-h-[24px] text-base text-gray-400"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
          >
            {typedSubtitle}
            {!subtitleDone ? (
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-cyan-400/80 align-middle" aria-hidden />
            ) : null}
          </motion.p>

          <motion.div
            className="mt-6 flex flex-wrap items-center justify-center gap-2.5"
            initial="hidden"
            animate="show"
          >
            {PROFILE_BADGES.map((r, i) => (
              <motion.button
                key={r.label}
                type="button"
                custom={i}
                initial="hidden"
                animate="show"
                variants={badgeMotion}
                onClick={() => setProfilePref({ profile: r.profile, sub_profile: r.sub_profile || "" })}
                className={[
                  "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-all duration-200",
                  "border-[rgba(0,212,255,0.3)] bg-[rgba(0,212,255,0.06)] text-[#00D4FF]",
                  "hover:bg-[rgba(0,212,255,0.12)] hover:shadow-[0_0_16px_rgba(0,212,255,0.15)]",
                  isRoleActive(r) ? "ring-1 ring-[#00D4FF]/60 shadow-[0_0_12px_rgba(0,212,255,0.25)]" : "",
                ].join(" ")}
                aria-pressed={isRoleActive(r)}
              >
                {r.label}
              </motion.button>
            ))}
          </motion.div>
        </div>

        {/* Separator */}
        <div
          className="my-7 h-px w-full"
          style={{
            background:
              "linear-gradient(90deg, transparent, rgba(0,212,255,0.65), transparent)",
          }}
          aria-hidden
        />

        {/* Form */}
        <form onSubmit={onSubmit} autoComplete="off" className="relative space-y-5">
          <input
            type="text"
            name="prevent_autofill_user"
            tabIndex={-1}
            aria-hidden
            autoComplete="username"
            className="pointer-events-none absolute h-0 w-0 opacity-0"
            defaultValue=""
          />
          <input
            type="password"
            name="prevent_autofill_pass"
            tabIndex={-1}
            aria-hidden
            autoComplete="current-password"
            className="pointer-events-none absolute h-0 w-0 opacity-0"
            defaultValue=""
          />

          <div className="space-y-2">
            <label
              htmlFor="login-username"
              className="text-sm font-medium uppercase tracking-wider text-gray-400"
            >
              Username
            </label>
            <div className="relative">
              <User className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-500" />
              <input
                id="login-username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                name="marche_identifier"
                autoComplete="off"
                readOnly={!fieldsReady}
                onFocus={enableFields}
                required
                className={[
                  inputBase,
                  "border-[rgba(255,255,255,0.1)] pl-12 pr-4",
                  hasError ? "login-input-error" : "",
                ].join(" ")}
              />
            </div>
          </div>

          <motion.div className="space-y-2" variants={fadeUp} initial="hidden" animate="show" custom={0}>
            <div className="flex items-center justify-between gap-2">
              <label
                htmlFor="login-password"
                className="text-sm font-medium uppercase tracking-wider text-gray-400"
              >
                Password
              </label>
              <button
                type="button"
                className="text-sm text-cyan-400 transition-colors hover:text-cyan-300"
                onClick={(e) => {
                  e.preventDefault()
                  setError("Mot de passe oublié : contactez votre administrateur.")
                }}
              >
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-500" />
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                name="marche_secret"
                autoComplete="off"
                readOnly={!fieldsReady}
                onFocus={enableFields}
                required
                className={[
                  inputBase,
                  "border-[rgba(255,255,255,0.1)] pl-12 pr-14",
                  hasError ? "login-input-error" : "",
                ].join(" ")}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
                onClick={(e) => {
                  e.preventDefault()
                  setShowPassword((v) => !v)
                }}
                aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
              >
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
          </motion.div>

          <AnimatePresence mode="wait">
            {error ? (
              <motion.div
                key="login-error"
                initial={{ opacity: 0, y: -8, height: 0 }}
                animate={{ opacity: 1, y: 0, height: "auto" }}
                exit={{ opacity: 0, y: -4, height: 0 }}
                transition={{ duration: 0.25 }}
                className="overflow-hidden rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-200"
                role="alert"
              >
                {error}
              </motion.div>
            ) : null}
          </AnimatePresence>

          <motion.button
            type="submit"
            disabled={loading}
            className="flex h-[52px] w-full items-center justify-center rounded-xl bg-gradient-to-r from-cyan-500 via-blue-600 to-purple-600 text-base font-semibold text-white transition-all duration-200 hover:scale-[1.01] hover:opacity-90 hover:shadow-[0_8px_30px_rgba(0,212,255,0.3)] active:scale-[0.98] disabled:pointer-events-none disabled:opacity-60"
            whileTap={{ scale: loading ? 1 : 0.98 }}
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Signing in...
              </>
            ) : (
              "Sign in"
            )}
          </motion.button>
        </form>
      </motion.div>
    </motion.div>
  )
}
