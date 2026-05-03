import React, { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Moon, Sun, Bell, ChevronDown, LayoutDashboard, FileText } from "lucide-react"
import { useTheme } from "@/context/ThemeContext"
import { useAuth } from "@/context/AuthContext"
import { fetchNotifications, logout as apiLogout, markAllNotificationsRead, markNotificationRead } from "@/services/api"
import { Brand } from "@/components/brand/Brand"
import { normalizeProfileSelection } from "@/lib/profile"
import { Link, useLocation } from "react-router-dom"
import { cn } from "@/lib/utils"
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

  const navItems = useMemo(() => ([
    { icon: LayoutDashboard, label: "Dashboard", href: "/" },
    { icon: FileText, label: "Reports", href: "/reports" },
  ]), [])

  const onLogout = async () => {
    await apiLogout()
    setUser(null)
    navigate("/login", { replace: true })
  }

  const loadNotifications = async () => {
    const res = await fetchNotifications(5)
    setNotifError("")
    setNotifState({ unread: res.unread_count ?? 0, items: res.notifications || [] })
  }

  useEffect(() => {
    loadNotifications().catch((e) => setNotifError(e?.message || "Failed to load notifications."))
    const t = setInterval(() => {
      loadNotifications().catch((e) => setNotifError(e?.message || "Failed to load notifications."))
    }, 60_000)
    return () => clearInterval(t)
  }, [])

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
                  await markAllNotificationsRead().catch(() => {})
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
                      if (!n.read) await markNotificationRead(n.id).catch(() => {})
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
          <DropdownMenuContent className="w-56" align="end" forceMount>
            <DropdownMenuLabel className="leading-tight">
              <div className="text-sm font-semibold">{user?.display_name || user?.username || "Admin"}</div>
              <div className="text-xs text-muted-foreground">{user?.role || "session"}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer hover:bg-[#1a0b2e] hover:text-white focus:bg-[#1a0b2e] focus:text-white"
              onClick={() => navigate("/profile")}
            >
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem
              className="cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground"
              onClick={onLogout}
            >
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
