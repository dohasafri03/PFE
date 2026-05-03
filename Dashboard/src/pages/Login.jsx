import React, { useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { login as apiLogin } from "@/services/api"
import { useAuth } from "@/context/AuthContext"
import { normalizeProfileSelection } from "@/lib/profile"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Loader2, User, Lock, Eye, EyeOff } from "lucide-react"
import { Brand } from "@/components/brand/Brand"
import loginBg from "@/assets/login-bg.png"

export function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { setUser } = useAuth()

  const [profilePref, setProfilePref] = useState({ profile: "GLOBAL", sub_profile: "" }) // UI preference only
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const from = location.state?.from || "/"

  const onSubmit = async (e) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const res = await apiLogin(username, password)
      // Use backend profile when provided; otherwise fallback to the UI-selected preference.
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
      // Surface real errors (API unreachable / 401 / CORS) instead of always "invalid".
      const msg = (err && typeof err === "object" && "message" in err) ? String(err.message || "") : "";
      if (msg) {
        setError(msg)
      } else {
        setError("Identifiants invalides.")
      }
    } finally {
      setLoading(false)
    }
  }

  const roles = [
    { label: "GLOBAL", profile: "GLOBAL", sub_profile: "", cls: "bg-white/8 text-white/85 ring-1 ring-white/12" },
    // DATA is one profile; AI is a sub-profile under DATA
    { label: "DATA", profile: "DATA", sub_profile: "", cls: "bg-cyan-500/14 text-cyan-50 ring-1 ring-cyan-400/25" },
    { label: "AI", profile: "DATA", sub_profile: "AI", cls: "bg-violet-500/16 text-violet-50 ring-1 ring-violet-400/25" },
    { label: "CLOUD", profile: "CLOUD", sub_profile: "", cls: "bg-sky-500/14 text-sky-50 ring-1 ring-sky-400/25" },
    { label: "DEV", profile: "DEV", sub_profile: "", cls: "bg-emerald-500/14 text-emerald-50 ring-1 ring-emerald-400/25" },
  ]

  const isRoleActive = (r) => {
    const p = String(profilePref.profile || "").toUpperCase()
    const sp = String(profilePref.sub_profile || "").toUpperCase()
    return p === String(r.profile).toUpperCase() && sp === String(r.sub_profile || "").toUpperCase()
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-[#1a0b2e] text-white">
      {/* Photo d’arrière-plan : léger flou + zone droite (logo) plus nette */}
      <div className="pointer-events-none absolute inset-0">
        <img
          src={loginBg}
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[68%_center] opacity-95 blur-md scale-105 sm:object-[65%_center]"
        />
      </div>
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          clipPath: "ellipse(42% 58% at 76% 50%)",
          WebkitClipPath: "ellipse(42% 58% at 76% 50%)",
        }}
      >
        <img
          src={loginBg}
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[68%_center] contrast-[1.05] saturate-[1.06] sm:object-[65%_center]"
        />
      </div>
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-r from-[#1a0b2e]/95 via-[#1a0b2e]/50 to-[#1a0b2e]/10" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-transparent" />
      </div>
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 -left-40 h-[480px] w-[480px] rounded-full bg-[#6C63FF]/12 blur-3xl" />
        <div className="absolute -bottom-40 right-0 h-[500px] w-[500px] rounded-full bg-[#00C2D1]/10 blur-3xl" />
      </div>

      <div className="relative flex min-h-screen items-center justify-center p-5 sm:p-8">
        <Card className="group relative w-full max-w-xl overflow-hidden rounded-3xl border border-white/10 alexsys-glass transition-transform duration-300 will-change-transform hover:-translate-y-0.5 sm:max-w-4xl">
          <CardContent className="p-0">
            <div className="grid grid-cols-1 md:grid-cols-2">
              {/* LEFT: branding / identity */}
              <div className="relative min-w-0 p-7 sm:p-9 md:p-10">
                <div className="pointer-events-none absolute inset-0 opacity-60">
                  <div className="absolute -left-24 -top-24 h-64 w-64 rounded-full bg-white/6 blur-3xl" />
                  <div className="absolute -bottom-28 -right-24 h-72 w-72 rounded-full bg-white/6 blur-3xl" />
                </div>

                <div className="relative">
                  <Brand className="justify-start" />

                  <div className="mt-7 space-y-2">
                    <div className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
                      Alexsys Solutions
                    </div>
                    <div className="text-sm font-semibold tracking-wide text-white/65">
                      AI Procurement Intelligence
                    </div>
                    <div className="text-sm text-white/58">
                      Monitor tenders. Prioritize. Generate winning dossiers.
                    </div>
                  </div>

                  <div className="mt-6 flex flex-wrap gap-2">
                    {roles.map((r) => (
                      <button
                        key={`${r.profile}/${r.sub_profile || ""}/${r.label}`}
                        type="button"
                        onClick={() => setProfilePref({ profile: r.profile, sub_profile: r.sub_profile || "" })}
                        className={[
                          "inline-flex items-center rounded-full px-3 py-1 text-[11px] font-semibold backdrop-blur transition-all duration-200",
                          "hover:-translate-y-0.5 hover:shadow-[0_16px_40px_rgba(0,0,0,0.22)] active:translate-y-0",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20",
                          r.cls,
                          isRoleActive(r) ? "ring-2 ring-white/25 shadow-[0_0_0_1px_rgba(255,255,255,0.10)]" : "",
                        ].join(" ")}
                        aria-pressed={isRoleActive(r)}
                        title={`Use ${r.label}${r.sub_profile ? ` (${r.profile}/${r.sub_profile})` : ""}`}
                      >
                        {r.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* RIGHT: form */}
              <div className="min-w-0 border-t border-white/10 p-7 sm:p-9 md:border-t-0 md:border-l md:p-10">
                <div className="space-y-2">
                  <div className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                    Welcome back
                  </div>
                  <div className="text-sm text-white/60">
                    Sign in to access your dashboard.
                  </div>
                </div>

                <form onSubmit={onSubmit} className="mt-7 space-y-5">
              <div className="space-y-2">
                <div className="text-sm font-medium text-white/65">Username</div>
                <div className="relative">
                  <User className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-white/50" />
                  <Input
                    placeholder="Enter your username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    required
                    className="h-12 rounded-xl border-white/10 bg-black/25 pl-11 text-base text-white placeholder:text-white/45 transition-all duration-200 focus-visible:border-white/25 focus-visible:ring-2 focus-visible:ring-[#6C63FF]/30 focus-visible:bg-black/30"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-white/65">Password</div>
                  <button
                    type="button"
                    className="text-sm text-white/60 transition-colors hover:text-white/90 hover:underline underline-offset-4"
                    onClick={(e) => {
                      e.preventDefault();
                      setError("Forgot password: contact your admin or use the profile account passwords.");
                    }}
                  >
                    Forgot password?
                  </button>
                </div>

                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-white/50" />
                  <Input
                    placeholder="Enter your password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                    className="h-12 rounded-xl border-white/10 bg-black/25 pl-11 pr-11 text-base text-white placeholder:text-white/45 transition-all duration-200 focus-visible:border-white/25 focus-visible:ring-2 focus-visible:ring-[#3B82F6]/25 focus-visible:bg-black/30"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-2 text-white/60 hover:text-white transition-colors"
                    onClick={(e) => {
                      e.preventDefault();
                      setShowPassword((v) => !v);
                    }}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    title={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error ? (
                <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-100 transition-opacity">
                  {error}
                </div>
              ) : null}

              <Button
                type="submit"
                className="h-12 w-full rounded-xl bg-gradient-to-r from-[#2DD4BF] via-[#3B82F6] to-[#6C63FF] text-base font-semibold text-white shadow-lg shadow-black/30 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_20px_50px_rgba(59,130,246,0.22)] active:translate-y-0 active:shadow-[0_10px_30px_rgba(0,0,0,0.30)]"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Sign in"
                )}
              </Button>
                </form>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
