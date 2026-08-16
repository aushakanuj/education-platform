import { describe, expect, it, vi } from "vitest";

import {
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
});
