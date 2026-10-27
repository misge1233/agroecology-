// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Stepper } from "./stepper";

const steps = [
  { key: "location", label: "Location", reachable: true, complete: true },
  { key: "challenge", label: "Challenge", reachable: true, complete: false },
  { key: "objective", label: "Objective", reachable: false, complete: false },
];

describe("Stepper", () => {
  it("marks the current step, lets the user jump back, and locks future steps", () => {
    const onSelect = vi.fn();
    render(
      <Stepper
        steps={steps}
        current="challenge"
        onSelect={onSelect}
        label="Request steps"
        currentLabel="current step"
        completedLabel="completed"
      />
    );
    expect(screen.getByRole("navigation", { name: "Request steps" })).toBeInTheDocument();
    const current = screen.getByText(/Challenge, current step/).closest("[aria-current='step']");
    expect(current).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Location, completed/ }));
    expect(onSelect).toHaveBeenCalledWith("location");

    // Unreached steps are plain text, not buttons.
    expect(screen.queryByRole("button", { name: /Objective/ })).toBeNull();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });
});
