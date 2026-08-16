import { describe, expect, it, vi } from "vitest";

import {
  crumbSlideDirection,
  getCrumbTrail,
  setCrumbTrail,
  subscribeCrumbTrail,
} from "./crumbTrail";

describe("crumbTrail", () => {
  it("notifies subscribers when the trail changes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeCrumbTrail(listener);
    setCrumbTrail([{ label: "Subjects", to: "/" }]);
    expect(getCrumbTrail()).toEqual([{ label: "Subjects", to: "/" }]);
    expect(listener).toHaveBeenCalled();
    setCrumbTrail(null);
    expect(getCrumbTrail()).toBeNull();
    unsubscribe();
  });

  it("slides forward from the right and back toward the right", () => {
    expect(crumbSlideDirection(1, 2)).toBe(1);
    expect(crumbSlideDirection(3, 2)).toBe(-1);
    expect(crumbSlideDirection(2, 2)).toBe(1);
  });
});
