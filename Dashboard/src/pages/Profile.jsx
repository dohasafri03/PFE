import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Layout } from "@/components/layout/Layout";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  addProfileActivity,
  changePassword,
  fetchProfileActivity,
  fetchProfileMe,
  fetchProfileStats,
  updateProfileMe,
} from "@/services/api";
import { useAuth } from "@/context/AuthContext";
import { Heart, Sparkles, FileText, TrendingUp, Clock, User, Lock, Eye, EyeOff, Loader2 } from "lucide-react";

/** Cartes alignées sur KPICards (Dashboard) : clair #F3F4F6, sombre glass. */
const DashboardSurfaceCard = ({ children, className = "" }) => (
  <Card
    className={[
      "rounded-xl border border-black/5 bg-[#F3F4F6] shadow-sm transition-all duration-200",
      "dark:border-white/10 dark:bg-white/5 dark:shadow-[0_18px_60px_rgba(0,0,0,0.45)]",
      "hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(15,23,42,0.10)] dark:hover:border-white/15",
      className,
    ].join(" ")}
  >
    {children}
  </Card>
);

const profileMetricTones = {
  red: {
    ring: "ring-red-500/20",
    iconBg: "bg-red-500/10",
    iconText: "text-red-600 dark:text-red-400",
  },
  green: {
    ring: "ring-green-500/20",
    iconBg: "bg-green-500/10",
    iconText: "text-green-600 dark:text-green-400",
  },
  purple: {
    ring: "ring-[#6C63FF]/20",
    iconBg: "bg-[#6C63FF]/10",
    iconText: "text-[#6C63FF] dark:text-[#a59cf7]",
  },
  orange: {
    ring: "ring-orange-500/20",
    iconBg: "bg-orange-500/10",
    iconText: "text-orange-600 dark:text-orange-400",
  },
};

function ProfileMetricCard({ title, value, icon, tone = "blue" }) {
  const t = profileMetricTones[tone] || profileMetricTones.purple
  return (
    <Card
      className={[
        "group rounded-xl p-0 ring-1 transition-all duration-200 min-h-[120px] sm:min-h-[128px]",
        "bg-[#F3F4F6] border border-black/5 shadow-sm",
        "hover:bg-[#1a0b2e] hover:border-white/10 hover:text-white",
        "hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(15,23,42,0.10)]",
        "dark:bg-white/5 dark:border-white/10 dark:shadow-[0_18px_60px_rgba(0,0,0,0.45)]",
        t.ring,
      ].join(" ")}
    >
      <CardContent className="flex h-full flex-col justify-center px-5 py-6 sm:px-6 sm:py-7">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div
              className={`h-11 w-11 shrink-0 rounded-xl ${t.iconBg} ring-1 ring-border flex items-center justify-center transition-colors group-hover:bg-white/10 group-hover:ring-white/20`}
            >
              <div className={`${t.iconText} transition-colors group-hover:text-white [&>svg]:h-5 [&>svg]:w-5`}>{icon}</div>
            </div>
            <div className="min-w-0">
              <div className="text-xs font-semibold text-muted-foreground transition-colors group-hover:text-white/80">{title}</div>
              <div className="mt-2 text-2xl font-bold tracking-tight text-foreground truncate transition-colors group-hover:text-white">{value}</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

const getInitials = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "U";
  const parts = raw.split(/\s+/).filter(Boolean);
  const a = (parts[0] || raw).slice(0, 1);
  const b = (parts[1] || raw.slice(1, 2) || "").slice(0, 1);
  return (a + b).toUpperCase();
};

const passwordStrength = (pw) => {
  const s = String(pw || "");
  let score = 0;
  if (s.length >= 8) score += 1;
  if (s.length >= 12) score += 1;
  if (/[a-z]/.test(s) && /[A-Z]/.test(s)) score += 1;
  if (/\d/.test(s)) score += 1;
  if (/[^a-zA-Z0-9]/.test(s)) score += 1;
  const pct = Math.min(100, Math.round((score / 5) * 100));
  const label = pct >= 80 ? "Fort" : pct >= 45 ? "Moyen" : "Faible";
  const bar = pct >= 80 ? "bg-emerald-500" : pct >= 45 ? "bg-orange-500" : "bg-red-500";
  return { score, pct, label, bar };
};

function PasswordField({ label, value, onChange, autoComplete, error, placeholder }) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5">
      <div className="text-sm font-medium text-slate-700 dark:text-slate-200">{label}</div>
      <div className="relative">
        <Input
          type={show ? "text" : "password"}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          placeholder={placeholder}
          aria-invalid={!!error}
          className={[
            "h-11 rounded-[10px] border-[1.5px] bg-white/80 dark:bg-white/5 px-3 pr-10 py-2",
            "border-slate-200/90 dark:border-white/10",
            "placeholder:text-slate-400 placeholder:italic dark:placeholder:text-slate-400/80",
            "focus-visible:ring-2 focus-visible:ring-indigo-100 dark:focus-visible:ring-indigo-500/20",
            "focus-visible:ring-offset-0 focus-visible:border-indigo-500",
            error ? "border-red-300 focus-visible:border-red-500 focus-visible:ring-red-100 dark:border-red-500/40 dark:focus-visible:ring-red-500/20" : "",
          ].join(" ")}
          required
        />
        <button
          type="button"
          onClick={() => setShow((v) => !v)}
          className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/5 dark:text-slate-300 transition"
          aria-label={show ? "Hide password" : "Show password"}
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

export function Profile() {
  const { user, setUser } = useAuth();

  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState([]);
  const [activityPage, setActivityPage] = useState(1);
  const [meProfile, setMeProfile] = useState(null);

  const [editOpen, setEditOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [editError, setEditError] = useState("");
  const [pwError, setPwError] = useState("");
  const [editForm, setEditForm] = useState({ display_name: "", role: "" });
  const [pwForm, setPwForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [pwSubmitting, setPwSubmitting] = useState(false);

  const loadAll = async () => {
    const [s, a, me] = await Promise.all([
      fetchProfileStats(),
      fetchProfileActivity(50),
      fetchProfileMe(),
    ]);
    setStats(s);
    setActivity(a.items || []);
    setMeProfile(me);
  };

  useEffect(() => {
    loadAll().catch(() => {});
  }, []);

  // Reset pagination when activity data changes (e.g. new event appended).
  useEffect(() => {
    setActivityPage(1);
  }, [activity?.length]);

  const activityPageSize = 10;
  const activityTotalPages = useMemo(() => {
    const total = Array.isArray(activity) ? activity.length : 0;
    return Math.max(1, Math.ceil(total / activityPageSize));
  }, [activity]);

  const activityPageItems = useMemo(() => {
    const items = Array.isArray(activity) ? activity : [];
    const page = Math.min(Math.max(1, activityPage), activityTotalPages);
    const start = (page - 1) * activityPageSize;
    return items.slice(start, start + activityPageSize);
  }, [activity, activityPage, activityTotalPages]);

  const personalCards = useMemo(() => {
    const liked = stats?.liked_count ?? 0;
    const rec = stats?.recommended_count ?? 0;
    const dossiers = stats?.generated_dossiers_count ?? 0;
    const avg = stats?.avg_score_selected ?? 0;
    return [
      { title: "Liked Opportunities", value: liked, tone: "red", icon: <Heart className="h-5 w-5" /> },
      { title: "Recommended", value: rec, tone: "green", icon: <Sparkles className="h-5 w-5" /> },
      { title: "Generated Dossiers", value: dossiers, tone: "purple", icon: <FileText className="h-5 w-5" /> },
      { title: "Avg Score (Selected)", value: avg, tone: "orange", icon: <TrendingUp className="h-5 w-5" /> },
    ];
  }, [stats]);

  const formatDate = (iso) => {
    if (!iso) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString("fr-FR");
  };

  const openEdit = () => {
    setEditError("");
    const base = meProfile || user || {};
    setEditForm({
      display_name: base.display_name || base.username || "",
      role: base.role || "Admin",
    });
    setEditOpen(true);
  };

  const submitEdit = async (e) => {
    e?.preventDefault?.();
    setEditError("");
    try {
      setEditSubmitting(true);
      const res = await updateProfileMe({
        display_name: editForm.display_name,
        role: editForm.role,
      });
      // Keep AuthContext in sync for header/avatar.
      setUser({
        username: res.username,
        display_name: res.display_name || res.username,
        role: res.role || "Admin",
        avatar_url: res.avatar_url || "",
      });
      setMeProfile(res);
      await addProfileActivity({ type: "profile_edit", message: "Updated profile" });
      setEditOpen(false);
      await loadAll().catch(() => {});
    } catch (err) {
      setEditError("Impossible de mettre a jour le profil.");
    } finally {
      setEditSubmitting(false);
    }
  };

  const openPassword = () => {
    setPwError("");
    setPwForm({ current_password: "", new_password: "", confirm_password: "" });
    setPwOpen(true);
  };

  const submitPassword = async (e) => {
    e?.preventDefault?.();
    setPwError("");
    if (!pwForm.current_password || !pwForm.new_password) {
      setPwError("Veuillez remplir tous les champs.");
      return;
    }
    if (pwForm.new_password.length < 6) {
      setPwError("Le nouveau mot de passe doit contenir au moins 6 caracteres.");
      return;
    }
    if (pwForm.new_password !== pwForm.confirm_password) {
      setPwError("La confirmation ne correspond pas.");
      return;
    }
    try {
      setPwSubmitting(true);
      await changePassword(pwForm.current_password, pwForm.new_password);
      await addProfileActivity({ type: "security_action", message: "Changed password" });
      setPwOpen(false);
    } catch (err) {
      setPwError(err?.message || "Mot de passe actuel incorrect (ou erreur serveur).");
    } finally {
      setPwSubmitting(false);
    }
  };

  const renderActivityIcon = (type) => {
    switch (type) {
      case "liked_opportunity":
        return <Heart className="h-4 w-4 text-red-600 dark:text-red-400" />;
      case "unliked_opportunity":
        return <Heart className="h-4 w-4 text-muted-foreground opacity-70" />;
      case "viewed_opportunity":
        return <Clock className="h-4 w-4 text-blue-600 dark:text-blue-400" />;
      case "generated_document":
        return <FileText className="h-4 w-4 text-[#6C63FF] dark:text-[#a59cf7]" />;
      case "recommendation_alert":
        return <Sparkles className="h-4 w-4 text-green-600 dark:text-green-400" />;
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <Layout>
      <div className="flex min-w-0 max-w-full flex-col gap-6">
        {/* Bandeau identique au Dashboard (dégradé + texte blanc) */}
        <div className="alexsys-animated-header relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-r from-[#00C2D1] via-[#3B82F6] to-[#1a0b2e] p-5 text-white shadow-[0_18px_60px_rgba(0,0,0,0.35)] sm:p-6">
          <div className="pointer-events-none absolute inset-0 opacity-50">
            <div className="absolute -top-24 -left-24 h-64 w-64 rounded-full bg-white/10 blur-3xl" />
            <div className="absolute -bottom-28 -right-28 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
          </div>
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-transparent to-[#1a0b2e]/85" />
          <div className="pointer-events-none absolute inset-0 opacity-35 mix-blend-overlay">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.22),transparent_45%),radial-gradient(circle_at_80%_30%,rgba(255,255,255,0.16),transparent_50%),linear-gradient(120deg,rgba(255,255,255,0.08),transparent_40%,rgba(255,255,255,0.10))]" />
          </div>
          <div className="relative z-10 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3 sm:gap-4">
              <Avatar className="h-14 w-14 shrink-0 ring-2 ring-white/25 shadow-lg sm:h-16 sm:w-16">
                <AvatarImage src={(meProfile?.avatar_url || user?.avatar_url) || "/avatars/01.png"} alt="@user" />
                <AvatarFallback className="bg-white/15 text-sm text-white font-bold sm:text-base">
                  {((meProfile?.display_name || user?.display_name || user?.username || "AD").slice(0, 2)).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <div className="text-2xl sm:text-3xl font-bold tracking-tight truncate text-white drop-shadow-[0_10px_24px_rgba(0,0,0,0.35)]">
                  {meProfile?.display_name || user?.display_name || user?.username || "Admin"}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Badge className="border-0 bg-white/20 text-white hover:bg-white/25 backdrop-blur-sm">
                    {meProfile?.role || user?.role || "Admin"}
                  </Badge>
                  <span className="text-sm sm:text-base font-medium text-white/85 drop-shadow-[0_10px_24px_rgba(0,0,0,0.35)]">
                    AI Procurement Dashboard
                  </span>
                </div>
              </div>
            </div>
            <div className="flex w-full shrink-0 flex-wrap gap-2 sm:w-auto sm:justify-end">
              <Button
                variant="outline"
                onClick={openEdit}
                className="h-9 rounded-full border-white/20 bg-black/20 px-3 text-xs text-white backdrop-blur hover:bg-white/15 hover:text-white sm:px-4 sm:text-sm"
              >
                Edit profile
              </Button>
              <Button
                variant="outline"
                onClick={openPassword}
                className="h-9 rounded-full border-white/20 bg-black/20 px-3 text-xs text-white backdrop-blur hover:bg-white/15 hover:text-white sm:px-4 sm:text-sm"
              >
                Change password
              </Button>
            </div>
          </div>
        </div>

        <Dialog open={editOpen} onOpenChange={setEditOpen}>
          <DialogContent className="w-full max-w-[420px] rounded-2xl border border-slate-200/70 bg-white p-7 shadow-2xl shadow-indigo-100/60 dark:border-white/10 dark:bg-[#1E1E2E]">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{
                opacity: 1,
                scale: 1,
                x: editError ? [0, -10, 10, -7, 7, 0] : 0,
              }}
              transition={{
                duration: editError ? 0.35 : 0.2,
                ease: "easeOut",
              }}
            >
              <DialogHeader className="space-y-2">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700 ring-1 ring-indigo-100 dark:bg-white/5 dark:text-indigo-200 dark:ring-white/10">
                      <User className="h-5 w-5" />
                    </div>
                    <div>
                      <DialogTitle className="text-lg font-semibold text-slate-900 dark:text-white">Edit profile</DialogTitle>
                      <DialogDescription className="text-sm text-slate-400">Mettre à jour vos informations d’affichage.</DialogDescription>
                    </div>
                  </div>
                </div>
              </DialogHeader>

              <div className="mt-5 flex flex-col items-center text-center">
                <div className="h-16 w-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-200/60">
                  <span className="text-white font-bold text-xl">
                    {getInitials(meProfile?.display_name || user?.display_name || user?.username || "")}
                  </span>
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">
                  {meProfile?.display_name || user?.display_name || user?.username || "User"}
                </div>
              </div>

              <form onSubmit={submitEdit} className="mt-5 space-y-4">
                <div className="space-y-1.5">
                  <div className="text-sm font-medium text-slate-700 dark:text-slate-200">Display name</div>
                  <Input
                    value={editForm.display_name}
                    onChange={(e) => setEditForm((p) => ({ ...p, display_name: e.target.value }))}
                    placeholder="ex: Doha Safri"
                    required
                    className="h-11 rounded-[10px] border-[1.5px] border-slate-200/90 bg-white/80 dark:bg-white/5 px-3 py-2 placeholder:text-slate-400 placeholder:italic dark:placeholder:text-slate-400/80 focus-visible:ring-2 focus-visible:ring-indigo-100 dark:focus-visible:ring-indigo-500/20 focus-visible:ring-offset-0 focus-visible:border-indigo-500 dark:border-white/10"
                  />
                </div>
                <div className="space-y-1.5">
                  <div className="text-sm font-medium text-slate-700 dark:text-slate-200">Role</div>
                  <Input
                    value={editForm.role}
                    onChange={(e) => setEditForm((p) => ({ ...p, role: e.target.value }))}
                    placeholder="ex: Admin, Analyst..."
                    className="h-11 rounded-[10px] border-[1.5px] border-slate-200/90 bg-white/80 dark:bg-white/5 px-3 py-2 placeholder:text-slate-400 placeholder:italic dark:placeholder:text-slate-400/80 focus-visible:ring-2 focus-visible:ring-indigo-100 dark:focus-visible:ring-indigo-500/20 focus-visible:ring-offset-0 focus-visible:border-indigo-500 dark:border-white/10"
                  />
                </div>

                {editError ? (
                  <div className="rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">
                    {editError}
                  </div>
                ) : null}

                <div className="border-t border-slate-100 dark:border-white/10 pt-4 flex items-center justify-end gap-2">
                  <Button type="button" variant="secondary" className="rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10" onClick={() => setEditOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={editSubmitting}
                    className="rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-semibold hover:opacity-90 hover:shadow-lg hover:shadow-indigo-200/60"
                  >
                    {editSubmitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                    Save
                  </Button>
                </div>
              </form>
            </motion.div>
          </DialogContent>
        </Dialog>

        <Dialog open={pwOpen} onOpenChange={setPwOpen}>
          <DialogContent className="w-full max-w-[420px] rounded-2xl border border-slate-200/70 bg-white p-7 shadow-2xl shadow-indigo-100/60 dark:border-white/10 dark:bg-[#1E1E2E]">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{
                opacity: 1,
                scale: 1,
                x: pwError ? [0, -10, 10, -7, 7, 0] : 0,
              }}
              transition={{
                duration: pwError ? 0.35 : 0.2,
                ease: "easeOut",
              }}
            >
              <DialogHeader className="space-y-2">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700 ring-1 ring-indigo-100 dark:bg-white/5 dark:text-indigo-200 dark:ring-white/10">
                      <Lock className="h-5 w-5" />
                    </div>
                    <div>
                      <DialogTitle className="text-lg font-semibold text-slate-900 dark:text-white">Change password</DialogTitle>
                      <DialogDescription className="text-sm text-slate-400">Mettez à jour le mot de passe de votre compte.</DialogDescription>
                    </div>
                  </div>
                </div>
              </DialogHeader>

              <form onSubmit={submitPassword} className="mt-5 space-y-4">
                <PasswordField
                  label="Current password"
                  value={pwForm.current_password}
                  onChange={(e) => setPwForm((p) => ({ ...p, current_password: e.target.value }))}
                  autoComplete="current-password"
                  error={pwError}
                  placeholder="••••••••"
                />

                <div className="space-y-2">
                  <PasswordField
                    label="New password"
                    value={pwForm.new_password}
                    onChange={(e) => setPwForm((p) => ({ ...p, new_password: e.target.value }))}
                    autoComplete="new-password"
                    error={pwError}
                    placeholder="Min. 8 caractères"
                  />

                  {pwForm.new_password ? (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-300">
                        <span>Force</span>
                        <span className="font-semibold">{passwordStrength(pwForm.new_password).label}</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
                        <motion.div
                          className={`h-full ${passwordStrength(pwForm.new_password).bar}`}
                          initial={false}
                          animate={{ width: `${passwordStrength(pwForm.new_password).pct}%` }}
                          transition={{ duration: 0.2 }}
                        />
                      </div>
                    </div>
                  ) : null}
                </div>

                <PasswordField
                  label="Confirm new password"
                  value={pwForm.confirm_password}
                  onChange={(e) => setPwForm((p) => ({ ...p, confirm_password: e.target.value }))}
                  autoComplete="new-password"
                  error={pwError}
                  placeholder="••••••••"
                />

                {pwError ? (
                  <div className="rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">
                    {pwError}
                  </div>
                ) : null}

                <div className="border-t border-slate-100 dark:border-white/10 pt-4 flex items-center justify-end gap-2">
                  <Button type="button" variant="secondary" className="rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10" onClick={() => setPwOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={pwSubmitting}
                    className="rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-semibold hover:opacity-90 hover:shadow-lg hover:shadow-indigo-200/60"
                  >
                    {pwSubmitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                    Update password
                  </Button>
                </div>
              </form>
            </motion.div>
          </DialogContent>
        </Dialog>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {personalCards.map((c, idx) => (
            <motion.div
              key={c.title}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: 0.05 * idx }}
            >
              <ProfileMetricCard title={c.title} value={c.value} icon={c.icon} tone={c.tone} />
            </motion.div>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <DashboardSurfaceCard className="overflow-hidden rounded-2xl">
            <CardHeader>
              <CardTitle className="text-base font-semibold tracking-tight text-foreground">Activity Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative pl-4">
                <div className="absolute left-1 top-0 bottom-0 w-px bg-black/10 dark:bg-white/15" />
                <div className="space-y-4">
                  {(activityPageItems || []).map((e, idx) => (
                    <div key={`${e.created_at || idx}-${idx}`} className="relative">
                      <div className="absolute -left-1.5 top-1 h-3 w-3 rounded-full bg-background ring-2 ring-black/10 dark:ring-white/20" />
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5">{renderActivityIcon(e.type)}</div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-foreground">
                            {e.type?.replaceAll("_", " ") || "activity"}
                            {e.opportunity_id ? (
                              <span className="text-xs text-muted-foreground"> • {e.opportunity_id}</span>
                            ) : null}
                          </div>
                          {e.message ? <div className="text-xs text-muted-foreground">{e.message}</div> : null}
                          <div className="text-xs text-muted-foreground mt-1">{formatDate(e.created_at)}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                  {(!activity || activity.length === 0) ? (
                    <div className="text-sm text-muted-foreground">No recent activity.</div>
                  ) : null}
                </div>
              </div>

              {Array.isArray(activity) && activity.length > activityPageSize ? (
                <div className="mt-4 pt-4 border-t border-black/5 dark:border-white/10 flex items-center justify-between gap-3">
                  <div className="text-xs text-muted-foreground">
                    Page {Math.min(Math.max(1, activityPage), activityTotalPages)} / {activityTotalPages}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8 border-black/10 bg-white/80 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
                      disabled={activityPage <= 1}
                      onClick={() => setActivityPage((p) => Math.max(1, p - 1))}
                    >
                      Prev
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8 border-black/10 bg-white/80 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
                      disabled={activityPage >= activityTotalPages}
                      onClick={() => setActivityPage((p) => Math.min(activityTotalPages, p + 1))}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </DashboardSurfaceCard>
        </div>

      </div>
    </Layout>
  );
}
