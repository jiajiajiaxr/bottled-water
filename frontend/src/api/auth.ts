import { request } from "./client";
import { demoUser } from "../mock";
import type { User } from "../types";

export async function login(name: string, password = "agenthub"): Promise<User> {
  try {
    const result = await request<{ access_token: string; user: User }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({
          username: name || "demo",
          email: name,
          password,
        }),
      },
    );
    window.localStorage.setItem("agenthub_token", result.access_token);
    return result.user;
  } catch {
    return {
      ...demoUser,
      id: `user-${Date.now()}`,
      name: name || demoUser.name,
      role: "member",
    };
  }
}

export async function register(payload: {
  email: string;
  username: string;
  password: string;
  display_name?: string;
}): Promise<User> {
  const result = await request<{ access_token: string; user: User }>(
    "/auth/signup",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
  window.localStorage.setItem("agenthub_token", result.access_token);
  return result.user;
}

export async function updateProfile(payload: {
  display_name?: string;
  name?: string;
  avatar_url?: string;
  settings?: Record<string, unknown>;
}): Promise<User> {
  return await request<User>("/auth/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function changePassword(payload: {
  current_password: string;
  new_password: string;
}): Promise<{ changed: boolean }> {
  return await request<{ changed: boolean }>("/auth/password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function demoLogin(): Promise<User> {
  try {
    const result = await request<{ access_token: string; user: User }>(
      "/auth/demo",
      { method: "POST" },
    );
    window.localStorage.setItem("agenthub_token", result.access_token);
    return result.user;
  } catch {
    return demoUser;
  }
}

export async function me(): Promise<User> {
  return await request<User>("/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await request<{ ok: boolean }>("/auth/logout", { method: "POST" });
  } finally {
    window.localStorage.removeItem("agenthub_token");
  }
}
