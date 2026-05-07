import React, { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Moon, Sun, Bell, ChevronDown, LayoutDashboard, FileText, User, LogOut } from "lucide-react"
import { useTheme } from "@/context/ThemeContext"
import { useAuth } from "@/context/AuthContext"
import { fetchNotifications, logout as apiLogout, markAllNotificationsRead, markNotificationRead } from "@/services/api"
import { Brand } from "@/components/brand/Brand"
import { normalizeProfileSelection } from "@/lib/profile"
import { Link, useLocation } from "react-router-dom"
import { cn } from "@/lib/utils"
import { motion } from "framer-motion"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

export function Header() {
  const { theme, setTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, setUser } = useAuth()
  const [notifState, setNotifState] = useState({ unread: 0, items: [] })
  const [notifError, setNotifError] = useState("")

  const initials = useMemo(() => {
    const raw = String(user?.display_name || user?.username || "").trim()
    if (!raw) return "U"
    const parts = raw.split(/\s+/).filter(Boolean)
    const a = (parts[0] || raw).slice(0, 1)
    const b = (parts[1] || raw.slice(1, 2) || "").slice(0, 1)
    return (a + b).toUpperCase()
  }, [user?.display_name, user?.username])

  const navItems = useMemo(() => ([
    { icon: LayoutDashboard, label: "Dashboard", href: "/" },
    { icon: FileText, label: "Reports", href: "/reports" },
  ]), [])

  const onLogout = async () => {
    await apiLogout()
    setUser(null)
    navigate("/login", { replace: true })
  }

  const notifProfile = useMemo(() => {
    const fromUser = String(user?.profile || "").trim()
    const fromUserSub = String(user?.sub_profile || "").trim()
    let storedProfile = ""
    let storedSub = ""
    try {
      storedProfile = localStorage.getItem("marche_ai_profile") || ""
      storedSub = localStorage.getItem("marche_ai_sub_profile") || ""
    } catch (_) {}
    const sel = normalizeProfileSelection({
      profile: fromUser || storedProfile || "GLOBAL",
      sub_profile: fromUserSub || storedSub || "",
    })
    return String(sel.profile || "GLOBAL").toUpperCase()
  }, [user?.profile, user?.sub_profile])

  const loadNotifications = async () => {
    const res = await fetchNotifications(5, notifProfile)
    setNotifError("")
    setNotifState({ unread: res.unread_count ?? 0, items: res.notifications || [] })
  }

  useEffect(() => {
    loadNotifications().catch((e) => setNotifError(e?.message || "Failed to load notifications."))
    const t = setInterval(() => {
      loadNotifications().catch((e) => setNotifError(e?.message || "Failed to load notifications."))
    }, 60_000)
    const onStorage = (e) => {
      if (!e) return
      if (e.key === "marche_ai_profile" || e.key === "marche_ai_sub_profile") {
        loadNotifications().catch(() => {})
      }
    }
    window.addEventListener("storage", onStorage)
    return () => {
      clearInterval(t)
      window.removeEventListener("storage", onStorage)
    }
  }, [notifProfile, user?.username])

  const unreadBadge = useMemo(() => {
    const n = Number(notifState.unread || 0)
    return n > 99 ? "99+" : String(n)
  }, [notifState.unread])

  const profileBadge = useMemo(() => {
    const sel = normalizeProfileSelection({ profile: user?.profile, sub_profile: user?.sub_profile })
    const p = String(sel.profile || "GLOBAL").toUpperCase()
    const sp = sel.sub_profile ? String(sel.sub_profile).toUpperCase() : ""
    const label = sp ? `${p} / ${sp}` : p
    const tone =
      p === "DATA"
        ? "bg-[#6C63FF]/15 text-[#c7c4ff] ring-1 ring-[#6C63FF]/30"
        : p === "CLOUD"
        ? "bg-sky-500/15 text-sky-200 ring-1 ring-sky-500/30"
        : p === "DEV"
        ? "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/30"
        : "bg-white/5 text-muted-foreground ring-1 ring-white/10"
    return { label, tone }
  }, [user?.profile, user?.sub_profile])

  return (
    <header className="sticky top-0 z-30 flex h-[72px] w-full min-w-0 items-center justify-between gap-3 border-b border-border bg-background/60 px-4 sm:px-6 backdrop-blur">
      <div className="flex min-w-0 flex-1 items-center gap-5">
        <Brand compact className="scale-[1.1] origin-left" />
        <div className="hidden h-9 w-px bg-border/80 sm:block" aria-hidden="true" />
        <nav className="hidden min-w-0 items-center gap-3 sm:flex">
          {navItems.map((item) => {
            const active = location.pathname === item.href
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                to={item.href}
                className={cn(
                  "inline-flex items-center gap-2.5 rounded-full px-4 py-2 text-[15px] font-semibold transition-colors",
                  active
                    ? "bg-gradient-to-r from-primary/20 to-accent/10 text-foreground ring-1 ring-primary/20"
                    : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
                )}
              >
                <Icon className="h-[18px] w-[18px]" />
                <span className="truncate">{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:gap-4">
        <span className={`hidden sm:inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${profileBadge.tone}`}>
          {profileBadge.label}
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon" className="relative flex">
              <Bell className="h-4 w-4" />
              {notifState.unread ? (
                <span className="absolute -right-1 -top-1 min-w-5 h-5 px-1 rounded-full bg-destructive text-destructive-foreground text-[10px] flex items-center justify-center">
                  {unreadBadge}
                </span>
              ) : null}
              <span className="sr-only">Notifications</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-96">
            <DropdownMenuLabel className="flex items-center justify-between">
              <span>Notifications</span>
              <button
                type="button"
                className="text-xs text-primary hover:underline"
                onClick={async (e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  await markAllNotificationsRead(notifProfile).catch(() => {})
                  await loadNotifications().catch(() => {})
                }}
              >
                Mark all read
              </button>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {notifError ? (
              <div className="px-2 py-3">
                <div className="text-sm text-destructive">{notifError}</div>
                <button
                  type="button"
                  className="mt-2 text-xs text-primary hover:underline"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    loadNotifications().catch((err) => setNotifError(err?.message || "Failed to load notifications."))
                  }}
                >
                  Retry
                </button>
              </div>
            ) : notifState.items?.length ? (
              <div className="max-h-80 overflow-auto">
                {notifState.items.map((n) => (
                  <DropdownMenuItem
                    key={n.id}
                    className={`cursor-pointer whitespace-normal items-start gap-2 ${n.read ? "" : "bg-primary/5"}`}
                    onClick={async () => {
                      if (!n.read) await markNotificationRead(n.id, notifProfile).catch(() => {})
                      if (n.opportunity_id) navigate("/", { state: { openOpportunityId: n.opportunity_id } })
                      else navigate("/notifications")
                      await loadNotifications().catch(() => {})
                    }}
                  >
                    <div className="flex flex-col gap-0.5">
                      <div className="text-xs text-muted-foreground">{n.type}</div>
                      <div className="text-sm">{n.message}</div>
                    </div>
                  </DropdownMenuItem>
                ))}
              </div>
            ) : (
              <div className="px-2 py-3 text-sm text-muted-foreground">No notifications.</div>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem className="cursor-pointer" onClick={() => navigate("/notifications")}>
              View all notifications
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {/* Theme switch (pill) */}
        <div
          className="relative flex h-9 w-[92px] items-center rounded-full border border-border bg-background/55 p-1 shadow-sm backdrop-blur"
          role="group"
          aria-label="Theme"
        >
          <div
            className={[
              "pointer-events-none absolute left-1 top-1 h-7 w-[44px] rounded-full bg-white/80 shadow",
              "transition-transform duration-200 ease-out",
              "dark:bg-white/10",
              theme === "dark" ? "translate-x-[38px]" : "translate-x-0",
            ].join(" ")}
          />
          <button
            type="button"
            onClick={() => setTheme("light")}
            className={[
              "relative z-10 flex h-7 w-[44px] items-center justify-center rounded-full transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              theme === "light" ? "text-[#F59E0B]" : "text-muted-foreground hover:text-foreground",
            ].join(" ")}
            aria-pressed={theme === "light"}
            aria-label="Light mode"
          >
            <Sun className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setTheme("dark")}
            className={[
              "relative z-10 flex h-7 w-[44px] items-center justify-center rounded-full transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              theme === "dark" ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            ].join(" ")}
            aria-pressed={theme === "dark"}
            aria-label="Dark mode"
          >
            <Moon className="h-4 w-4" />
          </button>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-9 px-2 rounded-full flex items-center gap-2">
              <Avatar className="h-8 w-8">
                <AvatarImage src={user?.avatar_url || "/avatars/01.png"} alt="@user" />
                <AvatarFallback>{(user?.display_name || user?.username || "AD").slice(0, 2).toUpperCase()}</AvatarFallback>
              </Avatar>
              <span className="hidden sm:inline text-sm font-medium">{user?.display_name || user?.username || "Admin"}</span>
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            forceMount
            className={cn(
              "w-[220px] rounded-[14px] border border-slate-200 bg-white p-2 shadow-xl shadow-indigo-100/60",
              "dark:border-white/10 dark:bg-[#1E1E2E]"
            )}
          >
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
                  <div className="rounded-[10px] bg-gradient-to-r from-indigo-50 to-purple-50 p-3 dark:from-white/5 dark:to-white/5">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-200/60">
                        <span className="text-white font-bold text-sm">{initials}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">
                          {user?.display_name || user?.username || "User"}
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="text-[11px] font-medium text-indigo-500 dark:text-indigo-300">
                            {user?.role || "session"}
                          </span>
                          <span className="inline-flex items-center rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-semibold text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-200 ring-1 ring-indigo-200/60 dark:ring-indigo-500/25">
                            {String(user?.role || "Admin")}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="my-1.5 border-t border-slate-100 dark:border-white/10" />

                  <DropdownMenuItem
                    className={cn(
                      "group cursor-pointer rounded-lg px-2.5 py-2 text-sm text-slate-700 transition-all",
                      "hover:bg-indigo-50 hover:text-indigo-600 focus:bg-indigo-50 focus:text-indigo-600",
                      "dark:text-slate-200 dark:hover:bg-white/5 dark:hover:text-indigo-200 dark:focus:bg-white/5 dark:focus:text-indigo-200"
                    )}
                    onClick={() => navigate("/profile")}
                  >
                    <User className="h-[15px] w-[15px] text-slate-500 transition-colors group-hover:text-indigo-600 dark:text-slate-300 dark:group-hover:text-indigo-200" />
                    <span className="flex-1">Mon profil</span>
                    <span className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">›</span>
                  </DropdownMenuItem>

                  <div className="my-1.5 border-t border-slate-100 dark:border-white/10" />

                  <DropdownMenuItem
                    className={cn(
                      "group cursor-pointer rounded-lg px-2.5 py-2 text-sm font-medium text-red-500 transition-all",
                      "hover:bg-red-50 hover:text-red-600 focus:bg-red-50 focus:text-red-600",
                      "dark:text-red-300 dark:hover:bg-red-500/10 dark:hover:text-red-200 dark:focus:bg-red-500/10 dark:focus:text-red-200"
                    )}
                    onClick={onLogout}
                  >
                    <LogOut className="h-[15px] w-[15px] text-red-400 transition-colors group-hover:text-red-600 dark:text-red-300 dark:group-hover:text-red-200" />
                    <span className="flex-1">Se déconnecter</span>
                    <span className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">›</span>
                  </DropdownMenuItem>
            </motion.div>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
