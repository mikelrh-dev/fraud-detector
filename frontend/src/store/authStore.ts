import { create } from "zustand";
import { persist } from "zustand/middleware";
import { decodeJwt } from "../api/auth";

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
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
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

      logout: () => {
        set({
          token: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        });
      },
    }),
    {
      name: "auth-storage",
    },
  ),
);
