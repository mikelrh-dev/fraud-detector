import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "../components/EmptyState";

describe("EmptyState", () => {
  it("renders icon slot, title, hint and action", () => {
    const { container } = render(
      <EmptyState
        icon={<svg data-testid="icon-slot" />}
        title="No hay transacciones"
        hint="Registra la primera operación para comenzar."
        action={
          <a href="/transactions/new">Crear primera transacción</a>
        }
      />,
    );

    expect(screen.getByTestId("icon-slot")).toBeInTheDocument();
    expect(screen.getByText("No hay transacciones")).toBeInTheDocument();
    expect(
      screen.getByText("Registra la primera operación para comenzar."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Crear primera transacción"),
    ).toBeInTheDocument();
    // The action renders as an interactive link
    expect(container.querySelector("a")).not.toBeNull();
  });

  it("renders title only when hint and action are omitted", () => {
    const { container } = render(
      <EmptyState icon={<span data-testid="i" />} title="Sin alertas" />,
    );
    expect(screen.getByText("Sin alertas")).toBeInTheDocument();
    expect(container.querySelector("a")).toBeNull();
  });

  it("compact mode drops the tall vertical padding (table-cell usage)", () => {
    const full = render(
      <EmptyState icon={null} title="A" />,
    );
    const compact = render(
      <EmptyState icon={null} title="B" compact />,
    );
    const fullBlock = full.container.firstElementChild as HTMLElement;
    const compactBlock = compact.container.firstElementChild as HTMLElement;
    expect(fullBlock.className).toContain("py-12");
    expect(compactBlock.className).toContain("py-6");
    expect(compactBlock.className).not.toContain("py-12");
  });
});
