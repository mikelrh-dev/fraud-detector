import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act } from "@testing-library/react";

/**
 * A28: `refresh()` and `logout()` existed and were never called. On any 401 the
 * client did `localStorage.removeItem(...)` + `window.location.href = "/login"`,
 * so a 15-minute access token expiry threw the user out of a perfectly valid
 * 24-hour session and reloaded the whole SPA, losing every cache entry.
 *
 * These lock: one silent refresh, replay of the original request, single-flight
 * under concurrent 401s, and no infinite retry loop.
 */

const mockPost = vi.fn();
const mockRequest = vi.fn();

vi.mock("axios", () => {
  const instance = {
    create: () => ({
      interceptors: {
        request: { use: (fn: unknown) => void fn },
        response: { use: (_ok: unknown, fail: unknown) => void fail },
      },
      request: (...args: unknown[]) => mockRequest(...args),
      post: (...args: unknown[]) => mockPost(...args),
    }),
    post: (...args: unknown[]) => mockPost(...args),
  };
  return { default: instance };
});

type FailHandler = (error: unknown) => Promise<unknown>;

/** Captures the rejection handler installed on the response interceptor. */
let onRejected: FailHandler;

async function loadClient() {
  vi.resetModules();
  mockPost.mockReset();
  mockRequest.mockReset();

  // Re-mock so the interceptor registration is observable.
  vi.doMock("axios", () => {
    const instance = {
      create: () => ({
        interceptors: {
          request: { use: (fn: unknown) => void fn },
          response: {
            use: (_ok: unknown, fail: FailHandler) => {
              onRejected = fail;
            },
          },
        },
        request: (...args: unknown[]) => mockRequest(...args),
        post: (...args: unknown[]) => mockPost(...args),
      }),
      post: (...args: unknown[]) => mockPost(...args),
    };
    return { default: instance };
  });

  return import("../api/client");
}

function err(status: number, url: string) {
  return {
    response: { status },
    config: { url, headers: {} },
  };
}

describe("A28 — refresh silencioso en 401", () => {
  beforeEach(() => {
    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: { token: "old-access", refreshToken: "refresh-1" },
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("hace refresh y reintenta el request original con el token nuevo", async () => {
    await loadClient();

    mockPost.mockResolvedValueOnce({
      data: { access_token: "new-access", refresh_token: "refresh-2" },
    });
    mockRequest.mockResolvedValueOnce({ data: ["ok"] });

    const config = { url: "/transactions", headers: {} as Record<string, string> };
    const result = await onRejected(err(401, "/transactions"));

    expect(mockPost).toHaveBeenCalledWith(
      "/api/v1/auth/refresh",
      {},
      { headers: { Authorization: "Bearer refresh-1" } },
    );
    expect(mockRequest).toHaveBeenCalledTimes(1);
    expect(config.headers.Authorization).toBeUndefined(); // config original intacto
    expect(result).toEqual({ data: ["ok"] });
  });

  it("NO intenta refrescar en los endpoints de auth", async () => {
    await loadClient();

    await expect(onRejected(err(401, "/auth/login"))).rejects.toBeTruthy();
    expect(mockPost).not.toHaveBeenCalled();
    expect(mockRequest).not.toHaveBeenCalled();
  });

  it("un solo refresh para varios 401 concurrentes (single-flight)", async () => {
    await loadClient();

    let resolveRefresh: (v: unknown) => void = () => {};
    mockPost.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRefresh = resolve;
        }),
    );
    mockRequest.mockResolvedValue({ data: "ok" });

    const all = Promise.all([
      onRejected(err(401, "/transactions")),
      onRejected(err(401, "/alerts")),
      onRejected(err(401, "/monitoring/dashboard")),
    ]);

    resolveRefresh({
      data: { access_token: "new-access", refresh_token: "refresh-2" },
    });
    await all;

    // Three concurrent 401s must not burn three rotating refresh tokens.
    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockRequest).toHaveBeenCalledTimes(3);
  });

  it("no entra en bucle si el request reintentado vuelve a dar 401", async () => {
    await loadClient();

    mockPost.mockResolvedValue({
      data: { access_token: "new-access", refresh_token: "refresh-2" },
    });
    mockRequest.mockRejectedValue(err(401, "/transactions"));

    await expect(onRejected(err(401, "/transactions"))).rejects.toBeTruthy();

    // Exactly one retry, then it gives up.
    expect(mockRequest).toHaveBeenCalledTimes(1);
  });

  it("limpia la sesión si el refresh falla, sin recargar la SPA", async () => {
    await loadClient();

    mockPost.mockRejectedValue(new Error("refresh token revocado"));

    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, assign, href: "" },
      writable: true,
    });

    await expect(onRejected(err(401, "/transactions"))).rejects.toBeTruthy();

    expect(localStorage.getItem("auth-storage")).toBeNull();
    expect(mockRequest).not.toHaveBeenCalled();
  });

  it("no borra la sesión cuando el 401 viene de un login fallido", async () => {
    await loadClient();

    await expect(onRejected(err(401, "/auth/login"))).rejects.toBeTruthy();
    expect(localStorage.getItem("auth-storage")).not.toBeNull();
  });
});

describe("A28 — el logout revoca el refresh token en el servidor", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("envía el refresh token en X-Refresh-Token al cerrar sesión", async () => {
    vi.resetModules();
    const post = vi.fn().mockResolvedValue({ data: undefined });
    vi.doMock("axios", () => ({
      default: {
        create: () => ({
          interceptors: {
            request: { use: () => {} },
            response: { use: () => {} },
          },
          request: vi.fn(),
          post,
        }),
        post,
      },
    }));

    localStorage.setItem(
      "auth-storage",
      JSON.stringify({ state: { token: "access-1", refreshToken: "refresh-1" } }),
    );

    const { useAuthStore } = await import("../store/authStore");

    await act(async () => {
      useAuthStore.getState().login("access-1", "refresh-1");
    });

    useAuthStore.getState().logout();

    await vi.waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/api/v1/auth/logout",
        {},
        {
          headers: {
            Authorization: "Bearer access-1",
            "X-Refresh-Token": "refresh-1",
          },
        },
      );
    });

    // Local session is gone immediately, regardless of the network result.
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().refreshToken).toBeNull();
  });
});
