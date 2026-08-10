import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ClassesPage } from "./ClassesPage";
import { TEACHER_SECTIONS } from "../../mocks/teacherAssignments";

describe("ClassesPage", () => {
  it("smoke-renders teacher class cards from fixtures", () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ClassesPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "My classes" })).toBeInTheDocument();
    expect(screen.queryByText(/class teacher/i)).not.toBeInTheDocument();

    for (const section of TEACHER_SECTIONS) {
      expect(screen.getByRole("link", { name: new RegExp(section.label) })).toBeInTheDocument();
    }
  });
});
