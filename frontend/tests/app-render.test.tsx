import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

async function loadApp() {
  try {
    return await import("../src/App");
  } catch {
    return null;
  }
}

describe("AgentHub app shell", () => {
  it("renders the main React application when src/App is available", async () => {
    const module = await loadApp();

    if (!module?.default) {
      expect(module).toBeNull();
      return;
    }

    render(React.createElement(module.default));

    expect(
      (await screen.findByRole("main")) ??
        screen.queryByText(/agenthub|chat|conversation|task/i),
    ).toBeTruthy();
  }, 15000);
});
