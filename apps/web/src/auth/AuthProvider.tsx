import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  api,
  restoreAuthentication,
  setAccessToken,
  setAuthInvalidatedHandler,
} from "../api/client";
import type { Me } from "../types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  reload(): Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({
  children,
  initialMe = null,
  restoreOnMount = true,
}: {
  children: ReactNode;
  initialMe?: Me | null;
  restoreOnMount?: boolean;
}) {
  const queryClient = useQueryClient();
  const [me, setMe] = useState<Me | null>(initialMe);
  const [loading, setLoading] = useState(restoreOnMount);
  useEffect(() => {
    setAuthInvalidatedHandler(() => {
      setAccessToken(null);
      setMe(null);
      queryClient.clear();
    });
    return () => setAuthInvalidatedHandler(null);
  }, [queryClient]);
  async function reload() {
    setMe(await api<Me>("/api/v1/auth/me"));
  }
  useEffect(() => {
    if (!restoreOnMount) return;
    void (async () => {
      try {
        if (await restoreAuthentication()) await reload();
      } finally {
        setLoading(false);
      }
    })();
  }, [restoreOnMount]);
  async function signIn(email: string, password: string) {
    const token = await api<{ access_token: string }>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    );
    setAccessToken(token.access_token);
    await reload();
  }
  async function signOut() {
    await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    setAccessToken(null);
    setMe(null);
    queryClient.clear();
  }
  const value = { me, loading, signIn, signOut, reload };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
// AuthProvider and its colocated hook intentionally share this module.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider required");
  return value;
}
