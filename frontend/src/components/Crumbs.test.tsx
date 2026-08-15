import { act, type MutableRefObject } from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Crumbs } from "./Crumbs";
import { ChromePlayedContext, type ChromePlayed } from "./PageChrome";

const routerFuture = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

describe("Crumbs", () => {
  it("marks the last part as the current page and links earlier parts", () => {
    render(
      <MemoryRouter future={routerFuture}>
        <Crumbs
          parts={[
            { label: "Subjects", to: "/" },
            { label: "Mathematics" },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Subjects" })).toHaveAttribute("href", "/");
    expect(screen.getByText("Mathematics")).toHaveAttribute("aria-current", "page");
  });

  it("keeps the clicked parent as current after going back a level", async () => {
    const played: MutableRefObject<ChromePlayed> = {
      current: {
        crumb: "prev",
        parts: [
          { label: "Subjects", to: "/" },
          { label: "Mathematics", to: "/subjects/math-1" },
          { label: "Rectangles" },
        ],
      },
    };

    render(
      <ChromePlayedContext.Provider value={played}>
        <MemoryRouter future={routerFuture}>
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: "Mathematics" },
            ]}
          />
        </MemoryRouter>
      </ChromePlayedContext.Provider>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole("link", { name: "Subjects" })).toHaveAttribute("href", "/");
    expect(screen.getByText("Mathematics")).toHaveAttribute("aria-current", "page");
  });

  it("adds the opened folder as the current crumb when going in", async () => {
    const played: MutableRefObject<ChromePlayed> = {
      current: {
        crumb: "prev",
        parts: [{ label: "Subjects" }],
      },
    };

    render(
      <ChromePlayedContext.Provider value={played}>
        <MemoryRouter future={routerFuture}>
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: "Mathematics" },
            ]}
          />
        </MemoryRouter>
      </ChromePlayedContext.Provider>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole("link", { name: "Subjects" })).toHaveAttribute("href", "/");
    expect(screen.getByText("Mathematics")).toHaveAttribute("aria-current", "page");
  });
});
