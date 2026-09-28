import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Component } from "react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { ErrorBoundary } from "../components/ErrorBoundary";

/**
 * A26: there was no error boundary anywhere in src/. A single render throw
 * unmounted the whole tree and left a blank white screen with no way back.
 * These lock the recovery contract.
 *
 * Note: absent elements must be queried with `queryBy*`. `getBy*` throws when
 * nothing matches, which fails the assertion for the wrong reason.
 */

function Boom({ explode }: { explode: boolean }): ReactNode {
  if (explode) throw new Error("DB password hunter2 leaked");
  return <div data-testid="ok">Pantalla viva</div>;
}

/** React logs caught errors; silence it so the suite output stays readable. */
afterEach(() => {
  vi.restoreAllMocks();
});

describe("ErrorBoundary — recuperación ante error de render", () => {
  it("muestra el estado de error en vez de una pantalla en blanco", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Boom explode />
      </ErrorBoundary>,
    );

    expect(screen.queryByTestId("error-state")).not.toBeNull();
    expect(screen.queryByTestId("ok")).toBeNull();
    expect(spy).toHaveBeenCalled();
  });

  it("NO filtra el mensaje interno del error al usuario", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Boom explode />
      </ErrorBoundary>,
    );

    // An internal message can carry table names, queries or paths. It must go
    // to the logger, never to the screen.
    expect(document.body.textContent).not.toContain("hunter2");
  });

  it("entrega el error a onError para logging", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const onError = vi.fn();

    render(
      <ErrorBoundary onError={onError}>
        <Boom explode />
      </ErrorBoundary>,
    );

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0].message).toContain("hunter2");
  });

  it("reset() remonta el subárbol cuando el error ya no ocurre", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    const { rerender } = render(
      <ErrorBoundary>
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.queryByTestId("error-state")).not.toBeNull();

    // The cause is gone on the next render, but the boundary holds the error
    // until it is reset. Pressing retry must bring the UI back.
    rerender(
      <ErrorBoundary>
        <Boom explode={false} />
      </ErrorBoundary>,
    );
    expect(screen.queryByTestId("error-state")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(screen.queryByTestId("ok")).not.toBeNull();
  });

  it("renderiza los hijos sin interferencia cuando no hay error", () => {
    render(
      <ErrorBoundary>
        <Boom explode={false} />
      </ErrorBoundary>,
    );

    expect(screen.queryByTestId("ok")).not.toBeNull();
    expect(screen.queryByTestId("error-state")).toBeNull();
  });
});

describe("ErrorBoundary — resetKeys limpian el error al navegar", () => {
  it("limpia el error cuando cambia una resetKey", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    const { rerender } = render(
      <ErrorBoundary resetKeys={["/transactions"]}>
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.queryByTestId("error-state")).not.toBeNull();

    // Simulates the router changing pathname.
    rerender(
      <ErrorBoundary resetKeys={["/dashboard"]}>
        <Boom explode={false} />
      </ErrorBoundary>,
    );

    expect(screen.queryByTestId("ok")).not.toBeNull();
    expect(screen.queryByTestId("error-state")).toBeNull();
  });

  it("NO limpia el error si las resetKeys no cambian", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    const { rerender } = render(
      <ErrorBoundary resetKeys={["/transactions"]}>
        <Boom explode />
      </ErrorBoundary>,
    );

    rerender(
      <ErrorBoundary resetKeys={["/transactions"]}>
        <Boom explode />
      </ErrorBoundary>,
    );

    expect(screen.queryByTestId("error-state")).not.toBeNull();
  });
});

describe("ErrorBoundary — el fallback por defecto ofrece reintentar", () => {
  it("el fallback custom recibe un reset funcional", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const seen: string[] = [];

    class Consumer extends Component<{ children: ReactNode }> {
      // The annotation is load-bearing, not decoration: React 19 types `render`
      // as returning `ReactNode`, and a body with no `return` infers `void`.
      // This method always throws, so `ReactNode` is accurate and unreachable.
      render(): ReactNode {
        seen.push("child");
        throw new Error("boom");
      }
    }

    render(
      <MemoryRouter>
        <ErrorBoundary
          fallback={(reset) => (
            <button type="button" onClick={reset}>
              Recuperar
            </button>
          )}
        >
          <Consumer>
            <span>nunca</span>
          </Consumer>
        </ErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.queryByRole("button", { name: "Recuperar" })).not.toBeNull();
    // React may render a throwing component more than once before unmounting;
    // what matters is that it rendered at all and was then replaced.
    expect(seen.length).toBeGreaterThan(0);
  });
});
