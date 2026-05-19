import { parseBudget } from "@/lib/budget";

// API runs on port 8011 in this project by default (FastAPI/Uvicorn).
// IMPORTANT: keep the API host aligned with the app host so the auth cookie is sent.
// (If the app is on localhost and API is on 127.0.0.1, cookies won't match.)
// Override via VITE_API_URL if needed.
const DEFAULT_API = (typeof window !== "undefined" && window.location?.hostname)
  ? `http://${window.location.hostname}:8011`
  : "http://localhost:8011";
const API_BASE_URL = import.meta.env.VITE_API_URL || DEFAULT_API;

const fetchWithCreds = (url, options = {}) => {
  return fetch(url, { credentials: "include", ...options });
};

const readErrorDetail = async (res) => {
  const text = await res.text().catch(() => "");
  try {
    const data = JSON.parse(text);
    if (data && typeof data.detail === "string" && data.detail.trim()) return data.detail;
  } catch (_) {
    // ignore JSON parse errors
  }
  return text || res.statusText || `HTTP ${res.status}`;
};

export const fetchOpportunities = async (profile = "GLOBAL", options = {}) => {
  try {
    // Prefer the pipeline export (same content as n8n-generated CSV) when available.
    const p = String(profile || "GLOBAL").toUpperCase();
    const endpoint = p === "GLOBAL" || p === "ALL"
      ? `${API_BASE_URL}/results/opportunities`
      : `${API_BASE_URL}/opportunities?profile=${encodeURIComponent(p)}`;

    const exportResponse = await fetchWithCreds(endpoint);
    if (exportResponse.ok) {
      const exportData = await exportResponse.json();
      const opportunities = exportData.opportunities || [];
       return opportunities.map((c) => {
         const ds = Array.isArray(c.domains) ? c.domains : [];
         const inferredService = ds.length ? ds.slice(0, 2).join(" / ") : "";
         const objet = c.objet || c.description || "";
         return ({
           id: c.id,
           reference: c.reference || c.id,
           url: c.url || "",
           title: c.title || "Sans Titre",
           buyer: c.buyer || c.organization || "Acheteur Inconnu",
           organization: c.organization || c.buyer || "Acheteur Inconnu",
           service: c.service || inferredService || c.sector || "IT",
           budget: parseBudget(c.budget),
           deadline: c.deadline || null,
           score: Math.round(c.score || 0),
           similarity_score: typeof c.similarity_score === "number" ? c.similarity_score : 0,
           liked: !!c.liked,
           level: c.priority || "COLD",
           sector: (c.sector || (c.domains && c.domains[0]) || "IT"),
           // Keep raw procurement text for inference (buyer/org, domains, etc.)
           objet,
           description: objet || c.title || "",
           domains: ds,
           domain: ds,
           keywords: [],
           descriptionTechnique: c.description_technique || c.technical_description || "",
           descriptionFonctionnelle: c.description_fonctionnelle || c.functional_description || "",
           requirements: c.requirements || [],
         })
       });
     }

    // Using the score endpoint which returns the latest CSV results quickly
    const response = await fetchWithCreds(`${API_BASE_URL}/pipeline/score`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}), // Empty body to trigger default behavior (latest CSV)
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    // Default to an empty array if relevant_consultations is missing
    const consultations = data.relevant_consultations || [];

    // If the score endpoint doesn't include per-user like state, overlay it from /liked.
    // This avoids intermittent "likes disappearing" when /results/opportunities is temporarily unavailable.
    let likedSet = null;
    try {
      const hasLikedField = Array.isArray(consultations) && consultations.some((c) => c && Object.prototype.hasOwnProperty.call(c, "liked"));
      if (!hasLikedField) {
        const likedRes = await fetchLiked();
        const likedItems = likedRes?.opportunities || [];
        likedSet = new Set(likedItems.map((o) => String(o?.id || o?.reference || "")).filter(Boolean));
      }
    } catch (_) {
      likedSet = null;
    }
    
    // Map backend data structure to frontend expectations
    return consultations.map(c => ({
      id: c.reference || c.id,
      reference: c.reference || c.id,
      url: c.url || "",
      title: c.objet || 'Sans Titre',
      buyer: c.acheteur || 'Acheteur Inconnu',
      organization: c.acheteur || 'Acheteur Inconnu',
       service: (c.domains && c.domains.length > 0) ? c.domains.slice(0, 2).join(' / ') : 'IT',
      budget: parseBudget(c.budget),
      deadline: c.deadline || null,
      score: Math.round(c.score || 0),
      similarity_score: typeof c.similarity_score === "number" ? c.similarity_score : 0,
      liked: likedSet ? likedSet.has(String(c.reference || c.id)) : !!c.liked,
      level: c.priority || 'COLD',
      sector: (c.domains && c.domains.length > 0) ? c.domains[0] : 'IT',
      description: c.objet || '',
      domains: c.domains || [],
      keywords: c.keywords || [],
      descriptionTechnique: c.description_technique || "",
      descriptionFonctionnelle: c.description_fonctionnelle || "",
      requirements: c.requirements || []
    }));

  } catch (error) {
    console.error("Error fetching opportunities:", error);
    // Fallback to empty array on error to prevent UI crash
    return [];
  }
};

export const toggleLike = async (id, liked = null) => {
  const url = `${API_BASE_URL}/like/${encodeURIComponent(id)}`;
  const body = liked === null ? {} : { liked: !!liked };
  const res = await fetchWithCreds(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Like failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const fetchLiked = async () => {
  const res = await fetchWithCreds(`${API_BASE_URL}/liked`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Liked fetch failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const fetchRecommended = async (threshold = 0.75) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/recommended?threshold=${encodeURIComponent(threshold)}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Recommended fetch failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const fetchDossiers = async (consultationId) => {
  try {
    const response = await fetchWithCreds(`${API_BASE_URL}/results/dossiers/${encodeURIComponent(consultationId)}`);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    return data.files || [];
  } catch (error) {
    console.error("Error fetching dossiers:", error);
    return [];
  }
};

export const startPipeline = async (options = {}) => {
  const response = await fetchWithCreds(`${API_BASE_URL}/pipeline/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(options),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Pipeline start failed: ${response.status} ${text}`);
  }

  return response.json();
};

export const generateDossiers = async (options = {}) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/pipeline/generate-dossiers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options || {}),
  })
  if (!res.ok) {
    const detail = await readErrorDetail(res)
    throw new Error(detail)
  }
  return res.json()
}

export const fetchPipelineStatus = async () => {
  const response = await fetchWithCreds(`${API_BASE_URL}/pipeline/status`);
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Pipeline status failed: ${response.status} ${text}`);
  }
  return response.json();
};

export const fetchDossiersIndex = async () => {
  const response = await fetchWithCreds(`${API_BASE_URL}/results/dossiers/index`);
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Dossiers index failed: ${response.status} ${text}`);
  }
  return response.json();
};

export const getDownloadUrl = (path) => {
  if (!path) return '#';
  return `${API_BASE_URL}${path}`;
};
export const getExportUrl = (format) => {
  return `${API_BASE_URL}/results/${format}`;
};

export const login = async (username, password) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Login failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const logout = async () => {
  await fetchWithCreds(`${API_BASE_URL}/auth/logout`, { method: "POST" }).catch(() => {});
  return true;
};

export const me = async () => {
  const res = await fetchWithCreds(`${API_BASE_URL}/auth/me`);
  if (!res.ok) return { ok: false };
  return res.json();
};

export const changePassword = async (current_password, new_password) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/auth/change-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password, new_password }),
  });
  if (!res.ok) {
    const detail = await readErrorDetail(res);
    throw new Error(detail);
  }
  return res.json();
};

export const fetchProfileStats = async () => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/stats`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Profile stats failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const fetchProfileMe = async () => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/me`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Profile me failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const updateProfileMe = async (payload) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/me`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Profile update failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const fetchProfilePreferences = async () => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/preferences`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Profile preferences failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const saveProfilePreferences = async (prefs) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/preferences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prefs || {}),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Profile preferences save failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const fetchProfileActivity = async (limit = 50) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/activity?limit=${encodeURIComponent(limit)}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Profile activity failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const addProfileActivity = async (event) => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/activity`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event || {}),
  });
  // Best effort: don't break UI if logging fails
  return res.ok;
};

export const fetchProfileSecurity = async () => {
  const res = await fetchWithCreds(`${API_BASE_URL}/profile/security`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Profile security failed: ${res.status} ${text}`);
  }
  return res.json();
};

export const fetchNotifications = async (limit = 50, profile) => {
  const p = profile ? `&profile=${encodeURIComponent(profile)}` : "";
  const res = await fetchWithCreds(`${API_BASE_URL}/notifications?limit=${encodeURIComponent(limit)}${p}`);
  if (!res.ok) {
    const detail = await readErrorDetail(res);
    throw new Error(detail);
  }
  return res.json();
};

export const markNotificationRead = async (id, profile) => {
  const p = profile ? `?profile=${encodeURIComponent(profile)}` : "";
  const res = await fetchWithCreds(`${API_BASE_URL}/notifications/read/${encodeURIComponent(id)}${p}`, { method: "POST" });
  if (!res.ok) {
    const detail = await readErrorDetail(res);
    throw new Error(detail);
  }
  return res.json();
};

export const markAllNotificationsRead = async (profile) => {
  const p = profile ? `?profile=${encodeURIComponent(profile)}` : "";
  const res = await fetchWithCreds(`${API_BASE_URL}/notifications/read_all${p}`, { method: "POST" });
  if (!res.ok) {
    const detail = await readErrorDetail(res);
    throw new Error(detail);
  }
  return res.json();
};
