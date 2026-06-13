import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCreateTransaction } from "./useCreateTransaction";
import { server } from "../tests/mocks/server";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const validPayload = {
  amount: 500,
  currency: "USD",
  merchant_name: "Test Store",
  card_last4: "1234",
  user_id: "00000000-0000-0000-0000-000000000001",
};

describe("useCreateTransaction", () => {
  it("returns a mutation function", () => {
    const { result } = renderHook(() => useCreateTransaction(), {
      wrapper: createWrapper(),
    });
    expect(result.current.mutate).toBeDefined();
    expect(result.current.mutateAsync).toBeDefined();
  });

  it("mutates successfully and returns a ScoreResponse", async () => {
    const { result } = renderHook(() => useCreateTransaction(), {
      wrapper: createWrapper(),
    });

    let data: unknown;
    result.current.mutate(validPayload, {
      onSuccess: (res) => {
        data = res;
      },
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(data).toBeDefined();
    expect((data as Record<string, unknown>)?.classification).toBe("legitimate");
    expect((data as Record<string, unknown>)?.ml_score).toBe(12.3);
  });

  it("calls onError when the API returns an error", async () => {
    // Override handler to return 500
    server.use(
      http.post("*/api/v1/transactions", () => {
        return HttpResponse.json({ detail: "Server error" }, { status: 500 });
      }),
    );

    const { result } = renderHook(() => useCreateTransaction(), {
      wrapper: createWrapper(),
    });

    let errorCaught = false;
    result.current.mutate(validPayload, {
      onError: () => {
        errorCaught = true;
      },
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(errorCaught).toBe(true);
  });
});
