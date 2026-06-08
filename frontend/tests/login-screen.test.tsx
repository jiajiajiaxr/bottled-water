import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { App as AntApp } from "antd";
import { LoginScreen } from "@/features/auth/components/LoginScreen";

vi.mock("@/api", () => ({
  api: {
    login: vi.fn(),
    register: vi.fn(),
    demoLogin: vi.fn(),
  },
}));

vi.mock("@/assets/login-illustration.svg", () => ({
  default: "login-illustration.svg",
}));

describe("LoginScreen", () => {
  it("renders the login experience", () => {
    render(
      <AntApp>
        <LoginScreen onLogin={vi.fn()} />
      </AntApp>,
    );

    expect(screen.getByText("欢迎回来")).toBeInTheDocument();
    expect(screen.getByTestId("demo-login")).toBeInTheDocument();
    expect(screen.getByLabelText("AgentHub 登录")).toBeInTheDocument();
  });
});
