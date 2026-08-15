import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PageChrome } from "./PageChrome";
import { RouteMotion } from "./RouteMotion";

describe("PageChrome", () => {
  it("renders crumbs outside the fading route page", async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RouteMotion>
          <PageChrome>
            <nav aria-label="Breadcrumb">Subjects</nav>
          </PageChrome>
          <p>Fading body</p>
        </RouteMotion>
      </MemoryRouter>,
    );

    const crumbs = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(crumbs.closest(".route-motion__page")).toBeNull();
    expect(crumbs.closest(".route-motion__chrome")).not.toBeNull();
    expect(screen.getByText("Fading body").closest(".route-motion__page")).not.toBeNull();
  });
});
