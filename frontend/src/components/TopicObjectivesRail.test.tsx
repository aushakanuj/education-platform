import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { TopicObjectivesRail } from "./TopicObjectivesRail";

describe("TopicObjectivesRail", () => {
  beforeEach(() => {
    window.localStorage.removeItem("ep.objectivesCollapsed");
  });

  it("collapses and expands objectives", () => {
    render(
      <TopicObjectivesRail
        objectives={["Define rectangles and squares based on their interior angles."]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Objectives" })).toBeInTheDocument();
    expect(
      screen.getByText("Define rectangles and squares based on their interior angles."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Collapse objectives" }));

    expect(screen.queryByRole("heading", { name: "Objectives" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand objectives" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    fireEvent.click(screen.getByRole("button", { name: "Expand objectives" }));

    expect(screen.getByRole("heading", { name: "Objectives" })).toBeInTheDocument();
  });

  it("renders nothing when there are no objectives", () => {
    const { container } = render(<TopicObjectivesRail objectives={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
