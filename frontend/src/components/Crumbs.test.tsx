import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { CrumbHost, Crumbs, HostedCrumbs } from "./Crumbs";

describe("Crumbs", () => {
  it("renders the trail inline when there is no host", () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Crumbs
          parts={[
            { label: "Subjects", to: "/" },
            { label: "Mathematics" },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent(
      /Subjects\s*\/\s*Mathematics/,
    );
    expect(screen.getByRole("link", { name: "Subjects" })).toHaveAttribute("href", "/");
  });

  it("lifts the trail into the host without duplicating it", () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CrumbHost>
          <HostedCrumbs />
          <Crumbs
            parts={[
              { label: "Subjects", to: "/" },
              { label: "Mathematics" },
            ]}
          />
        </CrumbHost>
      </MemoryRouter>,
    );

    expect(screen.getAllByRole("navigation", { name: "Breadcrumb" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Subjects" })).toHaveAttribute("href", "/");
  });

  it("keeps local crumbs in the page when a host is present", () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CrumbHost>
          <HostedCrumbs />
          <Crumbs parts={[{ label: "Subjects" }]} />
          <Crumbs local parts={[{ label: "Units" }, { label: "History" }]} />
        </CrumbHost>
      </MemoryRouter>,
    );

    const navs = screen.getAllByRole("navigation", { name: "Breadcrumb" });
    expect(navs).toHaveLength(2);
    expect(navs[0]).toHaveTextContent("Subjects");
    expect(navs[1]).toHaveTextContent(/Units\s*\/\s*History/);
  });
});
