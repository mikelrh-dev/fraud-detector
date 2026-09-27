import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";
import { AUTH_STORAGE_KEY } from "./auth";

const apiClient = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

/** Per-request flags we attach to the axios config. */
interface RetriableConfig extends InternalAxiosRequestConfig {
  /** Set once a request has already survived one refresh, to stop looping. */
  _retried?: boolean;
  /** Requests that must never trigger a refresh (auth endpoints, revocation). */
  skipAuthRefresh?: boolean;
}

function readPersistedState(): { token?: string; refreshToken?: string } {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw)?.state ?? {};
  } catch {
    return {};
  }
}

// Request interceptor: attach JWT token from store
apiClient.interceptors.request.use((config) => {
  // The persisted store is the source of truth here: it is what survives a
  // reload, and after a silent refresh it holds the new token.
  const { token } = readPersistedState();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * Single-flight refresh.
 *
 * A dashboard fires several queries at once, so an expired access token
 * produces a burst of concurrent 401s. Without a shared promise each one would
 * start its own refresh, and since refresh tokens rotate (the consumed one is
 * blacklisted server-side) the extra attempts would look like replay attacks
 * and burn the whole session.
 */
let inFlightRefresh: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken } = readPersistedState();
  if (!refreshToken) return null;

  try {
    // Bare axios, not apiClient: going through the instance would re-enter this
    // interceptor, and a 401 on the refresh call would recurse.
    const response = await axios.post(
      "/api/v1/auth/refresh",
      {},
      { headers: { Authorization: `Bearer ${refreshToken}` } },
    );

    const { access_token: accessToken, refresh_token: newRefreshToken } =
      response.data ?? {};

    if (!accessToken || !newRefreshToken) return null;

    // Update the persisted store so every later request picks up the new token.
    // Imported dynamically because the store imports this module's siblings.
    const { useAuthStore } = await import("../store/authStore");
    useAuthStore.getState().setTokens(accessToken, newRefreshToken);

    return accessToken;
  } catch {
    return null;
  }
}

function getRefreshedToken(): Promise<string | null> {
  if (!inFlightRefresh) {
    inFlightRefresh = refreshAccessToken().finally(() => {
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

const AUTH_ENDPOINTS = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"];

// Response interceptor: one silent refresh on 401, then give up cleanly
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined;
    const status = error.response?.status;
    const url = config?.url ?? "";

    const canRefresh =
      status === 401 &&
      config !== undefined &&
      !config._retried &&
      !config.skipAuthRefresh &&
      !AUTH_ENDPOINTS.some((endpoint) => url.includes(endpoint));

    if (canRefresh) {
      const accessToken = await getRefreshedToken();

      if (accessToken) {
        config._retried = true;
        config.headers.Authorization = `Bearer ${accessToken}`;
        return apiClient.request(config);
      }
    }

    // The session is genuinely over. Clear it and let ProtectedRoute redirect,
    // instead of `window.location.href`, which tore down the whole SPA and lost
    // every cache entry and in-progress filter.
    if (status === 401 && !url.includes("/auth/login")) {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }

    return Promise.reject(error);
  },
);

export default apiClient;
