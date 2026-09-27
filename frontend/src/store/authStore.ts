import { create } from "zustand";
import { persist } from "zustand/middleware";
import { decodeJwt, revokeRefreshToken } from "../api/auth";

export interface User {
  id: string;
  role: string;
}

export interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (accessToken: string, refreshToken: string) => void;
  /**
   * Replace the token pair without touching `user`. Used by the response
   * interceptor after a silent refresh: the identity has not changed, only the
   * access token, and re-deriving the user is wasted work.
   */
  setTokens: (accessToken: string, refreshToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      login: (accessToken: string, refreshToken: string) => {
        const payload = decodeJwt(accessToken);
        const user: User | null = payload
          ? { id: payload.sub, role: payload.role }
          : null;

        set({
          token: accessToken,
          refreshToken,
          user,
          isAuthenticated: true,
        });
      },

      setTokens: (accessToken: string, refreshToken: string) => {
        set({ token: accessToken, refreshToken });
      },

      logout: () => {
        // Capture both tokens BEFORE clearing: the revocation below needs the
        // access token, and once set() runs, persisted storage already holds
        // null for both.
        const { refreshToken, token } = get();

        set({
          token: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        });

        // Tell the server to blacklist the refresh token. Without this the
        // token stays valid server-side until it expires, so "log out" only
        // ever cleared the browser. Best-effort: the local session is already
        // gone and a failure here must not resurrect it.
        if (refreshToken) {
          void revokeRefreshToken(refreshToken, token).catch(() => undefined);
        }
      },
    }),
    {
      name: "auth-storage",
    },
  ),
);
