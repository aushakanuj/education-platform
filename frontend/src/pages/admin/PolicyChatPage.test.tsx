import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as chatsApi from "../../api/chats";
import { PolicyChatPage } from "./PolicyChatPage";

vi.mock("../../api/chats", () => ({
  listChats: vi.fn(),
  createChat: vi.fn(),
  getChat: vi.fn(),
  deleteChat: vi.fn(),
  postChatMessage: vi.fn(),
}));

const sampleContext = { used_tokens: 120, limit_tokens: 8192, used_percent: 1 };

describe("PolicyChatPage", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    vi.mocked(chatsApi.listChats).mockResolvedValue([
      {
        id: "c1",
        title: "Attendance",
        updated_at: "2026-08-15T00:00:00Z",
        context: sampleContext,
      },
    ]);
    vi.mocked(chatsApi.getChat).mockResolvedValue({
      id: "c1",
      title: "Attendance",
      updated_at: "2026-08-15T00:00:00Z",
      context: sampleContext,
      messages: [
        {
          id: "m1",
          role: "assistant",
          content: "Ask a policy question.",
          created_at: "2026-08-15T00:00:00Z",
        },
      ],
    });
    vi.mocked(chatsApi.createChat).mockResolvedValue({
      id: "c2",
      title: "New chat",
      updated_at: "2026-08-15T00:00:00Z",
      context: sampleContext,
    });
    vi.mocked(chatsApi.postChatMessage).mockResolvedValue({
      user_message: {
        id: "m2",
        role: "user",
        content: "What is attendance policy?",
        created_at: "2026-08-15T00:01:00Z",
      },
      assistant_message: {
        id: "m3",
        role: "assistant",
        content: "Notify the office after three absences.",
        citations: [{ id: "1", label: "Handbook", excerpt: "three absences" }],
        created_at: "2026-08-15T00:01:01Z",
      },
      context: { used_tokens: 400, limit_tokens: 8192, used_percent: 5 },
    });
  });

  it("loads conversations, shows context percent, and sends a message", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PolicyChatPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Ask a policy question.")).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/Context window 1 percent/i)).toBeInTheDocument();
    expect(screen.getByText("Attendance", { selector: ".policy-chat__conv-title" })).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Message"),
      "What is attendance policy?",
    );
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(
        screen.getByText("Notify the office after three absences."),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Handbook")).toBeInTheDocument();
    expect(screen.getByLabelText(/Context window 5 percent/i)).toBeInTheDocument();
  });
});
