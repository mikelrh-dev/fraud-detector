import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import AlertsPage from "../pages/AlertsPage";
import { confirmFraud } from "../api/alerts";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import { makeAuthState } from "../test-utils/authState";
import type { ReactNode } from "react";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function mockAuth() {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = makeAuthState();
      return selector ? selector(state) : state;
    },
  );
}

/** One OPEN alert — the only state from which a verdict can be recorded. */
function openAlerts(count = 1) {
  server.use(
    http.get("*/api/v1/alerts", () =>
      HttpResponse.json({
        items: Array.from({ length: count }, (_, i) => ({
          id: `alert-${i}`,
          transaction_id: `1111111${i}-2222-3333-4444-555555555555`,
          status: "open",
          score: 88,
          threshold: 40,
          classification: "review",
          reviewed_by: null,
          reviewed_at: null,
          created_at: new Date().toISOString(),
        })),
        total: count,
        page: 1,
        page_size: 20,
      }),
    ),
  );
}

/**
 * An analyst who correctly identifies fraud had no way to record it.
 *
 * The queue offered "Revisar" and "Falso Pos." — look at it, and it's wrong.
 * There was no third option for "it's right", so a correct confirmation and an
 * unexamined alert left the row in the same state, and the only labelled
 * examples the backend could ever hold were false positives.
 *
 * This is thin wiring and deliberately nothing else: the confirm control is the
 * existing `ActionButton`, the dialog is the existing `ConfirmDialog`, and the
 * request goes through the existing mutation switch. Nothing about the alert
 * row, the response shape or the verdict's rendering is here — the label is
 * not on `AlertResponse` yet, which is a deliberate boundary recorded on the
 * schema.
 */
describe("AlertsPage — confirming fraud", () => {
  beforeEach(() => {
    mockAuth();
  });

  it("offers a confirm-fraud control on an open alert, in both modes", async () => {
    openAlerts(1);
    render(<AlertsPage />, { wrapper: createWrapper() });

    // Rendered once per responsive mode, like every other action on this page.
    const buttons = await screen.findAllByRole("button", {
      name: "Confirmar Fraude",
    });
    expect(buttons.length).toBeGreaterThanOrEqual(2);
  });

  it("carries the house touch floor, like every other action control", async () => {
    openAlerts(1);
    render(<AlertsPage />, { wrapper: createWrapper() });

    // `AlertsPage.touch.test.tsx` checks `max-md:min-h-[40px]` on three hardcoded
    // label strings, so a fourth action would silently escape it. Asserted here
    // so the new control is covered by name rather than by a list someone has to
    // remember to extend.
    for (const btn of await screen.findAllByRole("button", {
      name: "Confirmar Fraude",
    })) {
      expect(btn.className).toContain("max-md:min-h-[40px]");
      expect(btn.className).toContain("focus-visible:ring-2");
    }
  });

  it("is absent once the alert is no longer open", async () => {
    // Asserted in both directions in ONE test on purpose. A test that only
    // checks the control is missing passes against a page where the control
    // was never built at all, which is exactly what it did before the wiring
    // existed. The presence half is what makes the absence mean something.
    const alertBody = (status: string) =>
      HttpResponse.json({
        items: [
          {
            id: "alert-done",
            transaction_id: "11111111-2222-3333-4444-555555555555",
            status,
            score: 88,
            threshold: 40,
            classification: "review",
            reviewed_by: null,
            reviewed_at: null,
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      });

    // Positive half first: on an OPEN alert the control must be there.
    server.use(http.get("*/api/v1/alerts", () => alertBody("open")));
    const positive = render(<AlertsPage />, { wrapper: createWrapper() });
    expect(
      (await screen.findAllByRole("button", { name: "Confirmar Fraude" })).length,
    ).toBeGreaterThan(0);
    positive.unmount();

    // Negative half: a reviewed alert offers only Revertir.
    server.use(http.get("*/api/v1/alerts", () => alertBody("reviewed")));
    render(<AlertsPage />, { wrapper: createWrapper() });

    await screen.findAllByRole("button", { name: "Revertir" });
    expect(
      screen.queryByRole("button", { name: "Confirmar Fraude" }),
    ).toBeNull();
  });

  it("opens the shared dialog, asking for a reason, and names the verdict", async () => {
    openAlerts(1);
    const user = userEvent.setup();
    render(<AlertsPage />, { wrapper: createWrapper() });

    const btn = (await screen.findAllByRole("button", {
      name: "Confirmar Fraude",
    }))[0];
    await user.click(btn);

    const dialog = await screen.findByRole("dialog");
    // The title has to distinguish this from a false positive, or an analyst
    // confirming under the wrong dialog records the wrong verdict — and that
    // mistake is invisible afterwards, because both write `resolved`.
    expect(dialog.textContent).toContain("Confirmar Fraude");
    // Same reason control as the other two verdict actions.
    expect(screen.getByPlaceholderText("Razón (requerida)")).toBeTruthy();
  });

  it("POSTs to /confirm-fraud with the typed reason", async () => {
    openAlerts(1);
    let seen: { url: string; body: unknown } | null = null;
    server.use(
      http.post("*/api/v1/alerts/*/confirm-fraud", async ({ request }) => {
        // `request.url`, not `params.id`: msw does not expose that wildcard
        // under the name the pattern suggests, and asserting on an
        // always-undefined param is a test that passes nothing.
        seen = { url: request.url, body: await request.json() };
        return HttpResponse.json({
          id: "alert-0",
          transaction_id: "11111110-2222-3333-4444-555555555555",
          status: "resolved",
          score: 88,
          threshold: 40,
          classification: "review",
          reviewed_by: null,
          reviewed_at: null,
          created_at: new Date().toISOString(),
        });
      }),
    );

    const user = userEvent.setup();
    render(<AlertsPage />, { wrapper: createWrapper() });

    const btn = (await screen.findAllByRole("button", {
      name: "Confirmar Fraude",
    }))[0];
    await user.click(btn);
    await user.type(screen.getByPlaceholderText("Razón (requerida)"), "Cargo real");
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(seen).not.toBeNull());
    expect(seen!.url).toContain("/api/v1/alerts/alert-0/confirm-fraud");
    // `confirm_fraud`, not `false_positive`: the enum on the backend is
    // `^(review|false_positive|confirm_fraud|revert)$` and a mismatch is a 422
    // at the body parser.
    expect(seen!.body).toEqual({ action: "confirm_fraud", reason: "Cargo real" });
  });

  it("surfaces a failure through the dialog's own error slot", async () => {
    openAlerts(1);
    server.use(
      http.post("*/api/v1/alerts/*/confirm-fraud", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    render(<AlertsPage />, { wrapper: createWrapper() });

    const btn = (await screen.findAllByRole("button", {
      name: "Confirmar Fraude",
    }))[0];
    await user.click(btn);
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Error al ejecutar la acción");
  });
});

describe("alerts API client — confirmFraud", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("posts the verb the backend enum accepts", async () => {
    let seen: { path: string; body: unknown } | null = null;
    server.use(
      http.post("*/api/v1/alerts/*/confirm-fraud", async ({ request }) => {
        seen = { path: request.url, body: await request.json() };
        return HttpResponse.json({
          id: "alert-9",
          transaction_id: "11111111-2222-3333-4444-555555555555",
          status: "resolved",
          score: 88,
          threshold: 40,
          classification: "review",
          reviewed_by: null,
          reviewed_at: null,
          created_at: new Date().toISOString(),
        });
      }),
    );

    await confirmFraud("alert-9", "Fraude confirmado");

    expect(seen).not.toBeNull();
    expect(seen!.path).toContain("/api/v1/alerts/alert-9/confirm-fraud");
    expect(seen!.body).toEqual({
      action: "confirm_fraud",
      reason: "Fraude confirmado",
    });
  });
});
