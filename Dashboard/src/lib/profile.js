export const PROFILE_CONFIG = {
  DATA: {
    label: "Data",
    subProfiles: ["AI"],
    domains: ["data", "big data", "etl", "analytics", "ai", "machine learning"],
  },
  DEV: {
    label: "Development",
    domains: ["dev", "software", "web", "application"],
  },
  CLOUD: {
    label: "Cloud",
    domains: ["cloud", "aws", "azure", "gcp", "devops"],
  },
};

export const PROFILE_THEME = {
  DATA: { primary: "#06b6d4", gradient: "from-cyan-500 to-[#6C63FF]" },
  DEV: { primary: "#10b981", gradient: "from-emerald-500 to-[#6C63FF]" },
  CLOUD: { primary: "#F97316", gradient: "from-[#F97316] to-[#6C63FF]" },
  // Alexsys brand bar: teal/cyan -> blue -> purple (matches logo nuances)
  GLOBAL: { primary: "#6C63FF", gradient: "from-[#00C2D1] via-[#3B82F6] to-[#6C63FF]" },
};

export function normalizeProfile(value) {
  const v = String(value || "").trim().toUpperCase();
  if (!v) return "GLOBAL";
  if (v === "CYBER") return "CYBERSECURITY";
  if (["GLOBAL", "DATA", "CLOUD", "DEV", "CYBERSECURITY", "AI"].includes(v)) return v;
  return "GLOBAL";
}

export function normalizeSubProfile(value) {
  const v = String(value || "").trim().toUpperCase();
  if (!v || v === "NONE" || v === "NULL") return null;
  if (v === "CYBER") return "CYBERSECURITY";
  if (["AI"].includes(v)) return v;
  return null;
}

export function normalizeProfileSelection({ profile, sub_profile }) {
  let p = normalizeProfile(profile);
  let sp = normalizeSubProfile(sub_profile);
  // AI is a sub-profile of DATA; keep UI consistent.
  if (p === "AI") {
    p = "DATA";
    sp = "AI";
  }
  if (p !== "DATA") sp = null;
  return { profile: p, sub_profile: sp };
}

function safeStr(v) {
  return (v == null) ? "" : String(v);
}

function toUpperTokens(value) {
  return String(value || "")
    .toUpperCase()
    .split(/[\/,|]/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function buildOpportunityText(op) {
  const reqs = Array.isArray(op?.requirements) ? op.requirements.join(" ") : safeStr(op?.requirements);
  return [
    safeStr(op?.title),
    safeStr(op?.description),
    safeStr(op?.descriptionTechnique),
    safeStr(op?.descriptionFonctionnelle),
    safeStr(op?.buyer),
    safeStr(op?.service),
    reqs,
    Array.isArray(op?.domains) ? op.domains.join(" ") : safeStr(op?.domains),
  ]
    .join(" ")
    .toLowerCase();
}

export function isAIOpportunity(op) {
  const text = buildOpportunityText(op);
  // Prefer domain tags when available
  const doms = Array.isArray(op?.domains) ? op.domains.map((d) => String(d || "").toUpperCase()) : [];
  if (doms.includes("AI")) return true;
  return Boolean(
    text.match(/\b(ai|ml|nlp|llm)\b/) ||
      text.includes("artificial intelligence") ||
      text.includes("intelligence artificielle") ||
      text.includes("machine learning") ||
      text.includes("deep learning") ||
      text.includes("chatbot")
  );
}

function includesAnyToken(text, tokens) {
  const t = String(text || "");
  for (const raw of tokens || []) {
    const kw = String(raw || "").trim().toLowerCase();
    if (!kw) continue;
    // Use word boundaries for short keywords to avoid matching everything.
    if (kw.length <= 4) {
      const re = new RegExp(`\\b${kw.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")}\\b`, "i");
      if (re.test(t)) return true;
    } else {
      if (t.includes(kw)) return true;
    }
  }
  return false;
}

export function filterOpportunitiesByProfile(opportunities, profile) {
  const list = Array.isArray(opportunities) ? opportunities : [];
  const p = normalizeProfile(profile);
  if (!p || p === "GLOBAL" || p === "ALL") return list;

  // DATA includes AI automatically (no separate AI profile).
  if (p === "DATA") {
    return list.filter((op) => {
      const doms = Array.isArray(op?.domains) ? op.domains.map((d) => String(d || "").toUpperCase()) : [];
      if (doms.includes("DATA") || doms.includes("AI")) return true;
      // If domains are missing, apply a stricter keyword-based filter (avoid letting everything through).
      const text = buildOpportunityText(op);
      const dataKw = ["big data", "etl", "analytics", "data", "sql", "bi", "data lake", "data warehouse", "machine learning", "ai"];
      return includesAnyToken(text, dataKw);
    });
  }

  if (p === "DEV") {
    return list.filter((op) => {
      const doms = Array.isArray(op?.domains) ? op.domains.map((d) => String(d || "").toUpperCase()) : [];
      const serviceTokens = toUpperTokens(op?.service);
      const hasDev = doms.includes("DEV") || serviceTokens.includes("DEV");
      const hasAI = doms.includes("AI") || serviceTokens.includes("AI");
      return hasDev && !hasAI;
    });
  }

  const config = PROFILE_CONFIG[p];
  if (!config) return list;
  return list.filter((op) => {
    const doms = Array.isArray(op?.domains) ? op.domains.map((d) => String(d || "").toUpperCase()) : [];
    if (doms.includes(p)) return true;
    const text = buildOpportunityText(op);
    return includesAnyToken(text, config.domains);
  });
}

export function filterOpportunities(opportunities, { profile, subFilter } = {}) {
  const p = normalizeProfile(profile);
  const base = filterOpportunitiesByProfile(opportunities, p);
  if (p === "DATA") {
    const sf = String(subFilter || "ALL").toUpperCase();
    if (sf === "AI") return base.filter(isAIOpportunity);
  }
  return base;
}

