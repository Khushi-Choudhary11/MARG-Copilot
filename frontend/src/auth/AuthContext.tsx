import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type AuthUser, type Role } from "../api";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const raw = localStorage.getItem("auth_user");
    const token = localStorage.getItem("auth_token");
    if (raw && token) {
      try {
        setUser({ ...JSON.parse(raw), token });
      } catch {
        /* ignore */
      }
    }
    setLoading(false);
  }, []);

  async function login(username: string, password: string) {
    const { data } = await api.post("/api/auth/login", { username, password });
    const authUser: AuthUser = {
      username: data.username,
      role: data.role,
      name: data.name,
      token: data.token,
    };
    localStorage.setItem("auth_token", data.token);
    localStorage.setItem("auth_user", JSON.stringify({ username: authUser.username, role: authUser.role, name: authUser.name }));
    setUser(authUser);
  }

  function logout() {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    setUser(null);
  }

  function hasRole(...roles: Role[]) {
    return !!user && roles.includes(user.role);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
