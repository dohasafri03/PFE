import React, { useMemo } from "react"
import {
  PieChart, Pie, Cell, Tooltip as RechartsTooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend, AreaChart, Area, Line
} from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { toDeadlineComparableDate } from "@/lib/date"

const COLORS = {
  HOT: "#EF4444",
  WARM: "#F97316",
  COLD: "#3B82F6",
}

function barColorForService(name) {
  const key = String(name || "").trim().toUpperCase()
  // Logo strip palette (teal -> blue -> mauve). Use one segment per sector.
  const TEAL = "#00C2D1"
  const BLUE = "#3B82F6"
  const MAUVE = "#6C63FF"

  if (!key) return BLUE
  if (key.includes("AI")) return MAUVE
  if (key.includes("DATA") || key.includes("BI")) return BLUE
  if (key.includes("CLOUD") || key.includes("DEVOPS")) return TEAL
  if (key.includes("DEV") || key.includes("SOFTWARE")) return BLUE
  if (key.includes("CYBER")) return MAUVE
  // IT as its own sector (avoid `includes("IT")` — it matches "DEV")

  if (key === "IT" || /\bIT\b/.test(key)) return TEAL

  // Deterministic fallback: assign one of the 3 segments by a simple hash.
  const palette = [TEAL, BLUE, MAUVE]
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0
  return palette[h % palette.length]
}

function barColorUnique(_name, index) {
  const TEAL = "#00C2D1"
  const BLUE = "#3B82F6"
  const MAUVE = "#6C63FF"
  const ORANGE = "#F97316"
  const GREEN = "#22C55E"
  const RED = "#EF4444"
  const palette = [TEAL, BLUE, MAUVE, ORANGE, GREEN, RED]
  return palette[index % palette.length]
}

function TooltipCard({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  return (
    <div className="rounded-xl border border-border bg-card px-3 py-2 shadow-[0_16px_40px_rgba(15,23,42,0.10)] dark:shadow-[0_16px_50px_rgba(0,0,0,0.45)]">
      <div className="text-xs font-semibold text-foreground">{label}</div>
      <div className="mt-1 space-y-0.5">
        {payload.map((p) => (
          <div key={p.dataKey} className="flex items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
              <span>{p.name || p.dataKey}</span>
            </div>
            <div className="font-semibold text-foreground">{p.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Charts({ data }) {
  const uniqueData = useMemo(() => {
    const list = Array.isArray(data) ? data : []
    const byId = new Map()
    for (const o of list) {
      const id = String(o?.id || o?.reference || "").trim()
      if (!id) continue
      if (!byId.has(id)) byId.set(id, o)
    }
    return Array.from(byId.values())
  }, [data])

  // Pie Chart Data: Opportunities by Level
  const pieData = useMemo(() => {
    const counts = uniqueData.reduce((acc, curr) => {
      acc[curr.level] = (acc[curr.level] || 0) + 1
      return acc
    }, {})
    return Object.keys(counts).map(key => ({
      name: key,
      value: counts[key]
    }))
  }, [uniqueData])

  // Bar Chart Data: Opportunities by Sector
  const barData = useMemo(() => {
    const sectors = {}
    uniqueData.forEach(d => {
      if (!sectors[d.sector]) sectors[d.sector] = { name: d.sector, count: 0, budget: 0 }
      sectors[d.sector].count += 1
      sectors[d.sector].budget += d.budget
    })
    const rows = Object.values(sectors)
    rows.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")))
    return rows
  }, [uniqueData])

  // Timeline Data: cumulative opportunities by deadline date (upcoming)
  const lineData = useMemo(() => {
    const now = new Date()
    // Align with the list/table filtering: keep only items with deadline >= today (00:00).
    const today = new Date(now)
    today.setHours(0, 0, 0, 0)
    const counts = new Map()
    for (const d of (uniqueData || [])) {
      const dt = toDeadlineComparableDate(d.deadline)
      if (!dt) continue
      // Keep only upcoming items (same rule as the opportunities list).
      if (dt.getTime() < today.getTime()) continue
      // Use local date key (avoid UTC shift causing off-by-one day).
      const key = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`
      counts.set(key, (counts.get(key) || 0) + 1)
    }
    const keys = Array.from(counts.keys()).sort()
    let cum = 0
    const series = keys.map((k) => {
      cum += counts.get(k) || 0
      return { name: k, count: cum }
    })
    // Limit to last 18 points to avoid overcrowding.
    return series.slice(-18)
  }, [uniqueData])

  return (
    <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Level Distribution Pie Chart */}
      <Card className="min-w-0 bg-[#F3F4F6] border border-black/5 shadow-sm dark:bg-white/5 dark:border-white/10">
        <CardHeader>
          <CardTitle>Level Distribution</CardTitle>
        </CardHeader>
        <CardContent className="h-72 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={78}
                outerRadius={106}
                paddingAngle={5}
                dataKey="value"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[entry.name]} />
                ))}
              </Pie>
              <RechartsTooltip content={<TooltipCard />} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Sector Bar Chart */}
      <Card className="min-w-0 bg-[#F3F4F6] border border-black/5 shadow-sm dark:bg-white/5 dark:border-white/10">
        <CardHeader>
          <CardTitle>Opportunities by Sector</CardTitle>
        </CardHeader>
        <CardContent className="h-72 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.7} />
              <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12 }} />
              <RechartsTooltip cursor={{ fill: "hsl(var(--muted))" }} content={<TooltipCard />} />
              <Bar dataKey="count" name="Count" radius={[6, 6, 0, 0]}>
                {(barData || []).map((entry, index) => (
                  <Cell key={`bar-${index}`} fill={barColorUnique(entry?.name, index)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Deadlines Line Chart */}
      <Card className="min-w-0 bg-[#F3F4F6] border border-black/5 shadow-sm dark:bg-white/5 dark:border-white/10">
        <CardHeader>
          <CardTitle>Deadlines Timeline</CardTitle>
        </CardHeader>
        <CardContent className="h-72 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={lineData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="deadlineFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#3B82F6" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.7} />
              <XAxis
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 12 }}
                interval="preserveStartEnd"
              />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12 }} />
              <RechartsTooltip content={<TooltipCard />} />
              <Area
                type="monotone"
                dataKey="count"
                name="Count"
                stroke="#3B82F6"
                strokeWidth={2.5}
                fill="url(#deadlineFill)"
                dot={{ r: 3, strokeWidth: 2, fill: "hsl(var(--card))" }}
                activeDot={{ r: 5 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}
