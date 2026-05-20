/**
 * Parse budget values from API (number, string "984 000,00 DH", etc.)
 * Aligned with api/main.py _parse_pipeline_budget heuristics.
 */
export function parseBudget(value) {
  if (value == null || value === "") return 0
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 0 ? value : 0
  }

  let v = String(value).trim()
  if (!v || v === "-" || /^n\/?a$/i.test(v)) return 0

  v = v.replace(/[^0-9,.]/g, "")
  if (!v) return 0

  if (v.includes(",") && v.includes(".")) {
    if (v.lastIndexOf(",") > v.lastIndexOf(".")) {
      v = v.replace(/\./g, "").replace(",", ".")
    } else {
      v = v.replace(/,/g, "")
    }
  } else if (v.includes(",") && !v.includes(".")) {
    if (/,\d{1,2}$/.test(v)) {
      v = v.replace(",", ".")
    } else {
      v = v.replace(/,/g, "")
    }
  } else if (v.includes(".") && !v.includes(",")) {
    if (!/\.\d{1,2}$/.test(v)) {
      v = v.replace(/\./g, "")
    }
  }

  const n = Number.parseFloat(v)
  return Number.isFinite(n) && n > 0 ? n : 0
}

export function formatBudget(amount, fallback = "-") {
  const value = parseBudget(amount)
  if (value <= 0) return fallback
  const fixed = value.toFixed(2)
  const [intPart, decPart] = fixed.split(".")
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ")
  return `${grouped},${decPart} DH`
}
