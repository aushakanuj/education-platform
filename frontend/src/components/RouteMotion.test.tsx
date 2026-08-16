import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RouteMotion } from "./RouteMotion";

describe("RouteMotion", () => {
  it("renders the page body in the fading wrapper", () => {
    render(
      <MemoryRouter
        initialEntries={["/subjects/math"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/subjects/:subjectId"
            element={
              <RouteMotion>
                <div>Lesson body</div>
              </RouteMotion>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Lesson body")).toBeInTheDocument();
    expect(document.querySelector(".route-motion__page")).toBeTruthy();
  });
});
