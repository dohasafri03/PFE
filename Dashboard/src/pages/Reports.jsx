import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Layout } from "@/components/layout/Layout"
import { fetchDossiersIndex, getDownloadUrl } from "@/services/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Loader2, FileText, ArrowUpDown, Calendar, Filter } from "lucide-react"
import { toDeadlineComparableDate } from "@/lib/date"
import { useAuth } from "@/context/AuthContext"
import { normalizeProfileSelection } from "@/lib/profile"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

const docLinkBase =
  "inline-flex items-center rounded-md border px-2.5 py-1.5 text-xs font-semibold shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"

/** Distinct document kinds — readable in light & dark */
function documentKindTone(kind) {
  const k = String(kind || "").toLowerCase()
  if (k.includes("technique") || k === "tech") {
    return "border-sky-500/45 bg-sky-500/15 text-sky-950 hover:bg-sky-500/22 dark:border-sky-400/40 dark:bg-sky-500/20 dark:text-sky-50 dark:hover:bg-sky-500/30"
  }
  if (k.includes("administratif") || k.includes("admin")) {
    return "border-amber-500/45 bg-amber-500/15 text-amber-950 hover:bg-amber-500/22 dark:border-amber-400/40 dark:bg-amber-500/20 dark:text-amber-50 dark:hover:bg-amber-500/30"
  }
  if (k.includes("financier") || k.includes("financial")) {
    return "border-emerald-500/45 bg-emerald-500/15 text-emerald-950 hover:bg-emerald-500/22 dark:border-emerald-400/40 dark:bg-emerald-500/20 dark:text-emerald-50 dark:hover:bg-emerald-500/30"
  }
  if (k.includes("commerc")) {
    return "border-violet-500/45 bg-violet-500/15 text-violet-950 hover:bg-violet-500/22 dark:border-violet-400/40 dark:bg-violet-500/20 dark:text-violet-50 dark:hover:bg-violet-500/30"
  }
  return "border-border bg-muted/60 text-foreground hover:bg-muted/90 dark:bg-muted/25 dark:hover:bg-muted/40"
}

export function Reports() {
  const { user } = useAuth()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState([])
  const [query, setQuery] = useState("")
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState({ key: "generated_at", dir: "desc" }) // key: deadline | generated_at
  const [dateFrom, setDateFrom] = useState("")
  const [serviceFilter, setServiceFilter] = useState("ALL") // GLOBAL only
  const dateFromRef = useRef(null)

  const formatDeadline = (deadline) => {
    const d = toDeadlineComparableDate(deadline)
    if (!d) return "-"
    return d.toLocaleDateString("fr-FR")
  }

  const domainTone = (d) => {
    const key = String(d || "").toUpperCase()
    if (key === "AI") return "bg-purple-500/15 text-purple-700 dark:text-purple-200 ring-1 ring-purple-500/25"
    if (key === "DATA") return "bg-cyan-500/15 text-cyan-700 dark:text-cyan-200 ring-1 ring-cyan-500/25"
    if (key === "CLOUD") return "bg-sky-500/15 text-sky-700 dark:text-sky-200 ring-1 ring-sky-500/25"
    if (key === "DEV") return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-200 ring-1 ring-emerald-500/25"
    if (key === "CYBERSECURITY") return "bg-red-500/15 text-red-700 dark:text-red-200 ring-1 ring-red-500/25"
    return "bg-foreground/5 text-muted-foreground ring-1 ring-border"
  }

  const DomainTags = ({ domains }) => {
    const list = Array.isArray(domains) ? domains : []
    if (!list.length) return null
    return (
      <div className="mt-1 flex flex-wrap gap-1">
        {list.slice(0, 3).map((d) => {
          const key = String(d || "").toUpperCase()
          return (
            <span
              key={key}
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${domainTone(key)}`}
              title={`Service: ${key}`}
            >
              {key === "CYBERSECURITY" ? "CYBER" : key}
            </span>
          )
        })}
      </div>
    )
  }

  const toggleSort = (key) => {
    setSort((prev) => {
      if (prev.key === key) {
        return { key, dir: prev.dir === "asc" ? "desc" : "asc" }
      }
      // default: soonest deadline first, latest generation first
      return { key, dir: key === "deadline" ? "asc" : "desc" }
    })
  }

  useEffect(() => {
    setLoading(true)
    fetchDossiersIndex()
      .then((res) => {
        setItems(res.items || [])
        setError(null)
      })
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false))
  }, [])

  const profileSel = useMemo(() => {
    const sel = normalizeProfileSelection({ profile: user?.profile || "GLOBAL", sub_profile: user?.sub_profile })
    return sel
  }, [user?.profile, user?.sub_profile])

  const isGlobal = useMemo(() => {
    return String(profileSel.profile || "").toUpperCase() === "GLOBAL"
  }, [profileSel.profile])

  const filtered = useMemo(() => {
    // Keep only opportunities with an ongoing deadline (or unknown deadline).
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    const activeItems = (items || []).filter((it) => {
      const d = toDeadlineComparableDate(it.deadline)
      if (!d) return true
      return d >= now
    })

    // Profile-based filter (profile is selected at login).
    const profile = String(profileSel.profile || "").trim().toUpperCase() || "GLOBAL"
    const sub = String(profileSel.sub_profile || "").trim().toUpperCase() || ""
    const byProfile = (profile === "GLOBAL" || profile === "ALL")
      ? activeItems
      : activeItems.filter((it) => {
          const doms = Array.isArray(it.domains) ? it.domains : []
          const domUpper = doms.map((d) => String(d || "").toUpperCase())

          // DATA includes AI automatically.
          if (profile === "DATA") {
            const base = domUpper.includes("DATA") || domUpper.includes("AI")
            const svc = String(it.service || "").toUpperCase()
            const svcMatch = svc.includes("DATA") || svc.includes("AI")
            return base || svcMatch
          }

          if (domUpper.includes(profile)) return true

          // Fallback: infer from service string if domains missing.
          const svc = String(it.service || "").toUpperCase()
          if (!svc) return false
          // Handle CYBER label variants.
          if (profile === "CYBERSECURITY" && svc.includes("CYBER")) return true
          return svc.includes(profile)
        })

    const q = query.trim().toLowerCase()
    const withQuery = !q
      ? byProfile
      : byProfile.filter((it) => {
          const title = (it.title || "").toLowerCase()
          const folder = (it.folder || "").toLowerCase()
          return title.includes(q) || folder.includes(q)
        })

    const withDateFrom = dateFrom
      ? withQuery.filter((it) => {
          const d = toDeadlineComparableDate(it.deadline)
          if (!d) return true

          // Parse YYYY-MM-DD as a *local* date (avoid UTC offset shifting the boundary).
          const m = String(dateFrom || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/)
          const from = m
            ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 0, 0, 0, 0)
            : new Date(dateFrom)
          if (Number.isNaN(from.getTime())) return true

          return d.getTime() >= from.getTime()
        })
      : withQuery

    const withService = (isGlobal && String(serviceFilter || "ALL").toUpperCase() !== "ALL")
      ? withDateFrom.filter((it) => {
          const svc = String(it.service || "").toUpperCase()
          // allow "A / B" combined service values
          const parts = svc.split("/").map((p) => p.trim()).filter(Boolean)
          return parts.includes(String(serviceFilter).toUpperCase())
        })
      : withDateFrom

    const dir = sort.dir === "asc" ? 1 : -1
    return [...withService].sort((a, b) => {
      if (sort.key === "deadline") {
        const ad = toDeadlineComparableDate(a.deadline)
        const bd = toDeadlineComparableDate(b.deadline)
        const at = ad ? ad.getTime() : Number.POSITIVE_INFINITY
        const bt = bd ? bd.getTime() : Number.POSITIVE_INFINITY
        return at === bt ? 0 : at > bt ? dir : -dir
      }

      // generated_at (default)
      const ag = a.generated_at ? new Date(a.generated_at).getTime() : 0
      const bg = b.generated_at ? new Date(b.generated_at).getTime() : 0
      return ag === bg ? 0 : ag > bg ? dir : -dir
    })
  }, [items, query, sort, user?.profile, user?.sub_profile, profileSel.profile, profileSel.sub_profile, dateFrom, serviceFilter, isGlobal])

  const services = useMemo(() => {
    const set = new Set()
    ;(items || []).forEach((it) => {
      const svc = String(it?.service || "").trim()
      if (svc) set.add(svc.toUpperCase())
    })
    const list = Array.from(set).filter(Boolean).sort()
    return ["ALL", ...list.slice(0, 24)]
  }, [items])

  const summaries = useMemo(() => {
    const list = filtered || []
    const total = list.length
    const hot = list.filter((it) => String(it.level || "").toUpperCase() === "HOT").length
    return { total, hot }
  }, [filtered])

  // Pagination (client-side)
  const pageSize = 10
  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil((filtered?.length || 0) / pageSize))
  }, [filtered])

  useEffect(() => {
    setPage(1)
  }, [query, items?.length])

  const paged = useMemo(() => {
    const p = Math.min(Math.max(1, page), totalPages)
    const start = (p - 1) * pageSize
    return (filtered || []).slice(start, start + pageSize)
  }, [filtered, page, totalPages])

  return (
    <Layout>
      <div className="flex min-w-0 max-w-full flex-col gap-6">
        <div className="alexsys-animated-header relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-r from-[#00C2D1] via-[#3B82F6] to-[#1a0b2e] p-5 text-white shadow-[0_18px_60px_rgba(0,0,0,0.35)] sm:p-6">
          <div className="pointer-events-none absolute inset-0 opacity-50">
            <div className="absolute -top-24 -left-24 h-64 w-64 rounded-full bg-white/10 blur-3xl" />
            <div className="absolute -bottom-28 -right-28 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
          </div>
          {/* Dark mauve shade on the right (match Dashboard) */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-transparent to-[#1a0b2e]/85" />
          <div className="pointer-events-none absolute inset-0 opacity-35 mix-blend-overlay">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.22),transparent_45%),radial-gradient(circle_at_80%_30%,rgba(255,255,255,0.16),transparent_50%),linear-gradient(120deg,rgba(255,255,255,0.08),transparent_40%,rgba(255,255,255,0.10))]" />
          </div>
          <div className="relative z-10">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white drop-shadow-[0_10px_24px_rgba(0,0,0,0.35)]">
              Reports
            </h1>
            <p className="mt-1 text-sm sm:text-base font-medium text-white/85 drop-shadow-[0_10px_24px_rgba(0,0,0,0.35)]">
              Dossiers et documents générés par opportunité.
            </p>
          {profileSel?.profile && String(profileSel.profile).toUpperCase() !== "GLOBAL" ? (
            <div className="mt-2 text-xs text-muted-foreground">
              Profil actif: <span className="font-semibold text-foreground">{String(profileSel.profile).toUpperCase()}</span>
              {profileSel.sub_profile ? (
                <span className="ml-2">• sous-profil: <span className="font-semibold text-foreground">{String(profileSel.sub_profile).toUpperCase()}</span></span>
              ) : null}
            </div>
          ) : null}
          </div>
        </div>

        <div className="flex min-w-0 justify-center">
          <div className="w-full min-w-0 max-w-4xl rounded-3xl border border-black/5 bg-[#F3F4F6] p-4 shadow-sm dark:border-white/10 dark:bg-white/5 sm:p-6">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Filter className="h-4 w-4 text-sky-600 dark:text-sky-300" />
              Filters
            </div>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Search</div>
                <Input
                  placeholder="Titre ou référence..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="bg-background/70 border-border"
                />
              </div>
              <div className="space-y-1">
                <div className="text-xs text-muted-foreground">Deadline</div>
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    ref={dateFromRef}
                    className="pl-10 pr-10 bg-background/70 border-border focus:border-[#1a0b2e] focus:ring-2 focus:ring-[#1a0b2e]/25"
                  />
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-[#1a0b2e] hover:text-white focus:outline-none focus:ring-2 focus:ring-[#1a0b2e]/30"
                    onClick={() => {
                      const el = dateFromRef?.current
                      if (el?.showPicker) el.showPicker()
                      else el?.focus?.()
                    }}
                    title="Choisir une date"
                    aria-label="Choisir une date"
                  >
                    <Calendar className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {isGlobal ? (
                <div className="space-y-1">
                  <div className="text-xs text-muted-foreground">Service</div>
                  <Select value={serviceFilter} onValueChange={setServiceFilter}>
                    <SelectTrigger className="h-10 bg-background/70 border-border focus:ring-[#1a0b2e]/25 focus:border-[#1a0b2e]">
                      <SelectValue placeholder="Service: All" />
                    </SelectTrigger>
                    <SelectContent>
                      {services.map((s) => (
                        <SelectItem key={s} value={s}>
                          {s}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                className="border-border bg-background/60 hover:bg-[#1a0b2e] hover:border-[#1a0b2e] hover:text-white focus-visible:ring-[#1a0b2e]/25"
                onClick={() => {
                  setQuery("")
                  setDateFrom("")
                  setServiceFilter("ALL")
                }}
              >
                Reset
              </Button>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1 max-w-md hidden">
            <Input
              placeholder="Rechercher par titre ou référence..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        {error ? (
          <div className="rounded-xl border p-4 bg-card text-sm">
            <span className="font-semibold">Erreur:</span> {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex h-[50vh] items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <div className="max-w-full min-w-0 overflow-x-auto rounded-3xl border border-black/5 bg-[#F3F4F6] shadow-sm dark:border-white/10 dark:bg-white/5 dark:shadow-[0_16px_60px_rgba(0,0,0,0.25)]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Opportunité</TableHead>
                  <TableHead>
                    <Button
                      variant="ghost"
                      onClick={() => toggleSort("deadline")}
                      className="-ml-4 h-8"
                      title="Trier par deadline"
                    >
                      Deadline
                      <ArrowUpDown className="ml-2 h-4 w-4" />
                    </Button>
                  </TableHead>
                  <TableHead>
                    <Button
                      variant="ghost"
                      onClick={() => toggleSort("generated_at")}
                      className="-ml-4 h-8"
                      title="Trier par date de génération"
                    >
                      Généré
                      <ArrowUpDown className="ml-2 h-4 w-4" />
                    </Button>
                  </TableHead>
                  <TableHead>Documents</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length ? (
                  paged.map((it) => (
                    <TableRow key={it.folder} className="hover:bg-white/5 transition-colors">
                      <TableCell className="align-top">
                        <div className="font-medium">{it.title || it.folder}</div>
                        <div className="text-xs text-muted-foreground">Ref: {it.folder}</div>
                        {it.service ? (
                          <div className="mt-1 text-xs text-muted-foreground">
                            Service: <span className="text-foreground font-semibold">{it.service}</span>
                          </div>
                        ) : null}
                        <DomainTags domains={it.domains} />
                      </TableCell>
                      <TableCell className="align-top">
                        <div className="text-sm">{formatDeadline(it.deadline)}</div>
                      </TableCell>
                      <TableCell className="align-top">
                        <div className="text-sm">
                          {it.generated_at ? new Date(it.generated_at).toLocaleString("fr-FR") : "-"}
                        </div>
                      </TableCell>
                      <TableCell className="align-top">
                        <div className="flex flex-wrap gap-2">
                          {(it.documents || []).map((doc, idx) => (
                            <a
                              key={idx}
                              href={getDownloadUrl(doc.url)}
                              target="_blank"
                              rel="noreferrer"
                              className={cn(docLinkBase, documentKindTone(doc.kind))}
                            >
                              <FileText className="mr-2 h-4 w-4 shrink-0 opacity-90" />
                              {doc.kind} ({doc.ext.toUpperCase()})
                            </a>
                          ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={4} className="h-24 text-center">
                      Aucun résultat.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}

        {!loading && !error && filtered.length > pageSize ? (
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">
              Page {Math.min(Math.max(1, page), totalPages)} / {totalPages}{" "}
              {"\u2022"} {filtered.length} items
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </Layout>
  )
}
