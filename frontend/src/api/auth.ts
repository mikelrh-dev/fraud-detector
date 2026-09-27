import axios from "axios";
import apiClient from "./client";

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  role?: string;
}

/**
 * Authenticate user with email + password.
 * Returns JWT tokens.
 */
export async function login(data: LoginRequest): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>("/auth/login", data);
  return response.data;
}

/**
 * Register a new user (public registration).
 */
export async function register(data: RegisterRequest): Promise<UserResponse> {
  const response = await apiClient.post<UserResponse>("/auth/register", data);
  return response.data;
}

/**
 * Refresh access token using the current refresh token.
 */
export async function refresh(
  refreshToken: string,
): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>(
    "/auth/refresh",
    {},
    {
      headers: {
        Authorization: `Bearer ${refreshToken}`,
      },
    },
  );
  return response.data;
}

/**
 * Logout — blacklists the current token.
 *
 * Requires a valid access token, so this is a convenience for a live session.
 * For a real revocation at sign-out use `revokeRefreshToken`, which also sends
 * the refresh token.
 */
export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

/**
 * Revoke a refresh token server-side at sign-out.
 *
 * Sends both the access token (the endpoint authenticates with it) and the
 * refresh token via `X-Refresh-Token`, which makes the server blacklist the
 * pair instead of only the browser copy.
 *
 * Uses bare `axios` on purpose: going through `apiClient` would re-enter the
 * response interceptor, which reacts to 401 by attempting a refresh — during
 * logout, which is exactly the wrong moment and would recurse.
 *
 * Honest limitation: the endpoint depends on a valid access token, so if the
 * access token has already expired the refresh token is NOT revoked and the
 * call 401s. The local session is cleared regardless. Closing that gap needs a
 * backend endpoint that revokes by refresh token alone.
 */
export async function revokeRefreshToken(
  refreshToken: string,
  accessToken?: string | null,
): Promise<void> {
  // Prefer the token handed in by the caller. Reading it from storage here is
  // a fallback only: by the time logout runs, the store has usually already
  // been cleared, so a storage read would return null and the server would 401
  // without ever revoking the refresh token.
  const token = accessToken ?? readPersistedAccessToken();
  await axios.post(
    "/api/v1/auth/logout",
    {},
    {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        "X-Refresh-Token": refreshToken,
      },
    },
  );
}

/** Reads the access token from the persisted auth store, if present. */
function readPersistedAccessToken(): string | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw)?.state?.token ?? null;
  } catch {
    return null;
  }
}

export const AUTH_STORAGE_KEY = "auth-storage";

/** Decode JWT payload (base64url) to extract user info. */
export function decodeJwt(token: string): {
  sub: string;
  role: string;
  exp: number;
  iat: number;
} | null {
  try {
    const payload = token.split(".")[1];
    const decoded = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}
