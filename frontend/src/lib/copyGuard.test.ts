import { afterEach, describe, expect, it } from "vitest";

import { installCopyGuard, isEditableTarget, shouldBlockCopy } from "./copyGuard";

describe("copyGuard", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("treats page content as blocked and form fields as editable", () => {
    const paragraph = document.createElement("p");
    const input = document.createElement("input");
    const textarea = document.createElement("textarea");
    document.body.append(paragraph, input, textarea);

    expect(shouldBlockCopy(paragraph)).toBe(true);
    expect(isEditableTarget(input)).toBe(true);
    expect(shouldBlockCopy(textarea)).toBe(false);
  });

  it("prevents copy and context menu on page text but not in inputs", () => {
    const paragraph = document.createElement("p");
    paragraph.textContent = "lesson text";
    const input = document.createElement("input");
    document.body.append(paragraph, input);
    const uninstall = installCopyGuard();

    const copyPage = new Event("copy", { bubbles: true, cancelable: true });
    paragraph.dispatchEvent(copyPage);
    expect(copyPage.defaultPrevented).toBe(true);

    const menuPage = new Event("contextmenu", { bubbles: true, cancelable: true });
    paragraph.dispatchEvent(menuPage);
    expect(menuPage.defaultPrevented).toBe(true);

    const copyInput = new Event("copy", { bubbles: true, cancelable: true });
    input.dispatchEvent(copyInput);
    expect(copyInput.defaultPrevented).toBe(false);

    uninstall();
  });
});
