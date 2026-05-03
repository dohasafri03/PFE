import React, { useEffect, useMemo, useState } from "react"
import { BarChart3, Flame, CalendarDays, Heart, Star, TrendingUp } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatShortDate, toDeadlineComparableDate } from "@/lib/date"
import { isAIOpportunity } from "@/lib/profile"

export function KPICards({ data, profile = "GLOBAL" }) {
  const [totals, setTotals] = useState({
    opportunities: 0,
    hotOpportunities: 0,
    nearestDeadline: null,
    nearestDeadlineRaw: null,
    daysToNearestDeadline: null,
    likedOpportunities: 0,
    recommendedOpportunities: 0,
    dataOpportunities: 0,
    aiOpportunities: 0,
    aiPct: 0,
  })

  useEffect(() => {
    const list = Array.isArray(data) ? data : []
    if (!list.length) {
      setTotals((prev) => ({
        ...prev,
        opportunities: 0,
        hotOpportunities: 0,
        likedOpportunities: 0,
        recommendedOpportunities: 0,
        nearestDeadline: "N/A",
        nearestDeadlineRaw: null,
        daysToNearestDeadline: null,
        dataOpportunities: 0,
        aiOpportunities: 0,
        aiPct: 0,
      }))
      return
    }

    const hotOppos = list.filter(d => d.level === "HOT")
    const likedOppos = list.filter(d => !!d.liked)
    const recommendedOppos = list.filter(d => (d.similarity_score || 0) > 0.75)
    
    // Nearest deadline (future)
    const now = new Date()
    const sortedDates = [...list]
      .map(d => toDeadlineComparableDate(d.deadline))
      .filter(d => d && d >= now)
      .sort((a, b) => a - b)
    const nearest = sortedDates[0] || null
    const daysLeft = nearest ? Math.ceil((nearest.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)) : null

    const p = String(profile || "GLOBAL").toUpperCase()
    const aiCount = list.filter(isAIOpportunity).length
    const dataCount = p === "DATA"
      ? Math.max(0, list.length - aiCount)
      : 0
    const pct = list.length ? Math.round((aiCount * 100) / list.length) : 0

    setTotals({
      opportunities: list.length,
      hotOpportunities: hotOppos.length,
      likedOpportunities: likedOppos.length,
      recommendedOpportunities: recommendedOppos.length,
      nearestDeadline: nearest ? formatShortDate(nearest) : "N/A",
      nearestDeadlineRaw: nearest,
      daysToNearestDeadline: daysLeft,
      dataOpportunities: dataCount,
      aiOpportunities: aiCount,
      aiPct: pct,
    })
  }, [data, profile])

  const trend = useMemo(() => {
    // Persist last-run totals for "+X vs last run" without changing API.
    const key = "marche_ai_last_run_totals_v1"
    const current = {
      opportunities: Number(totals.opportunities || 0),
      hot: Number(totals.hotOpportunities || 0),
      liked: Number(totals.likedOpportunities || 0),
      recommended: Number(totals.recommendedOpportunities || 0),
      ts: Date.now(),
    }
    let prev = null
    try {
      const raw = localStorage.getItem(key)
      prev = raw ? JSON.parse(raw) : null
      localStorage.setItem(key, JSON.stringify(current))
    } catch (_) {
      prev = null
    }
    const delta = (a, b) => (Number(a || 0) - Number(b || 0))
    return {
      opp: prev ? delta(current.opportunities, prev.opportunities) : null,
      hot: prev ? delta(current.hot, prev.hot) : null,
      liked: prev ? delta(current.liked, prev.liked) : null,
      rec: prev ? delta(current.recommended, prev.recommended) : null,
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totals.opportunities, totals.hotOpportunities, totals.likedOpportunities, totals.recommendedOpportunities])

  const miniLine = (color = "#3B82F6") => (
    <svg viewBox="0 0 100 32" className="h-6 w-20">
      <path
        d="M2 26 C 18 18, 24 22, 36 14 S 62 10, 74 16 S 86 24, 98 8"
        fill="none"
        stroke={color}
        strokeWidth="2.5"
        strokeLinecap="round"
        opacity="0.9"
      />
      <path
        d="M2 26 C 18 18, 24 22, 36 14 S 62 10, 74 16 S 86 24, 98 8 L 98 32 L 2 32 Z"
        fill={color}
        opacity="0.10"
      />
    </svg>
  )

  const MetricCard = ({ icon, title, value, subtext, tone = "blue", right }) => {
    const tones = {
      blue: {
        ring: "ring-blue-500/20",
        iconBg: "bg-blue-500/10",
        iconText: "text-blue-600 dark:text-blue-400",
      },
      red: {
        ring: "ring-red-500/20",
        iconBg: "bg-red-500/10",
        iconText: "text-red-600 dark:text-red-400",
      },
      purple: {
        ring: "ring-[#6C63FF]/20",
        iconBg: "bg-[#6C63FF]/10",
        iconText: "text-[#6C63FF]",
      },
      pink: {
        ring: "ring-pink-500/20",
        iconBg: "bg-pink-500/10",
        iconText: "text-pink-600 dark:text-pink-400",
      },
      green: {
        ring: "ring-green-500/20",
        iconBg: "bg-green-500/10",
        iconText: "text-green-600 dark:text-green-400",
      },
    }
    const t = tones[tone] || tones.blue
    return (
      <Card
        className={[
          "group rounded-xl p-0 ring-1 transition-all duration-200",
          // Light mode: match the soft neutral card background from the reference
          "bg-[#F3F4F6] border border-black/5 shadow-sm",
          // Hover: premium deep mauve for all KPI cards
          "hover:bg-[#1a0b2e] hover:border-white/10 hover:text-white",
          "hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(15,23,42,0.10)]",
          // Dark mode: keep existing glassy look
          "dark:bg-white/5 dark:border-white/10 dark:shadow-[0_18px_60px_rgba(0,0,0,0.45)]",
          t.ring,
        ].join(" ")}
      >
        <CardContent className="p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3 min-w-0">
              <div className={`h-10 w-10 rounded-xl ${t.iconBg} ring-1 ring-border flex items-center justify-center transition-colors group-hover:bg-white/10 group-hover:ring-white/20`}>
                <div className={`${t.iconText} transition-colors group-hover:text-white`}>{icon}</div>
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-muted-foreground transition-colors group-hover:text-white/80">{title}</div>
                <div className="mt-1 text-2xl font-bold tracking-tight text-foreground truncate transition-colors group-hover:text-white">{value}</div>
                {subtext ? <div className="mt-1 text-xs text-muted-foreground transition-colors group-hover:text-white/70">{subtext}</div> : null}
              </div>
            </div>
            {right ? <div className="shrink-0">{right}</div> : null}
          </div>
        </CardContent>
      </Card>
    )
  }

  const urgent = typeof totals.daysToNearestDeadline === "number" && totals.daysToNearestDeadline <= 3 && totals.daysToNearestDeadline >= 0
  const deadlineSub = totals.daysToNearestDeadline == null
    ? "Closest submission date"
    : totals.daysToNearestDeadline < 0
    ? "Expired"
    : totals.daysToNearestDeadline === 0
    ? "Due today"
    : `in ${totals.daysToNearestDeadline} day(s)`

  const fmtDelta = (d) => {
    if (d == null) return null
    const n = Number(d || 0)
    const sign = n > 0 ? "+" : ""
    return `${sign}${n}`
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
      <MetricCard
        tone="blue"
        icon={<BarChart3 className="h-5 w-5" />}
        title="Total Opportunities"
        value={totals.opportunities}
        subtext={trend.opp == null ? "vs last run" : `${fmtDelta(trend.opp)} vs last run`}
        right={miniLine("#3B82F6")}
      />
      <MetricCard
        tone="red"
        icon={<Flame className="h-5 w-5" />}
        title="HOT Opportunities"
        value={totals.hotOpportunities}
        subtext="Priority action required"
        right={
          totals.hotOpportunities ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-1 text-[11px] font-semibold text-red-600 dark:text-red-300 ring-1 ring-red-500/20">
              <span className="relative inline-flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-30 animate-ping" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
              </span>
              HOT
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-foreground/5 px-2 py-1 text-[11px] font-semibold text-muted-foreground ring-1 ring-border">
              <TrendingUp className="h-3.5 w-3.5" />
              {trend.hot == null ? "stable" : `${fmtDelta(trend.hot)} vs last run`}
            </span>
          )
        }
      />
      <MetricCard
        tone={urgent ? "red" : "purple"}
        icon={<CalendarDays className="h-5 w-5" />}
        title="Next Deadline"
        value={totals.nearestDeadline}
        subtext={deadlineSub}
        right={
          urgent ? (
            <span className="inline-flex items-center rounded-full bg-red-500/10 px-2 py-1 text-[11px] font-semibold text-red-600 dark:text-red-300 ring-1 ring-red-500/25">
              Urgent
            </span>
          ) : null
        }
      />
      <MetricCard
        tone="pink"
        icon={<Heart className="h-5 w-5" />}
        title="Liked"
        value={totals.likedOpportunities}
        subtext="Saved opportunities"
        right={
          <span className="inline-flex items-center gap-1 rounded-full bg-foreground/5 px-2 py-1 text-[11px] font-semibold text-muted-foreground ring-1 ring-border">
            <TrendingUp className="h-3.5 w-3.5" />
            {trend.liked == null ? "vs last run" : `${fmtDelta(trend.liked)} vs last run`}
          </span>
        }
      />
      <MetricCard
        tone="green"
        icon={<Star className="h-5 w-5" />}
        title="Recommended"
        value={totals.recommendedOpportunities}
        subtext="Similarity score > 0.75"
        right={
          <span className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-2 py-1 text-[11px] font-semibold text-green-700 dark:text-green-300 ring-1 ring-green-500/20">
            <TrendingUp className="h-3.5 w-3.5" />
            {trend.rec == null ? "vs last run" : `${fmtDelta(trend.rec)} vs last run`}
          </span>
        }
      />
    </div>
  )
}
