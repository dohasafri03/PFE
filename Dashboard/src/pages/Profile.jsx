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
import { Heart, Sparkles, FileText, TrendingUp, Clock } from "lucide-react";

const GlassCard = ({ children, className = "" }) => (
  <Card className={`bg-white/5 backdrop-blur border-white/10 hover:shadow-md hover:shadow-black/20 transition-all ${className}`}>
    {children}
  </Card>
);

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
  const [editForm, setEditForm] = useState({ display_name: "", role: "", avatar_url: "" });
  const [pwForm, setPwForm] = useState({ current_password: "", new_password: "", confirm_password: "" });

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
      { title: "Liked Opportunities", value: liked, icon: <Heart className="h-4 w-4 text-red-500" /> },
      { title: "Recommended", value: rec, icon: <Sparkles className="h-4 w-4 text-green-400" /> },
      { title: "Generated Dossiers", value: dossiers, icon: <FileText className="h-4 w-4 text-primary" /> },
      { title: "Avg Score (Selected)", value: avg, icon: <TrendingUp className="h-4 w-4 text-orange-400" /> },
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
      avatar_url: base.avatar_url || "",
    });
    setEditOpen(true);
  };

  const submitEdit = async (e) => {
    e?.preventDefault?.();
    setEditError("");
    try {
      const res = await updateProfileMe({
        display_name: editForm.display_name,
        role: editForm.role,
        avatar_url: editForm.avatar_url,
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
      await changePassword(pwForm.current_password, pwForm.new_password);
      await addProfileActivity({ type: "security_action", message: "Changed password" });
      setPwOpen(false);
    } catch (err) {
      setPwError(err?.message || "Mot de passe actuel incorrect (ou erreur serveur).");
    }
  };

  const renderActivityIcon = (type) => {
    switch (type) {
      case "liked_opportunity":
        return <Heart className="h-4 w-4 text-red-500" />;
      case "unliked_opportunity":
        return <Heart className="h-4 w-4 text-muted-foreground" />;
      case "viewed_opportunity":
        return <Clock className="h-4 w-4 text-muted-foreground" />;
      case "generated_document":
        return <FileText className="h-4 w-4 text-primary" />;
      case "recommendation_alert":
        return <Sparkles className="h-4 w-4 text-green-400" />;
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <GlassCard className="overflow-hidden">
          <CardContent className="p-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <Avatar className="h-16 w-16 ring-1 ring-white/10">
                  <AvatarImage src={(meProfile?.avatar_url || user?.avatar_url) || "/avatars/01.png"} alt="@user" />
                  <AvatarFallback>{((meProfile?.display_name || user?.display_name || user?.username || "AD").slice(0, 2)).toUpperCase()}</AvatarFallback>
                </Avatar>
                <div>
                  <div className="text-2xl font-bold">{meProfile?.display_name || user?.display_name || user?.username || "Admin"}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="secondary" className="bg-white/10 text-foreground">{meProfile?.role || user?.role || "Admin"}</Badge>
                    <span className="text-xs text-muted-foreground">AI Procurement Dashboard</span>
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={openEdit}>
                  Edit profile
                </Button>
                <Button variant="outline" onClick={openPassword}>
                  Change password
                </Button>
              </div>
            </div>
          </CardContent>
        </GlassCard>

        <Dialog open={editOpen} onOpenChange={setEditOpen}>
          <DialogContent className="sm:max-w-lg bg-background/80 backdrop-blur border-white/10">
            <DialogHeader>
              <DialogTitle>Edit profile</DialogTitle>
              <DialogDescription>Mettre a jour les informations de base (affichage).</DialogDescription>
            </DialogHeader>
            <form onSubmit={submitEdit} className="space-y-3">
              <div className="space-y-1">
                <div className="text-sm font-medium">Display name</div>
                <Input
                  value={editForm.display_name}
                  onChange={(e) => setEditForm((p) => ({ ...p, display_name: e.target.value }))}
                  placeholder="ex: Admin"
                  required
                />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-medium">Role</div>
                <Input
                  value={editForm.role}
                  onChange={(e) => setEditForm((p) => ({ ...p, role: e.target.value }))}
                  placeholder="ex: Admin, Analyst..."
                />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-medium">Avatar URL (optional)</div>
                <Input
                  value={editForm.avatar_url}
                  onChange={(e) => setEditForm((p) => ({ ...p, avatar_url: e.target.value }))}
                  placeholder="https://..."
                />
              </div>
              {editError ? <div className="text-sm text-destructive">{editError}</div> : null}
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setEditOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit">Save</Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>

        <Dialog open={pwOpen} onOpenChange={setPwOpen}>
          <DialogContent className="sm:max-w-lg bg-background/80 backdrop-blur border-white/10">
            <DialogHeader>
              <DialogTitle>Change password</DialogTitle>
              <DialogDescription>Cette action met a jour le mot de passe de ton compte.</DialogDescription>
            </DialogHeader>
            <form onSubmit={submitPassword} className="space-y-3">
              <div className="space-y-1">
                <div className="text-sm font-medium">Current password</div>
                <Input
                  type="password"
                  value={pwForm.current_password}
                  onChange={(e) => setPwForm((p) => ({ ...p, current_password: e.target.value }))}
                  autoComplete="current-password"
                  required
                />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-medium">New password</div>
                <Input
                  type="password"
                  value={pwForm.new_password}
                  onChange={(e) => setPwForm((p) => ({ ...p, new_password: e.target.value }))}
                  autoComplete="new-password"
                  required
                />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-medium">Confirm new password</div>
                <Input
                  type="password"
                  value={pwForm.confirm_password}
                  onChange={(e) => setPwForm((p) => ({ ...p, confirm_password: e.target.value }))}
                  autoComplete="new-password"
                  required
                />
              </div>
              {pwError ? <div className="text-sm text-destructive">{pwError}</div> : null}
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setPwOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit">Update password</Button>
              </div>
            </form>
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
              <GlassCard className="hover:-translate-y-0.5">
                <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                  <CardTitle className="text-sm font-medium">{c.title}</CardTitle>
                  {c.icon}
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{c.value}</div>
                </CardContent>
              </GlassCard>
            </motion.div>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <GlassCard>
            <CardHeader>
              <CardTitle>Activity Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative pl-4">
                <div className="absolute left-1 top-0 bottom-0 w-px bg-white/10" />
                <div className="space-y-4">
                  {(activityPageItems || []).map((e, idx) => (
                    <div key={`${e.created_at || idx}-${idx}`} className="relative">
                      <div className="absolute -left-1.5 top-1 h-3 w-3 rounded-full bg-background ring-2 ring-white/10" />
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5">{renderActivityIcon(e.type)}</div>
                        <div className="flex-1">
                          <div className="text-sm font-medium">
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
                <div className="mt-4 pt-4 border-t border-white/10 flex items-center justify-between gap-3">
                  <div className="text-xs text-muted-foreground">
                    Page {Math.min(Math.max(1, activityPage), activityTotalPages)} / {activityTotalPages}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8"
                      disabled={activityPage <= 1}
                      onClick={() => setActivityPage((p) => Math.max(1, p - 1))}
                    >
                      Prev
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8"
                      disabled={activityPage >= activityTotalPages}
                      onClick={() => setActivityPage((p) => Math.min(activityTotalPages, p + 1))}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </GlassCard>
        </div>

      </div>
    </Layout>
  );
}
