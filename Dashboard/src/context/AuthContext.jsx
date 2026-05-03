import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { me as apiMe } from "@/services/api";
import { normalizeProfileSelection } from "@/lib/profile";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState(null);

  useEffect(() => {
    let mounted = true;
    apiMe()
      .then((res) => {
        if (!mounted) return;
        if (res && res.ok && res.username) {
          const sel = normalizeProfileSelection({ profile: res.profile || res.role, sub_profile: res.sub_profile });
          const profile = sel.profile;
          const sub_profile = sel.sub_profile;
          try {
            localStorage.setItem("marche_ai_profile", profile);
            if (sub_profile) localStorage.setItem("marche_ai_sub_profile", sub_profile);
            else localStorage.removeItem("marche_ai_sub_profile");
          } catch (_) {}
          setUser({
            username: res.username,
            display_name: res.display_name || res.username,
            role: res.role || "Admin",
            profile,
            sub_profile,
            avatar_url: res.avatar_url || "",
          });
        }
        else setUser(null);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const value = useMemo(() => ({ loading, user, setUser }), [loading, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
