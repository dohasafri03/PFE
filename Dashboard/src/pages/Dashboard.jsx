import React, { useMemo, useState, useEffect, useRef } from "react"
import { useLocation } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Layout } from "@/components/layout/Layout"
import { KPICards } from "@/components/dashboard/KPICards"
import { Charts } from "@/components/dashboard/Charts"
import { OpportunitiesTable } from "@/components/dashboard/OpportunitiesTable"
import { useAuth } from "@/context/AuthContext"
import { PROFILE_THEME, filterOpportunities, normalizeProfileSelection } from "@/lib/profile"
import {
  addProfileActivity,
  fetchOpportunities,
  toggleLike,
} from "@/services/api"
import { Button } from "@/components/ui/button"
import { Loader2, ExternalLink, Heart, Sparkles, Timer, BrainCircuit, Database } from "lucide-react"
import { formatShortDate, toDeadlineComparableDate } from "@/lib/date"
import { formatBudget } from "@/lib/budget"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export function Dashboard() {
  const location = useLocation()
  const { user } = useAuth()
  const [allData, setAllData] = useState([])
  const [loading, setLoading] = useState(true)
  const [profileLoading, setProfileLoading] = useState(false)
  const [selectedItem, setSelectedItem] = useState(null)
  const [detailTab, setDetailTab] = useState("overview")
  const [subFilter, setSubFilter] = useState("ALL") // DATA only: ALL | AI
  const [visibleData, setVisibleData] = useState(null)
  const [likePending, setLikePending] = useState(() => new Set())
  const lastViewedIdRef = useRef(null)
  const openedFromNotifRef = useRef(false)

  const normalizeTitle = (t) => {
    const s = String(t || "").replace(/\s+/g, " ").trim()
    if (!s) return ""
    const parts = s.split(" - ").map((p) => p.trim()).filter(Boolean)
    if (parts.length === 2 && parts[0].toLowerCase() === parts[1].toLowerCase()) return parts[0]
    // Some sources repeat the same (truncated) title twice like: "X... X..."
    const ell = s.includes("…") ? "…" : "..."
    if (s.includes(ell)) {
      const segs = s
        .split(ell)
        .map((p) => p.replace(/\s+/g, " ").trim())
        .filter(Boolean)
      if (segs.length >= 2) {
        const first = String(segs[0] || "").trim()
        const last = String(segs[segs.length - 1] || "").trim()
        const a = first.toLowerCase()
        const b = last.toLowerCase()
        // Exact duplicate.
        if (a && a === b) return first
        // Truncated duplicate: one side is a prefix of the other.
        if (a && b && (a.startsWith(b) || b.startsWith(a))) {
          return (first.length >= last.length) ? first : last
        }
      }
    }
    return s
  }

  const normalizeBuyer = (b) => {
    const s = String(b || "").trim()
    if (!s) return "-"
    return s.replace(/^acheteur\s+public\s+/i, "").trim() || "-"
  }

  const normalizeExternalUrl = (u) => {
    const raw = String(u || "").trim()
    if (!raw) return ""
    if (/^https?:\/\//i.test(raw)) return raw
    if (raw.startsWith("//")) return `https:${raw}`
    // Common case: backend/portal provides a host/path without scheme
    return `https://${raw}`
  }

  const profile = useMemo(() => {
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
    return sel.profile
  }, [user?.profile, user?.sub_profile])

  const effectiveSubProfile = useMemo(() => {
    const fromUserSub = String(user?.sub_profile || "").trim()
    let storedSub = ""
    try {
      storedSub = localStorage.getItem("marche_ai_sub_profile") || ""
    } catch (_) {}
    const sel = normalizeProfileSelection({
      profile,
      sub_profile: fromUserSub || storedSub || "",
    })
    return sel.sub_profile
  }, [profile, user?.sub_profile])

  // Reset DATA-only subfilter when switching profiles.
  useEffect(() => {
    if (String(profile || "").toUpperCase() !== "DATA") setSubFilter("ALL")
  }, [profile])

  useEffect(() => {
    setProfileLoading(true)
    // Fetch a broad list once; filtering is done client-side (keeps DATA including AI).
    fetchOpportunities("GLOBAL")
      .then((res) => setAllData(res))
      .finally(() => {
        setProfileLoading(false)
        setLoading(false)
      })
  }, [user?.username])

  const data = useMemo(() => {
    // If user is DATA with sub_profile=AI (ai account), default to Only AI view.
    const sf = (String(profile || "").toUpperCase() === "DATA" && String(effectiveSubProfile || "").toUpperCase() === "AI")
      ? "AI"
      : subFilter
    const filtered = filterOpportunities(allData, { profile, subFilter: sf })

    const now = new Date()
    now.setHours(0, 0, 0, 0)

    const activeOnly = (Array.isArray(filtered) ? filtered : []).filter((o) => {
      const dt = toDeadlineComparableDate(o?.deadline)
      // Keep only opportunities with a valid, non-expired deadline.
      if (!dt) return false
      return dt >= now
    })

    const dedupeById = (arr) => {
      const byId = new Map()
      for (const o of (Array.isArray(arr) ? arr : [])) {
        const key = String(o?.id || o?.reference || "").trim()
        if (!key) continue
        if (!byId.has(key)) byId.set(key, o)
      }
      return Array.from(byId.values())
    }

    return dedupeById(activeOnly)
  }, [allData, profile, subFilter, effectiveSubProfile])

  // Align KPI/Charts counts with the table's visible (post-search/filter) rows.
  const analyticsData = Array.isArray(visibleData) ? visibleData : data

  const theme = useMemo(() => {
    const p = String(profile || "GLOBAL").toUpperCase()
    return PROFILE_THEME[p] || PROFILE_THEME.GLOBAL
  }, [profile])

  const headerMeta = useMemo(() => {
    const p = String(profile || "GLOBAL").toUpperCase()
    if (p === "DATA") {
      return {
        title: "Data & AI Opportunities Dashboard",
        subtitle: "Opportunités data + IA, avec filtre AI optionnel.",
        iconLeft: Database,
        iconRight: BrainCircuit,
        showAiBadge: false,
      }
    }
    if (p === "CLOUD") return { title: "Cloud Opportunities Dashboard", subtitle: "Focus sur Cloud / DevOps.", iconLeft: null, iconRight: null, showAiBadge: false }
    if (p === "DEV") return { title: "Development Opportunities Dashboard", subtitle: "Focus sur Développement / Software.", iconLeft: null, iconRight: null, showAiBadge: false }
    return { title: "Vue d'ensemble", subtitle: "Analysez et gérez vos opportunités d'appels d'offres publics IT.", iconLeft: null, iconRight: null, showAiBadge: false }
  }, [profile])

  const formatMoney = (amount, fallback = "-") => formatBudget(amount, fallback)

  useEffect(() => {
    const oid = location?.state?.openOpportunityId
    if (!oid || openedFromNotifRef.current) return
    if (!Array.isArray(data) || !data.length) return

    const found = data.find((o) => String(o.id) === String(oid) || String(o.reference) === String(oid))
    if (found) {
      openedFromNotifRef.current = true
      setSelectedItem(found)
    }
  }, [location?.state?.openOpportunityId, data])

  const handleToggleLike = async (item) => {
    if (!item?.id) return
    const id = String(item.id)
    if (likePending.has(id)) return

    // Optimistic UI update
    const nextLiked = !item.liked
    setLikePending((prev) => {
      const n = new Set(prev)
      n.add(id)
      return n
    })
    setAllData((prev) => (Array.isArray(prev) ? prev.map((o) => (o.id === item.id ? { ...o, liked: nextLiked } : o)) : prev))
    setSelectedItem((prev) => (prev && prev.id === item.id ? { ...prev, liked: nextLiked } : prev))

    try {
      // Send the desired state to make the operation idempotent (avoids double-toggle on retries/double-clicks).
      const res = await toggleLike(item.id, nextLiked)
      const liked = !!res.liked
      setAllData((prev) => (Array.isArray(prev) ? prev.map((o) => (o.id === item.id ? { ...o, liked } : o)) : prev))
      setSelectedItem((prev) => (prev && prev.id === item.id ? { ...prev, liked } : prev))
    } catch (e) {
      // Revert on failure
      setAllData((prev) => (Array.isArray(prev) ? prev.map((o) => (o.id === item.id ? { ...o, liked: !!item.liked } : o)) : prev))
      setSelectedItem((prev) => (prev && prev.id === item.id ? { ...prev, liked: !!item.liked } : prev))
      console.error(e)
    } finally {
      setLikePending((prev) => {
        const n = new Set(prev)
        n.delete(id)
        return n
      })
    }
  }

  useEffect(() => {
    if (!selectedItem) return

    // Best-effort activity log (don't block UI if it fails)
    if (selectedItem.id && lastViewedIdRef.current !== selectedItem.id) {
      lastViewedIdRef.current = selectedItem.id
      addProfileActivity({
        type: "viewed_opportunity",
        opportunity_id: selectedItem.id,
        title: selectedItem.title,
      }).catch(() => {})
    }
  }, [selectedItem])

  useEffect(() => {
    if (!selectedItem) return
    setDetailTab("overview")
  }, [selectedItem?.id])

  if (loading) {
    return (
      <Layout>
        <div className="flex h-[80vh] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </Layout>
    )
  }

  const contentKey = `${String(profile || "GLOBAL").toUpperCase()}_${String(subFilter || "ALL").toUpperCase()}`

  return (
    <Layout>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={contentKey}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="flex min-w-0 max-w-full flex-col gap-6"
        >
        <div className="alexsys-animated-header relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-r from-[#00C2D1] via-[#3B82F6] to-[#1a0b2e] p-5 text-white shadow-[0_18px_60px_rgba(0,0,0,0.35)] sm:p-6">
          <div className="pointer-events-none absolute inset-0 opacity-50">
            <div className="absolute -top-24 -left-24 h-64 w-64 rounded-full bg-white/10 blur-3xl" />
            <div className="absolute -bottom-28 -right-28 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
          </div>
          {/* Dark mauve shade on the right (match screenshot) */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-transparent to-[#1a0b2e]/85" />
          <div className="pointer-events-none absolute inset-0 opacity-35 mix-blend-overlay">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.22),transparent_45%),radial-gradient(circle_at_80%_30%,rgba(255,255,255,0.16),transparent_50%),linear-gradient(120deg,rgba(255,255,255,0.08),transparent_40%,rgba(255,255,255,0.10))]" />
          </div>
          <div className="relative z-10 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                {headerMeta.iconLeft ? <headerMeta.iconLeft className="h-5 w-5 opacity-90" /> : null}
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight truncate text-white drop-shadow-[0_10px_24px_rgba(0,0,0,0.35)]">
                  {headerMeta.title}
                </h1>
                {headerMeta.iconRight ? <headerMeta.iconRight className="h-5 w-5 opacity-90" /> : null}
              </div>
              <p className="mt-1 text-sm sm:text-base font-medium text-white/85 drop-shadow-[0_10px_24px_rgba(0,0,0,0.35)]">
                {headerMeta.subtitle}
              </p>

              {String(profile || "").toUpperCase() === "DATA" ? (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <div className="inline-flex rounded-full bg-black/20 border border-white/15 p-1 backdrop-blur">
                    <button
                      type="button"
                      className={`px-3 py-1 text-xs font-semibold rounded-full transition-colors ${subFilter === "ALL" ? "bg-white/20 ring-1 ring-white/10" : "hover:bg-white/10"}`}
                      onClick={() => setSubFilter("ALL")}
                    >
                      Data
                    </button>
                    <button
                      type="button"
                      className={`px-3 py-1 text-xs font-semibold rounded-full transition-colors ${subFilter === "AI" ? "bg-white/20 ring-1 ring-white/10" : "hover:bg-white/10"}`}
                      onClick={() => setSubFilter("AI")}
                    >
                      AI
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
            <div className="text-xs text-white/70">
              Profil actif: <span className="font-semibold text-white">{String(profile || "GLOBAL").toUpperCase()}</span>
              {effectiveSubProfile ? (
                <span className="ml-2">• sous-profil: <span className="font-semibold text-white">{String(effectiveSubProfile).toUpperCase()}</span></span>
              ) : null}
            </div>
          </div>
        </div>

        <KPICards data={analyticsData} profile={profile} />
        <Charts data={analyticsData} profile={profile} subProfile={effectiveSubProfile} subFilter={subFilter} />
        
        <div className={`mt-4 transition-opacity ${profileLoading ? "opacity-60" : "opacity-100"}`}>
          <h2 className="text-xl font-semibold tracking-tight mb-4">Liste des opportunités</h2>
          {profileLoading ? (
            <div className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur p-4">
              <div className="h-4 w-48 bg-white/10 rounded animate-pulse mb-3" />
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, idx) => (
                  <div key={idx} className="h-10 bg-white/5 border border-white/10 rounded-xl animate-pulse" />
                ))}
              </div>
            </div>
          ) : null}
          {!profileLoading && Array.isArray(data) && data.length === 0 ? (
            <div className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur p-6 text-sm text-muted-foreground">
              {String(profile || "").toUpperCase() === "DATA" && subFilter === "AI"
                ? "No AI opportunities found"
                : "Aucune opportunité trouvée pour ce profil."}
            </div>
          ) : null}
          {!profileLoading ? (
            <div className="-mx-4 md:-mx-6 lg:-mx-8">
              <div className="px-4 md:px-6 lg:px-8">
                <OpportunitiesTable
                  data={data}
                  profile={profile}
                  onRowClick={(item) => setSelectedItem(item)}
                  onToggleLike={handleToggleLike}
                  onVisibleDataChange={setVisibleData}
                />
              </div>
            </div>
          ) : null}
        </div>

        <Dialog open={!!selectedItem} onOpenChange={() => setSelectedItem(null)}>
          <DialogContent className="w-[95vw] sm:max-w-4xl max-h-[85vh] overflow-y-auto border-black/10 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] dark:border-white/10 dark:bg-[#050915] dark:shadow-[0_30px_120px_rgba(0,0,0,0.78)]">
            {selectedItem && (
              <>
                <DialogHeader className="sr-only">
                  <DialogTitle>{normalizeTitle(selectedItem.title)}</DialogTitle>
                  <DialogDescription>
                    {selectedItem.buyer}
                    {selectedItem.service ? ` - Service: ${selectedItem.service}` : ""}
                    {" - "}Reference: {selectedItem.reference || selectedItem.id}
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-2">
                  {(() => {
                    const extractBuyerFromTitle = (titleRaw) => {
                      const raw = String(titleRaw || "")
                      if (!raw) return { title: "", buyer: "" }
                      // Handle cases where source appends a buyer line inside the title (often separated by newline)
                      // e.g. "Some title ...\nAcheteur public SOCIETE XYZ"
                      const m = raw.match(/([\s\S]*?)\bacheteur\s+public\b\s*[:\-]?\s*([^\n\r]+)\s*$/i)
                      if (!m) return { title: raw, buyer: "" }
                      const t = String(m[1] || "").replace(/\s+/g, " ").trim()
                      const b = String(m[2] || "").trim()
                      return { title: t || raw, buyer: b }
                    }

                    const extracted = extractBuyerFromTitle(selectedItem.title)
                    const displayTitle = normalizeTitle(extracted.title || selectedItem.title)
                    const buyerFromTitle = extracted.buyer || ""
                    const buyerDirect = normalizeBuyer(selectedItem.buyer)
                    const buyerIsMissing = !buyerDirect || ["non identifie", "non identifié", "-", "n/a"].includes(String(buyerDirect).toLowerCase())
                    const displayBuyer = buyerIsMissing ? normalizeBuyer(buyerFromTitle) : buyerDirect

                    const sim = Number(selectedItem.similarity_score || 0)
                    const recommended = sim > 0.75
                    const potential = sim > 0.6 && sim <= 0.75

                    const level = String(selectedItem.level || "COLD").toUpperCase()
                    const levelCls =
                      level === "HOT"
                        ? "bg-red-500/10 text-red-700 border-red-500/25 dark:bg-red-500/15 dark:text-red-200 dark:border-red-500/30 shadow-[0_0_16px_rgba(239,68,68,0.22)] dark:shadow-[0_0_16px_rgba(239,68,68,0.35)] animate-pulse"
                        : level === "WARM"
                        ? "bg-orange-500/10 text-orange-700 border-orange-500/25 dark:bg-orange-500/15 dark:text-orange-200 dark:border-orange-500/30 shadow-[0_0_16px_rgba(249,115,22,0.18)] dark:shadow-[0_0_16px_rgba(249,115,22,0.30)]"
                        : "bg-blue-500/10 text-blue-700 border-blue-500/25 dark:bg-blue-500/15 dark:text-blue-200 dark:border-blue-500/30 shadow-[0_0_16px_rgba(59,130,246,0.14)] dark:shadow-[0_0_16px_rgba(59,130,246,0.25)]"

                    const deadlineCmp = toDeadlineComparableDate(selectedItem.deadline)
                    const now = new Date()
                    const daysLeft = deadlineCmp
                      ? Math.ceil((deadlineCmp.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
                      : null
                    const countdownTone =
                      daysLeft == null
                        ? "text-muted-foreground"
                        : daysLeft < 0
                        ? "text-red-700 dark:text-red-300"
                        : daysLeft <= 5
                        ? "text-orange-700 dark:text-orange-200"
                        : "text-green-700 dark:text-green-300"
                    const countdownLabel =
                      daysLeft == null ? "N/A" : daysLeft < 0 ? "Expired" : `${daysLeft} day(s) left`

                    const score = Number(selectedItem.score || 0)
                    const scorePct = Math.max(0, Math.min(100, score * 10))
                    const scoreTone = score >= 6 ? "bg-[#6C63FF]" : score >= 3 ? "bg-[#3B82F6]" : "bg-[#00C2D1]"

                    const progress = (value, toneClass) => (
                      <div className="w-full h-2 rounded-full bg-black/5 dark:bg-white/5 overflow-hidden">
                        <div
                          className={`h-full ${toneClass}`}
                          style={{ width: `${Math.max(0, Math.min(100, Number(value) || 0))}%` }}
                        />
                      </div>
                    )

                    const domains = selectedItem.domains || (selectedItem.sector ? [selectedItem.sector] : [])
                    const isSimilar = (o) =>
                      o.id !== selectedItem.id &&
                      Array.isArray(o.domains) &&
                      o.domains.some((d) => domains.includes(d))
                    const similar = (data || [])
                      .filter(isSimilar)
                      .sort((a, b) => (b.similarity_score || 0) - (a.similarity_score || 0))
                      .slice(0, 12)

                    return (
                      <>
                        <div className="rounded-2xl border border-black/5 bg-[#F3F4F6] p-4 shadow-sm dark:border-white/10 dark:bg-[#0B1220] dark:shadow-[0_18px_70px_rgba(0,0,0,0.45)] sm:p-5">
                          <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4 items-start">
                            <div className="min-w-0">
                              <div className="flex items-start justify-between gap-3">
                                <h2
                                  className="text-lg sm:text-xl font-semibold leading-snug text-foreground min-w-0 whitespace-normal break-words"
                                  title={displayTitle}
                                >
                                  {displayTitle}
                                </h2>
                                <div className="flex items-center gap-2 shrink-0">
                                  <Button
                                    variant={selectedItem.liked ? "default" : "outline"}
                                    size="icon"
                                    onClick={() => handleToggleLike(selectedItem)}
                                    title={selectedItem.liked ? "Unlike" : "Like"}
                                  >
                                    <Heart
                                      className={`h-4 w-4 transition-transform active:scale-125 ${selectedItem.liked ? "fill-current scale-110" : "scale-100"}`}
                                    />
                                  </Button>
                                  {normalizeExternalUrl(selectedItem.url) ? (
                                    <Button variant="outline" size="icon" asChild title="Open original opportunity">
                                      <a
                                        href={normalizeExternalUrl(selectedItem.url)}
                                        target="_blank"
                                        rel="noreferrer"
                                      >
                                        <ExternalLink className="h-4 w-4" />
                                      </a>
                                    </Button>
                                  ) : (
                                    <Button variant="outline" size="icon" disabled title="URL missing">
                                      <ExternalLink className="h-4 w-4" />
                                    </Button>
                                  )}
                                </div>
                              </div>

                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold border ${levelCls}`}>
                                  {level}
                                </span>
                                {recommended ? (
                                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold bg-green-500/12 text-green-800 border border-green-500/25 shadow-[0_0_14px_rgba(34,197,94,0.18)] dark:bg-green-500/15 dark:text-green-200 dark:border-green-500/30 dark:shadow-[0_0_14px_rgba(34,197,94,0.25)]">
                                    <Sparkles className="h-3.5 w-3.5" /> Recommended
                                  </span>
                                ) : potential ? (
                                  <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-orange-500/10 text-orange-800 border border-orange-500/25 dark:text-orange-200">
                                    Potential
                                  </span>
                                ) : null}
                                <span className="text-xs text-muted-foreground">
                                  {selectedItem.service ? `${selectedItem.service} • ` : ""}Ref: {selectedItem.reference || selectedItem.id}
                                </span>
                              </div>

                            </div>

                            <div className="grid gap-3">
                              <div className="rounded-xl border border-black/5 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-[#0F172A] dark:shadow-[0_16px_50px_rgba(0,0,0,0.40)]">
                                <div className="text-xs text-muted-foreground">Budget</div>
                                <div className="text-2xl font-bold mt-1">{formatMoney(selectedItem.budget)}</div>
                              </div>
                              <div className="rounded-xl border border-black/5 bg-white p-4 shadow-sm flex items-center justify-between gap-3 dark:border-white/10 dark:bg-[#0F172A] dark:shadow-[0_16px_50px_rgba(0,0,0,0.40)]">
                                <div>
                                  <div className="text-xs text-muted-foreground">Deadline</div>
                                  <div className="text-sm font-semibold mt-1">{formatShortDate(selectedItem.deadline)}</div>
                                </div>
                                <div className={`inline-flex items-center gap-2 text-xs font-semibold ${countdownTone}`}>
                                  <Timer className="h-4 w-4" />
                                  {countdownLabel}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-4">
                          <div className="space-y-4">
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                              <div className="rounded-xl border border-black/5 bg-white p-3 shadow-sm dark:border-white/10 dark:bg-[#0F172A]">
                                <div className="text-xs text-muted-foreground">Budget</div>
                                <div className="text-sm font-semibold mt-1">{formatMoney(selectedItem.budget)}</div>
                              </div>
                              <div className="rounded-xl border border-black/5 bg-white p-3 shadow-sm dark:border-white/10 dark:bg-[#0F172A]">
                                <div className="text-xs text-muted-foreground">Deadline</div>
                                <div className="text-sm font-semibold mt-1">{formatShortDate(selectedItem.deadline)}</div>
                              </div>
                              <div className="rounded-xl border border-black/5 bg-white p-3 shadow-sm dark:border-white/10 dark:bg-[#0F172A]">
                                <div className="text-xs text-muted-foreground">Score</div>
                                <div className="mt-2 flex items-center gap-2">
                                  <div className="flex-1">{progress(scorePct, scoreTone)}</div>
                                  <div className="text-xs font-semibold">{score}</div>
                                </div>
                              </div>
                            </div>

                            <div className="rounded-2xl border border-black/5 bg-white shadow-sm dark:border-white/10 dark:bg-[#0B1220] dark:shadow-[0_18px_70px_rgba(0,0,0,0.45)]">
                              <div className="flex items-center gap-2 p-2 border-b border-black/5 dark:border-white/10 overflow-x-auto">
                                {[
                                  { id: "overview", label: "Overview" },
                                  { id: "technical", label: "Technical Analysis" },
                                  { id: "functional", label: "Functional Analysis" },
                                  { id: "requirements", label: "Requirements" },
                                  { id: "similar", label: "Similar Opportunities" },
                                ].map((t) => (
                                  <button
                                    key={t.id}
                                    type="button"
                                    onClick={() => setDetailTab(t.id)}
                                    className={`px-3 py-2 text-sm rounded-xl whitespace-nowrap transition-colors ${detailTab === t.id ? "bg-black/5 text-foreground dark:bg-white/10 dark:text-white" : "text-muted-foreground hover:text-foreground hover:bg-black/5 dark:text-white/70 dark:hover:text-white dark:hover:bg-white/5"}`}
                                  >
                                    {t.label}
                                  </button>
                                ))}
                              </div>

                              <div className="p-4">
                                {detailTab === "overview" ? (
                                  <div className="grid gap-2 text-sm text-muted-foreground leading-relaxed">
                                    <div><span className="font-semibold text-foreground">Organisme:</span> {displayBuyer}</div>
                                    <div><span className="font-semibold text-foreground">Service:</span> {selectedItem.service || "-"}</div>
                                    <div><span className="font-semibold text-foreground">URL:</span> {selectedItem.url ? (
                                      <a
                                        className="text-primary hover:underline ml-1"
                                        href={normalizeExternalUrl(selectedItem.url)}
                                        target="_blank"
                                        rel="noreferrer"
                                      >
                                        Open source
                                      </a>
                                    ) : <span className="ml-1">-</span>}</div>
                                  </div>
                                ) : null}

                                {detailTab === "technical" ? (
                                  <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                                    {selectedItem.descriptionTechnique || "-"}
                                  </div>
                                ) : null}

                                {detailTab === "functional" ? (
                                  <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                                    {selectedItem.descriptionFonctionnelle || "-"}
                                  </div>
                                ) : null}

                                {detailTab === "requirements" ? (
                                  <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                                    {(Array.isArray(selectedItem.requirements)
                                      ? selectedItem.requirements.join(" | ")
                                      : selectedItem.requirements) || "-"}
                                  </div>
                                ) : null}

                                {detailTab === "similar" ? (
                                  <div className="space-y-3">
                                    {similar.length ? (
                                      <div className="flex gap-3 overflow-x-auto pb-2">
                                        {similar.map((o) => (
                                          <div key={o.id} className="min-w-[260px] max-w-[260px] rounded-2xl border border-black/5 bg-white p-3 transition-colors hover:bg-slate-50 dark:border-white/10 dark:bg-[#0F172A] dark:hover:bg-[#162032]">
                                            <div className="text-sm font-semibold leading-snug whitespace-normal break-words max-h-16 overflow-auto pr-1" title={o.title}>
                                              {o.title}
                                            </div>
                                            <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                                              <div>Similarity: <span className="text-foreground font-semibold">{Math.round((Number(o.similarity_score || 0)) * 100)}%</span></div>
                                              <div>Score: <span className="text-foreground font-semibold">{o.score ?? "-"}</span></div>
                                              <div>Deadline: <span className="text-foreground font-semibold">{formatShortDate(o.deadline)}</span></div>
                                            </div>
                                            <div className="mt-3 flex justify-end">
                                              <Button size="sm" variant="outline" onClick={() => setSelectedItem(o)}>Compare</Button>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <div className="text-sm text-muted-foreground">Aucune suggestion disponible.</div>
                                    )}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </div>

                        </div>
                      </>
                    )
                  })()}
                </div>
              </>
            )}
          </DialogContent>
        </Dialog>
        </motion.div>
      </AnimatePresence>
    </Layout>
  )
}
