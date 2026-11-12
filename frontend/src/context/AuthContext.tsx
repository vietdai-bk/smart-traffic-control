import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "@/lib/api";
import type { Perm } from "@/lib/permissions";
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  permissions: string[];
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (perm: Perm) => boolean;
  token: string | null;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [token, setToken] = useState<string | null>(tokenStore.get());
  const [ready, setReady] = useState(false);

  const reset = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    setUser(null);
    setPermissions([]);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(reset);
    if (!tokenStore.get()) {
      setReady(true);
      return;
    }
    api
      .get<{ user: User; permissions: string[] }>("/auth/me")
      .then((r) => {
        setUser(r.user);
        setPermissions(r.permissions);
      })
      .catch(reset)
      .finally(() => setReady(true));
  }, [reset]);

  const login = useCallback(async (username: string, password: string) => {
    const r = await api.post<{ access_token: string; user: User; permissions: string[] }>("/auth/login", {
      username,
      password,
    });
    tokenStore.set(r.access_token);
    setToken(r.access_token);
    setUser(r.user);
    setPermissions(r.permissions);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* phiên có thể đã hết hạn */
    }
    reset();
  }, [reset]);

  const can = useCallback((perm: Perm) => permissions.includes(perm), [permissions]);

  const value = useMemo(
    () => ({ user, permissions, ready, login, logout, can, token }),
    [user, permissions, ready, login, logout, can, token],
  );
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth phải dùng trong AuthProvider");
  return ctx;
}
