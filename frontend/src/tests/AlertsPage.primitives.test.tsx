import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import AlertsPage from "../pages/AlertsPage";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import { makeAuthState } from "../test-utils/authState";
import type { ReactNode } from "react";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

const ALERTS_SOURCE = readFileSync(
  join(process.cwd(), "src", "pages", "AlertsPage.tsx"),
  "utf-8",
);

/**
 * Source with block comments removed, so the page's own notes about class
 * names it kept are not counted as re-typing them.
 */
const ALERTS_CODE = ALERTS_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "");

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

/**
 * One alert, status `reviewed`, so the "Revertir" action is the only one
 * rendered — which is what opens the dialog with the reason textarea, the
 * control this page's focus-ring decision is about.
 */
function singleReviewedAlert() {
  server.use(
    http.get("*/api/v1/alerts", () =>
      HttpResponse.json({
        items: [
          {
            id: "alert-review",
            transaction_id: "11111111-2222-3333-4444-555555555555",
            status: "reviewed",
            score: 62,
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
      }),
    ),
  );
}

/** Opens the reason dialog and returns its textarea. */
async function openReasonDialog(): Promise<HTMLTextAreaElement> {
  const user = userEvent.setup();
  render(<AlertsPage />, { wrapper: createWrapper() });

  // The mobile card list and the desktop table both render the action, so the
  // first match is whichever mounted first; both open the same dialog.
  const revert = (await screen.findAllByRole("button", { name: "Revertir" }))[0];
  await user.click(revert);

  // `getByPlaceholderText` is typed `HTMLElement` by default; the dialog's
  // reason control is a real `<textarea>`, and every caller below types it.
  return screen.getByPlaceholderText<HTMLTextAreaElement>("Razón (requerida)");
}

/**
 * The Task 7 contract for this page, which is mostly a NON-migration.
 *
 * The page's controls have no entry in the design system, so the deliverable
 * here is the decision and its pin: the one focus-ring divergence in the
 * product is preserved rather than silently flattened, and the reasons the
 * other controls were left alone are written down where the next person will
 * read them.
 */
describe("AlertsPage — primitives migration", () => {
  beforeEach(() => {
    mockAuth();
  });

  it("the reason field's divergent focus ring is preserved, not silently flattened", async () => {
    // THE decision this page had to make. This focus ring is not `FOCUS_RING`:
    // it is `focus:ring-accent/40` — accent at 40% opacity — where
    // `FOCUS_RING` and everything built on it use the `--color-focus-ring`
    // token at full strength. Flattening it shifts the hue #dc2626 → #ef4444
    // AND the opacity 40% → 100%, and it would also drop the bare `focus:`
    // prefix that makes it paint on mouse click.
    //
    // It is not the ONLY divergence in the product, whatever an earlier version
    // of this comment said: `AUTH_INPUT_CLASS` carries a third ring,
    // `focus:ring-risk-critical/25`. Two divergences, and this test pins only
    // this one, on this page.
    //
    // Asserted as the value it has, not as the value the design system wants,
    // because preserving it is the decision. Falsifiable both ways: normalising
    // to `FOCUS_RING` fails the first assertion, and deleting the ring fails
    // the second. A silent hue change is what this file exists to prevent.
    const textarea = await openReasonDialog();

    expect(textarea.classList.contains("focus:ring-2")).toBe(true);
    expect(textarea.classList.contains("focus:ring-accent/40")).toBe(true);
    // The full-strength house ring must NOT be on this control. Note what this
    // is NOT: the previous comment here cited a `focus:`-prefixed
    // focus-ring rule together with a byte offset, and no such rule is emitted
    // anywhere in the built stylesheet — the house ring is `focus-visible:`-
    // prefixed, so the stylesheet has no `focus:`-prefixed variant of the
    // focus-ring token to compete with. The assertion below is about the
    // `focus-visible:` token, and the real reason it cannot simply be "solved"
    // by passing both is that `focus:` and `focus-visible:` are DIFFERENT
    // STATES: both would apply, each in its own state, and a mouse click would
    // still paint the 40% accent ring. No stylesheet order reaches across
    // states.
    expect(textarea.classList.contains("focus-visible:ring-focus-ring")).toBe(
      false,
    );
  });

  it("the reason field keeps its own compact chrome, since no Textarea primitive exists", async () => {
    const textarea = await openReasonDialog();

    // `Input` renders an `<input>`, so there is nothing to migrate a
    // `<textarea>` into. The reason `INVALID_INPUT` lives in `lib/ui.ts`
    // rather than `Input.tsx` is so the next control primitive inherits it —
    // but that primitive has not been written.
    expect(textarea.tagName).toBe("TEXTAREA");
    expect(textarea.classList.contains("w-full")).toBe(true);
    expect(textarea.classList.contains("px-3")).toBe(true);
    expect(textarea.classList.contains("py-2")).toBe(true);
    expect(textarea.classList.contains("text-slate-200")).toBe(true);
  });

  it("the filter tabs and action buttons keep the treatments that have no variant", async () => {
    singleReviewedAlert();
    render(<AlertsPage />, { wrapper: createWrapper() });

    const tab = await screen.findByRole("button", { name: "Todas" });
    // A segmented filter needs a SELECTED state `BTN_VARIANTS` does not
    // define, and it is `rounded-full`, which a `Button` would lose: Tailwind
    // emits `rounded`, `rounded-full` and `rounded-lg` in that stylesheet
    // order, so the later `rounded-lg` in `BTN_SIZES` wins regardless of
    // attribute order, and the tabs stop being tabs.
    expect(tab.classList.contains("rounded-full")).toBe(true);
    expect(tab.classList.contains("bg-slate-700")).toBe(true);
    // These two assertions USED to pin the absence of a focus ring, as "the
    // accessibility cost of the gap". That was true and it was a defect: a
    // keyboard user tabbing the filter row got no indicator at all. They are
    // flipped, not deleted, and the flip is the record of the fix.
    //
    // The conflation being undone is the one the page's own comment made --
    // that the missing `BTN_VARIANTS` entry CAUSED the missing ring. It did
    // not. A ring is one orthogonal token, composing it changes no fill, no
    // radius and no size, and the selected-state variant is still owed and
    // still not made. `filter-rows.a11y.test.tsx` now enumerates every control
    // in every filter row, so a fifth pill without a ring goes red on its own
    // rather than waiting to be noticed.
    expect(tab.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(tab.classList.contains("focus-visible:ring-focus-ring")).toBe(true);

    const action = (await screen.findAllByRole("button", { name: "Revertir" }))[0];
    // A tonal `*/10` fill at `text-[11px] px-2 py-1 rounded`. `rounded` also
    // sorts before `rounded-lg`, so a `Button` would change the corner.
    expect(action.classList.contains("rounded")).toBe(true);
    expect(action.classList.contains("text-[11px]")).toBe(true);
    expect(action.classList.contains("bg-risk-warn/10")).toBe(true);
    expect(action.classList.contains("max-md:min-h-[40px]")).toBe(true);
    expect(action.classList.contains("focus-visible:ring-2")).toBe(true);
  });

  it("the dialog is still a sibling of PageTransition, not inside it", async () => {
    // Load-bearing placement, not tidiness. `PageTransition`'s
    // `animation-fill-mode: both` persists the `to` keyframe's transform as
    // `matrix(1, 0, 0, 1, 0, 0)` — not `none` — and any transformed ancestor
    // contains `position: fixed`. Inside the wrapper the dialog's
    // `fixed inset-0` backdrop measured 1241x4000 and clipped; outside any
    // transform it measured 1241x581, the viewport.
    //
    // Asserted structurally, because that is what can be observed in jsdom,
    // and asserted because `Modal` now portals but `ConfirmDialog` does not —
    // so this invariant is the only thing standing between the next JSX tidy-up
    // and a dialog that renders as a full-height strip down the page.
    await openReasonDialog();

    const dialog = screen.getByRole("dialog");
    expect(dialog.closest(".animate-fade-slide-up")).toBeNull();
  });

  it("the dialog keeps ConfirmDialog's own error slot and aria-describedby", async () => {
    // The strongest reason the composition over `Modal` was declined: `Modal`
    // has no `error` prop, so the error would have had to travel as `children`
    // and `aria-describedby` on the panel would have gone with it. That is an
    // a11y regression traded for a refactor, so it is pinned here — this is the
    // behaviour the next person would break by composing the two.
    let reject = 0;
    server.use(
      http.post("*/api/v1/alerts/*/revert", () => {
        reject += 1;
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );

    const user = userEvent.setup();
    render(<AlertsPage />, { wrapper: createWrapper() });

    const revert = (await screen.findAllByRole("button", { name: "Revertir" }))[0];
    await user.click(revert);
    const dialog = screen.getByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(reject).toBe(1));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      "Error al ejecutar la acción",
    );
    expect(dialog.getAttribute("aria-describedby")).toBe(alert.getAttribute("id"));
  });

  it("the source no longer re-types a treatment the design system already defines", () => {
    // Only the treatments that HAVE a variant are asserted absent. The
    // tab/action/pagination treatments are deliberately still here, and their
    // tests assert them positively.
    expect(ALERTS_CODE).not.toContain("bg-accent");
    expect(ALERTS_CODE).not.toContain("hover:bg-action-hover");
    // The positive half, so the negative assertions cannot be satisfied by the
    // file simply not rendering these controls any more.
    expect(ALERTS_CODE).toContain("<ConfirmDialog");
  });
});
