import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LearningDirectory } from "../../api/types";
import { AdminMaterialsGradesPage } from "./AdminMaterialsGradesPage";

const authState = vi.hoisted(() => ({
  isDevMockSession: false,
}));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    isDevMockSession: authState.isDevMockSession,
  }),
}));

vi.mock("../../api/materials", () => ({
  fetchLearningDirectory: vi.fn(),
}));

vi.mock("../../api/adminIngest", () => ({
  uploadSubtopicMaterial: vi.fn(),
  pollMaterialVersionStatus: vi.fn(),
  isTerminalIngestStatus: (status: string) =>
    status === "ready" || status === "failed" || status === "published",
}));

import { pollMaterialVersionStatus, uploadSubtopicMaterial } from "../../api/adminIngest";
import { fetchLearningDirectory } from "../../api/materials";

const mockDirectory: LearningDirectory = {
  subjects: [
    {
      id: "subj-math-uuid",
      code: "MATH",
      name: "Mathematics",
      grade_name: "Grade 8",
      academic_period_name: "2025-2026",
      progress_percent: 0,
      topics: [
        {
          id: "topic-1-uuid",
          title: "Numbers",
          slug: "numbers",
          sequence: 1,
          progress_percent: 0,
          complete: false,
          objectives: [],
          subtopics: [
            {
              id: "st-1-uuid",
              title: "Place value",
              slug: "place-value",
              sequence: 1,
              has_lesson: true,
              lesson_completed: false,
              progress_percent: 0,
              quiz: null,
            },
          ],
          overall_quiz: null,
        },
      ],
    },
  ],
};

describe("AdminMaterialsGradesPage", () => {
  beforeEach(() => {
    authState.isDevMockSession = false;
    vi.mocked(fetchLearningDirectory).mockReset();
    vi.mocked(fetchLearningDirectory).mockResolvedValue(mockDirectory);
    vi.mocked(uploadSubtopicMaterial).mockReset();
    vi.mocked(pollMaterialVersionStatus).mockReset();
  });

  it("smoke-renders grade materials grid from live directory", async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AdminMaterialsGradesPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Materials" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();

    await waitFor(() => {
      expect(screen.getByRole("list")).toBeInTheDocument();
    });

    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 2, name: "8" })).toBeInTheDocument();
    expect(screen.getByText(/1 subjects · 1 published topics/i)).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveAttribute(
      "href",
      "/admin/materials/grades/grade-8",
    );
    expect(screen.queryByRole("heading", { level: 2, name: "1" })).not.toBeInTheDocument();
    expect(screen.queryByText(/draft/i)).not.toBeInTheDocument();
    expect(fetchLearningDirectory).toHaveBeenCalled();
  });

  it("enables upload and posts the curriculum ingest form", async () => {
    const user = userEvent.setup();
    vi.mocked(uploadSubtopicMaterial).mockResolvedValue({
      source_material_id: "mat-1",
      version_id: "ver-1",
      version_number: 1,
      title: "Place value",
      lifecycle_status: "processing",
      ingest_job_id: "job-1",
    });
    vi.mocked(pollMaterialVersionStatus).mockResolvedValue({
      id: "ver-1",
      source_material_id: "mat-1",
      version_number: 1,
      title: "Place value",
      lifecycle_status: "ready",
      failure_reason: null,
      chunk_count: 3,
    });

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AdminMaterialsGradesPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("list")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByLabelText(/subtopic/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/subtopic/i), "st-1-uuid");
    await user.clear(screen.getByLabelText(/^title$/i));
    await user.type(screen.getByLabelText(/^title$/i), "Place value PDF");

    const file = new File(["%PDF-1.4"], "place-value.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/pdf file/i), { target: { files: [file] } });
    await user.click(screen.getByRole("button", { name: /upload pdf/i }));

    await waitFor(() => {
      expect(uploadSubtopicMaterial).toHaveBeenCalled();
    });

    const [subtopicId, uploadedFile, title] = vi.mocked(uploadSubtopicMaterial).mock.calls[0]!;
    expect(subtopicId).toBe("st-1-uuid");
    expect(uploadedFile).toBeInstanceOf(File);
    expect(title).toBe("Place value PDF");
    expect(pollMaterialVersionStatus).toHaveBeenCalledWith("ver-1", expect.any(Object));
    expect(await screen.findByText(/ready/i)).toBeInTheDocument();
  });

  it("shows a clear error for fixture mock sessions without JWT", async () => {
    authState.isDevMockSession = true;

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AdminMaterialsGradesPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/real admin JWT/i);
    });
    expect(fetchLearningDirectory).not.toHaveBeenCalled();
  });
});
