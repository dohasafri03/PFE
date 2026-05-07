import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Bell, CheckCheck } from "lucide-react";
import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from "@/services/api";
import { useAuth } from "@/context/AuthContext";
import { normalizeProfileSelection } from "@/lib/profile";

const GlassCard = ({ children, className = "" }) => (
  <Card className={`bg-white/5 backdrop-blur border-white/10 hover:shadow-md hover:shadow-black/20 transition-all ${className}`}>
    {children}
  </Card>
);

const formatDate = (iso) => {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("fr-FR");
};

export function Notifications() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const notifProfile = useMemo(() => {
    const fromUser = String(user?.profile || "").trim()
    const fromUserSub = String(user?.sub_profile || "").trim()
    let storedProfile = ""
    let storedSub = ""
    try {
      storedProfile = localStorage.getItem("marche_ai_profile") || ""
      storedSub = localStorage.getItem("marche_ai_sub_profile") || ""
    } catch (_) {}
    const sel = normalizeProfileSelection({
      profile: fromUser || storedProfile || "GLOBAL",
      sub_profile: fromUserSub || storedSub || "",
    })
    return String(sel.profile || "GLOBAL").toUpperCase()
  }, [user?.profile, user?.sub_profile])

  const load = async () => {
    const res = await fetchNotifications(200, notifProfile);
    setItems(res.notifications || []);
    setUnread(res.unread_count ?? 0);
  };

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    load()
      .catch((e) => {
        if (!mounted) return;
        setError(e?.message || "Failed to load notifications.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    const t = setInterval(() => {
      load().catch(() => {});
    }, 60_000);

    const onStorage = (e) => {
      if (!e) return;
      if (e.key === "marche_ai_profile" || e.key === "marche_ai_sub_profile") {
        load().catch(() => {});
      }
    };
    window.addEventListener("storage", onStorage);

    return () => {
      mounted = false;
      clearInterval(t);
      window.removeEventListener("storage", onStorage);
    };
  }, [notifProfile, user?.username]);

  const onOpen = async (n) => {
    if (!n) return;
    if (!n.read) {
      await markNotificationRead(n.id, notifProfile).catch(() => {});
    }
    if (n.opportunity_id) {
      navigate("/", { state: { openOpportunityId: n.opportunity_id } });
    }
    await load().catch(() => {});
  };

  const groupedTitle = useMemo(() => {
    return `Notifications (${unread} unread)`;
  }, [unread]);

  return (
    <Layout>
      <div className="flex flex-col gap-4">
        <div className="flex items-start sm:items-center justify-between gap-3 flex-col sm:flex-row">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{groupedTitle}</h1>
            <p className="text-muted-foreground">Auto refresh every 60 seconds.</p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={async () => {
                await markAllNotificationsRead(notifProfile).catch(() => {});
                await load().catch(() => {});
              }}
              disabled={!items.length}
            >
              <CheckCheck className="mr-2 h-4 w-4" /> Mark all read
            </Button>
          </div>
        </div>

        {error ? <div className="text-sm text-destructive">{error}</div> : null}

        {loading ? (
          <GlassCard>
            <CardContent className="p-6 text-sm text-muted-foreground">Loading...</CardContent>
          </GlassCard>
        ) : null}

        {!loading && !items.length ? (
          <GlassCard>
            <CardContent className="p-6 text-sm text-muted-foreground flex items-center gap-2">
              <Bell className="h-4 w-4" /> No notifications yet.
            </CardContent>
          </GlassCard>
        ) : null}

        <div className="grid gap-3">
          {items.map((n, idx) => (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, delay: Math.min(0.25, idx * 0.02) }}
            >
              <GlassCard
                className={`cursor-pointer ${n.read ? "" : "ring-1 ring-primary/40 bg-primary/5"}`}
                onClick={() => onOpen(n)}
              >
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center justify-between gap-3">
                    <span className="truncate">{n.type}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{formatDate(n.created_at)}</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="text-sm">{n.message}</div>
                  {n.opportunity_id ? (
                    <div className="text-xs text-muted-foreground mt-2">Open opportunity: {n.opportunity_id}</div>
                  ) : null}
                </CardContent>
              </GlassCard>
            </motion.div>
          ))}
        </div>
      </div>
    </Layout>
  );
}

