export const parseDeadlineDate = (value) => {
  if (!value) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value

  const v = String(value).trim()
  if (!v) return null

  // Explicit "DD/MM/YYYY" (optionally with "HH:MM") used by the portal.
  const fr = v.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2}))?$/)
  if (fr) {
    const [, dd, mm, yyyy, hh = "00", min = "00"] = fr
    const d = new Date(Number(yyyy), Number(mm) - 1, Number(dd), Number(hh), Number(min))
    return Number.isNaN(d.getTime()) ? null : d
  }

  // ISO "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS..."
  if (/^\d{4}-\d{2}-\d{2}/.test(v)) {
    const d = new Date(v)
    return Number.isNaN(d.getTime()) ? null : d
  }

  // Last-resort parsing (may be locale-dependent).
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? null : d
}

// For comparisons like "next deadline", treat date-only values as end-of-day so
// an opportunity due "today" doesn't get skipped after midnight.
export const toDeadlineComparableDate = (value) => {
  const v = value == null ? "" : String(value).trim()
  const d = parseDeadlineDate(value)
  if (!d) return null

  const isDateOnly =
    /^(\d{2})\/(\d{2})\/(\d{4})$/.test(v) ||
    /^\d{4}-\d{2}-\d{2}$/.test(v) ||
    // Treat ISO timestamps at midnight as date-only (common when backend serializes a Date field)
    /^\d{4}-\d{2}-\d{2}T00:00(?::00(?:\.\d{1,3})?)?(?:Z)?$/.test(v)

  if (!isDateOnly) return d

  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999)
}

export const formatShortDate = (value, locale = "fr-FR") => {
  const d = parseDeadlineDate(value)
  if (!d) return "-"
  return d.toLocaleDateString(locale)
}
