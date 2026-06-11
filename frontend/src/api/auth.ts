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
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  role?: string;
}

/**
 * Authenticate user with username + password.
 * Returns JWT tokens.
 */
export async function login(data: LoginRequest): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>("/auth/login", data);
  return response.data;
}

/**
 * Register a new user (admin only).
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
 */
export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

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
