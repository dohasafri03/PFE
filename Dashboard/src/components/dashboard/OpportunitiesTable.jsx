import React, { useEffect, useMemo, useState } from "react"
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { ArrowUpDown, Search, FileSymlink, ExternalLink, Heart, Flame, Sparkles } from "lucide-react"


import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatShortDate, parseDeadlineDate } from "@/lib/date"
import { formatBudget } from "@/lib/budget"

const getLevelBadge = (level) => {
  switch (level) {
    case "HOT":
      return <Badge variant="destructive" className="bg-[#EF4444] hover:bg-[#EF4444]/90 text-white">HOT</Badge>
    case "WARM":
      return <Badge variant="default" className="bg-[#F97316] hover:bg-[#F97316]/90 text-white">WARM</Badge>
    case "COLD":
      return <Badge variant="secondary" className="bg-slate-200 text-slate-700 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200 dark:hover:bg-white/10">COLD</Badge>
    default:
      return <Badge variant="outline">{level}</Badge>
  }
}

const normalizeBuyer = (b) => {
  const s = String(b || "").trim()
  if (!s) return ""
  return s
    .replace(/^acheteur\s+public\b\s*[:\-]?\s*/i, "")
    .replace(/^acheteur\b\s*[:\-]?\s*/i, "")
    .trim()
}

const extractBuyerFromTitle = (titleRaw) => {
  const raw = String(titleRaw || "")
  if (!raw) return ""
  const m = raw.match(/\bacheteur\s+public\b\s*[:\-]?\s*([^\n\r]+)\s*$/i)
  if (!m) return ""
  return String(m[1] || "").trim()
}

const extractBuyerFromObjet = (objetRaw) => {
  const raw = String(objetRaw || "").replace(/\s+/g, " ").trim()
  if (!raw) return ""
  // Heuristics for sources that don't expose buyer/acheteur reliably.
  // Examples: "POUR LE COMPTE DE LA LOGDEV", "pour le compte du Conseil ..."
  const m = raw.match(/\bpour\s+le\s+compte\s+de\s+(?:la|le|l['’]|du|des)\s+([^.;,]+)\b/i)
  if (m && m[1]) return String(m[1]).trim()
  const m2 = raw.match(/\bpour\s+le\s+compte\s+de\s+([^.;,]+)\b/i)
  if (m2 && m2[1]) return String(m2[1]).trim()
  return ""
}

const resolveBuyerLabel = (rowObj) => {
  const direct =
    rowObj?.buyer ||
    rowObj?.acheteur ||
    rowObj?.organization ||
    rowObj?.organisme ||
    ""
  const fromTitle = extractBuyerFromTitle(rowObj?.title)
  const fromObjet = extractBuyerFromObjet(rowObj?.objet)
  const directNorm = normalizeBuyer(direct)
  const isDirectMissing = !directNorm || ["non identifie", "non identifié", "-", "n/a"].includes(directNorm.toLowerCase())
  const out = normalizeBuyer((isDirectMissing ? "" : directNorm) || fromTitle || fromObjet)
  return out || "Non identifie"
}

const parseSimilarityScore = (similarityScore) =>
  typeof similarityScore === "number" ? similarityScore : parseFloat(similarityScore || "0")

const isHotOpportunity = (row) => String(row?.level || "").trim().toUpperCase() === "HOT"

const isRecommendedOpportunity = (row) => parseSimilarityScore(row?.similarity_score) > 0.75

const getRecommendationTag = (similarityScore) => {
  const s = parseSimilarityScore(similarityScore)
  if (s > 0.75) {
    return (
      <span
        className="ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-green-400 ring-1 ring-green-500/40 shadow-[0_0_12px_rgba(34,197,94,0.35)]"
        title="Recommended"
      >
        Recommended
      </span>
    )
  }
  if (s > 0.6) {
    return (
      <span
        className="ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-orange-300 ring-1 ring-orange-500/40 shadow-[0_0_12px_rgba(249,115,22,0.30)]"
        title="Potential"
      >
        Potential
      </span>
    )
  }
  return (
    <span
      className="ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-muted-foreground ring-1 ring-border"
      title="Normal"
    >
      Normal
    </span>
  )
}

const getScoreBarStyle = (score) => {
  const s = typeof score === "number" ? score : parseFloat(score || "0")
  // Alexsys strip palette: teal / blue / mauve
  if (s >= 6) return "bg-[#6C63FF]"     // mauve
  if (s >= 3) return "bg-[#3B82F6]"     // blue
  return "bg-[#00C2D1]"                 // teal
}

const DOMAIN_STYLES = {
  AI: "bg-purple-500/15 text-purple-700 dark:text-purple-200 ring-1 ring-purple-500/25",
  DATA: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-200 ring-1 ring-cyan-500/25",
  CLOUD: "bg-sky-500/15 text-sky-700 dark:text-sky-200 ring-1 ring-sky-500/25",
  DEV: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-200 ring-1 ring-emerald-500/25",
  CYBERSECURITY: "bg-red-500/15 text-red-700 dark:text-red-200 ring-1 ring-red-500/25",
}

const normalizeDomainKey = (value) => {
  const key = String(value || "").trim().toUpperCase()
  if (!key) return ""
  if (key === "CYBER") return "CYBERSECURITY"
  return Object.prototype.hasOwnProperty.call(DOMAIN_STYLES, key) ? key : ""
}

const getColoredDomains = (domains, service) => {
  const out = []
  const seen = new Set()

  const push = (value) => {
    const key = normalizeDomainKey(value)
    if (!key || seen.has(key)) return
    seen.add(key)
    out.push(key)
  }

  if (Array.isArray(domains)) {
    domains.forEach(push)
  } else if (domains) {
    push(domains)
  }

  String(service || "")
    .split(/[\/,|]/)
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach(push)

  return out
}

const DomainTags = ({ domains, service }) => {
  const list = getColoredDomains(domains, service)
  if (!list.length) return null
  return (
    <div className="flex flex-wrap gap-1" title={list.join(" / ")}>
      {list.slice(0, 3).map((d) => {
        const key = String(d || "").toUpperCase()
        const cls = DOMAIN_STYLES[key] || "bg-foreground/5 text-muted-foreground ring-1 ring-border"
        return (
          <span
            key={key}
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${cls}`}
            title={`Domain: ${key}`}
          >
            {key === "CYBERSECURITY" ? "CYBER" : key}
          </span>
        )
      })}
    </div>
  )
}

export function OpportunitiesTable({ data, onRowClick, onToggleLike, onVisibleDataChange, profile = "GLOBAL" }) {
  const [sorting, setSorting] = useState([])
  const [globalFilter, setGlobalFilter] = useState("")
  const [likedOnly, setLikedOnly] = useState(false)
  const [serviceFilter, setServiceFilter] = useState("ALL")
  const [quickFilter, setQuickFilter] = useState(null) // null | "HOT" | "RECOMMENDED"

  const isGlobal = String(profile || "").trim().toUpperCase() === "GLOBAL"

  const likedCount = useMemo(() => data.filter((d) => !!d.liked).length, [data])
  const hotCount = useMemo(() => (data || []).filter(isHotOpportunity).length, [data])
  const recommendedCount = useMemo(() => (data || []).filter(isRecommendedOpportunity).length, [data])

  const serviceOptions = useMemo(() => {
    const set = new Set()
    for (const o of (data || [])) {
      const raw = (o?.service || "").toString()
      if (!raw) continue
      raw.split("/").forEach((p) => {
        const t = p.trim()
        if (t) set.add(t.toUpperCase())
      })
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [data])

  const tableData = useMemo(() => {
    let rows = likedOnly ? (data || []).filter((d) => !!d.liked) : (data || [])
    if (isGlobal && serviceFilter !== "ALL") {
      rows = rows.filter((o) => {
        const parts = (o?.service || "")
          .toString()
          .toUpperCase()
          .split("/")
          .map((p) => p.trim())
          .filter(Boolean)
        return parts.includes(serviceFilter)
      })
    }
    if (quickFilter === "HOT") {
      rows = rows.filter(isHotOpportunity)
    } else if (quickFilter === "RECOMMENDED") {
      rows = rows.filter(isRecommendedOpportunity)
    }
    return rows
  }, [data, likedOnly, serviceFilter, isGlobal, quickFilter])

  const columns = [
    {
      accessorKey: "reference",
      header: "Référence",
      cell: ({ row }) => <div className="font-medium text-xs">{row.getValue("reference")}</div>,
    },
    {
      accessorKey: "url",
      header: "URL",
      cell: ({ row }) => {
        const url = row.getValue("url")
        const enabled = typeof url === "string" && url.trim().length > 0
        return (
          <button
            type="button"
            className={enabled ? "text-primary" : "text-muted-foreground opacity-50 cursor-not-allowed"}
            title={enabled ? "Open original opportunity" : "URL missing"}
            onClick={(e) => {
              e.stopPropagation()
              if (!enabled) return
              window.open(url, "_blank", "noreferrer")
            }}
            aria-label="Open original opportunity"
            disabled={!enabled}
          >
            <ExternalLink className="h-4 w-4" />
          </button>
        )
      },
    },
    {
      accessorKey: "title",
      header: "Titre",
      cell: ({ row }) => (
        <div className="max-w-[240px] truncate" title={row.getValue("title")}>
          {row.getValue("title")}
        </div>
      ),
    },
    {
      accessorKey: "service",
      header: "Service",
      cell: ({ row }) => {
        const v = row.getValue("service") || ""
        const coloredDomains = getColoredDomains(row.original?.domains || row.original?.domain, v)
        return (
          <div className="max-w-[160px]" title={v}>
            {coloredDomains.length ? (
              <DomainTags domains={row.original?.domains || row.original?.domain} service={v} />
            ) : (
              <div className="text-muted-foreground">-</div>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: "buyer",
      header: "Organisme",
      cell: ({ row }) => {
        const label = resolveBuyerLabel(row.original)
        return (
          <div className="max-w-[240px] truncate" title={label}>
            {label}
          </div>
        )
      },
    },
    {
      accessorKey: "descriptionTechnique",
      header: "Desc. technique",
      cell: ({ row }) => {
        const v = row.getValue("descriptionTechnique") || ""
        return (
          <div className="max-w-[260px] truncate" title={v}>
            {v || "-"}
          </div>
        )
      },
    },
    {
      accessorKey: "descriptionFonctionnelle",
      header: "Desc. fonctionnelle",
      cell: ({ row }) => {
        const v = row.getValue("descriptionFonctionnelle") || ""
        return (
          <div className="max-w-[260px] truncate" title={v}>
            {v || "-"}
          </div>
        )
      },
    },
    {
      accessorKey: "requirements",
      header: "Requirements",
      cell: ({ row }) => {
        const reqs = row.getValue("requirements") || []
        const text = Array.isArray(reqs) ? reqs.join(" | ") : String(reqs || "")
        return (
          <div className="max-w-[240px] truncate" title={text}>
            {text || "-"}
          </div>
        )
      },
    },
    {
      accessorKey: "budget",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="-ml-4 h-8 data-[state=open]:bg-accent"
          >
            Budget
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        )
      },
      cell: ({ row }) => <div>{formatBudget(row.getValue("budget"))}</div>,
    },
    {
      accessorKey: "deadline",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="-ml-4 h-8"
          >
            Deadline
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        )
      },
      cell: ({ row }) => {
        return <div>{formatShortDate(row.getValue("deadline"))}</div>
      },
      sortingFn: (rowA, rowB, columnId) => {
        const a = parseDeadlineDate(rowA.getValue(columnId))
        const b = parseDeadlineDate(rowB.getValue(columnId))
        const at = a ? a.getTime() : Infinity
        const bt = b ? b.getTime() : Infinity
        return at === bt ? 0 : at > bt ? 1 : -1
      },
    },
    {
      accessorKey: "score",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="-ml-4 h-8"
          >
            Score
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        )
      },
      cell: ({ row }) => (
        <div
          className="flex items-center gap-2"
          title="Final score = keywords + budget + deadline + similarity"
        >
          <div className="w-20 h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full ${getScoreBarStyle(row.getValue("score"))}`}
              style={{ width: `${Math.max(0, Math.min(100, (Number(row.getValue("score")) || 0) * 10))}%` }}
            />
          </div>
          <span className="text-xs font-semibold">{row.getValue("score")}</span>
        </div>
      ),
    },
    {
      accessorKey: "level",
      header: "Niveau",
      cell: ({ row }) => (
        <div className="flex items-center">
          {getLevelBadge(row.getValue("level"))}
          {getRecommendationTag(row.original.similarity_score)}
        </div>
      ),
    },
    {
      id: "actions",
      cell: ({ row }) => (
        <div className="flex gap-2 relative">
          <Button variant="ghost" size="icon" onClick={() => onRowClick(row.original)} title="Voir details">
            <FileSymlink className="h-4 w-4 text-primary" />
          </Button>
        </div>
      ),
    },
    {
      id: "like",
      header: "Like",
      cell: ({ row }) => {
        const liked = !!row.original.liked
        return (
          <button
            type="button"
            className={liked ? "text-red-500" : "text-muted-foreground hover:text-red-500"}
            title={liked ? "Unlike" : "Like"}
            onClick={(e) => {
              e.stopPropagation()
              onToggleLike?.(row.original)
            }}
            aria-label="Toggle like"
          >
            <Heart className={`h-4 w-4 transition-transform active:scale-125 ${liked ? "fill-current scale-110" : "scale-100"}`} />
          </button>
        )
      },
    },
  ]

  const table = useReactTable({
    data: tableData,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onSortingChange: setSorting,
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: {
      sorting,
      globalFilter,
    },
    onGlobalFilterChange: setGlobalFilter,
  })

  useEffect(() => {
    if (typeof onVisibleDataChange !== "function") return
    const rows = table.getFilteredRowModel().rows || []
    const byId = new Map()
    for (const r of rows) {
      const o = r?.original
      const key = String(o?.id || o?.reference || "").trim()
      if (!key) continue
      if (!byId.has(key)) byId.set(key, o)
    }
    onVisibleDataChange(Array.from(byId.values()))
  }, [table, onVisibleDataChange, globalFilter, likedOnly, serviceFilter, quickFilter, tableData])

  return (
    <div className="min-w-0 max-w-full space-y-4">
      <div className="flex flex-col gap-3 py-4 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
        <div className="relative min-w-0 w-full flex-1 sm:max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search opportunities..."
            value={globalFilter ?? ""}
            onChange={(event) => setGlobalFilter(event.target.value)}
            className="pl-8"
          />
        </div>

        {isGlobal ? (
          <div className="w-full min-w-0 sm:w-[200px] sm:shrink-0">
            <Select value={serviceFilter} onValueChange={setServiceFilter}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Service: All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All services</SelectItem>
                {serviceOptions.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}

        <Button
          type="button"
          variant="outline"
          className={`w-full shrink-0 border transition-all duration-200 sm:w-auto ${
            quickFilter === "HOT"
              ? "border-red-500/60 bg-gradient-to-r from-red-500/15 to-orange-500/15 text-red-700 shadow-[0_0_18px_rgba(239,68,68,0.22)] hover:from-red-500/20 hover:to-orange-500/20 dark:border-red-400/50 dark:from-red-500/25 dark:to-orange-500/20 dark:text-red-200 dark:shadow-[0_0_22px_rgba(239,68,68,0.28)]"
              : "border-border hover:border-red-500/35 hover:bg-red-500/5 dark:hover:border-red-400/30 dark:hover:bg-red-500/10"
          }`}
          onClick={() => setQuickFilter((f) => (f === "HOT" ? null : "HOT"))}
          title="Afficher uniquement les opportunités HOT"
          aria-pressed={quickFilter === "HOT"}
        >
          <Flame className={`mr-2 h-4 w-4 ${quickFilter === "HOT" ? "text-red-600 dark:text-red-300" : "text-red-500/80"}`} />
          Hot opportunities ({hotCount})
        </Button>

        <Button
          type="button"
          variant="outline"
          className={`w-full shrink-0 border transition-all duration-200 sm:w-auto ${
            quickFilter === "RECOMMENDED"
              ? "border-emerald-500/60 bg-gradient-to-r from-emerald-500/15 to-teal-500/15 text-emerald-800 shadow-[0_0_18px_rgba(16,185,129,0.22)] hover:from-emerald-500/20 hover:to-teal-500/20 dark:border-emerald-400/50 dark:from-emerald-500/25 dark:to-teal-500/20 dark:text-emerald-200 dark:shadow-[0_0_22px_rgba(16,185,129,0.28)]"
              : "border-border hover:border-emerald-500/35 hover:bg-emerald-500/5 dark:hover:border-emerald-400/30 dark:hover:bg-emerald-500/10"
          }`}
          onClick={() => setQuickFilter((f) => (f === "RECOMMENDED" ? null : "RECOMMENDED"))}
          title="Afficher uniquement les opportunités recommandées (score > 75 %)"
          aria-pressed={quickFilter === "RECOMMENDED"}
        >
          <Sparkles
            className={`mr-2 h-4 w-4 ${
              quickFilter === "RECOMMENDED" ? "text-emerald-600 dark:text-emerald-300" : "text-emerald-500/80"
            }`}
          />
          Recommended ({recommendedCount})
        </Button>

        <Button
          type="button"
          variant="outline"
          className={`w-full shrink-0 border transition-all duration-200 sm:w-auto ${
            likedOnly
              ? "border-rose-500/60 bg-gradient-to-r from-rose-500/15 to-pink-500/15 text-rose-800 shadow-[0_0_18px_rgba(244,63,94,0.22)] hover:from-rose-500/20 hover:to-pink-500/20 dark:border-rose-400/50 dark:from-rose-500/25 dark:to-pink-500/20 dark:text-rose-200 dark:shadow-[0_0_22px_rgba(244,63,94,0.28)]"
              : "border-border hover:border-rose-500/35 hover:bg-rose-500/5 dark:hover:border-rose-400/30 dark:hover:bg-rose-500/10"
          }`}
          onClick={() => setLikedOnly((v) => !v)}
          title="Afficher uniquement les opportunités likées"
          aria-pressed={likedOnly}
        >
          <Heart
            className={`mr-2 h-4 w-4 ${
              likedOnly
                ? "fill-rose-600 text-rose-600 dark:fill-rose-300 dark:text-rose-300"
                : "text-rose-500/80"
            }`}
          />
          {likedOnly ? "Liked only" : "Show liked"} ({likedCount})
        </Button>
      </div>
      <div className="max-w-full min-w-0 overflow-x-auto overscroll-x-contain rounded-3xl border border-black/5 bg-[#F3F4F6] shadow-sm dark:border-white/10 dark:bg-white/5 dark:shadow-[0_18px_70px_rgba(0,0,0,0.45)]">
        <Table className="min-w-[1600px] text-[13.5px]">
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                  className={`cursor-pointer hover:bg-foreground/5 ${row.original?.liked ? "bg-red-500/5" : ""}`}
                  onClick={() => onRowClick(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className="align-top">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-end space-x-2 py-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
