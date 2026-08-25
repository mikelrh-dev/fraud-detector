import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  MotionList,
  MOTION_STAGGER_MAX_INDEX,
} from "../components/MotionList";

describe("MotionList", () => {
  it("renders children inside a motion-stagger container", () => {
    const { container } = render(
      <MotionList>
        <div data-testid="item">one</div>
      </MotionList>,
    );
    const list = container.firstElementChild!;
    expect(list.className).toContain("motion-stagger");
    expect(screen.getByTestId("item")).toBeInTheDocument();
  });

  it("assigns sequential --i indexes to element children", () => {
    const { container } = render(
      <MotionList>
        {[0, 1, 2].map((n) => (
          <div key={n} data-testid={`item-${n}`} />
        ))}
      </MotionList>,
    );
    for (let n = 0; n < 3; n += 1) {
      const el = container.querySelector(`[data-testid="item-${n}"]`)!;
      expect(el.style.getPropertyValue("--i")).toBe(String(n));
    }
  });

  it("clamps --i at the stagger cap so accumulated delay stays bounded", () => {
    const count = MOTION_STAGGER_MAX_INDEX + 4;
    const { container } = render(
      <MotionList>
        {Array.from({ length: count }, (_, n) => (
          <div key={n} data-testid={`item-${n}`} />
        ))}
      </MotionList>,
    );
    // Indexes grow until the cap, then stay pinned at the cap.
    const capped = container.querySelector(
      `[data-testid="item-${count - 1}"]`,
    )! as HTMLElement;
    expect(capped.style.getPropertyValue("--i")).toBe(
      String(MOTION_STAGGER_MAX_INDEX),
    );
    const justOverCap = container.querySelector(
      `[data-testid="item-${MOTION_STAGGER_MAX_INDEX}"]`,
    )! as HTMLElement;
    expect(justOverCap.style.getPropertyValue("--i")).toBe(
      String(MOTION_STAGGER_MAX_INDEX),
    );
    const beforeCap = container.querySelector(
      `[data-testid="item-${MOTION_STAGGER_MAX_INDEX - 1}"]`,
    )! as HTMLElement;
    expect(beforeCap.style.getPropertyValue("--i")).toBe(
      String(MOTION_STAGGER_MAX_INDEX - 1),
    );
  });

  it("merges --i into existing inline styles instead of overwriting them", () => {
    const { container } = render(
      <MotionList>
        <div data-testid="styled" style={{ color: "red" }} />
      </MotionList>,
    );
    const el = container.querySelector("[data-testid='styled']")! as HTMLElement;
    expect(el.style.getPropertyValue("--i")).toBe("0");
    expect(el.style.color).toBe("red");
  });

  it("forwards className and DOM props to the container", () => {
    const { container } = render(
      <MotionList className="md:hidden space-y-3" aria-busy="true">
        <div />
      </MotionList>,
    );
    const list = container.firstElementChild!;
    expect(list.className).toContain("md:hidden");
    expect(list.className).toContain("space-y-3");
    expect(list.getAttribute("aria-busy")).toBe("true");
  });

  it("passes non-element children through without crashing", () => {
    render(
      <MotionList>
        {"plain text"}
        {null}
        <div data-testid="after-text" />
      </MotionList>,
    );
    expect(screen.getByText("plain text")).toBeInTheDocument();
    expect(screen.getByTestId("after-text")).toBeInTheDocument();
  });
});
