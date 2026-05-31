import { useEffect, useState } from "react";
import { App as AntApp, Spin } from "antd";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "@/api";
import type { User } from "@/types";
import { LoginRoute } from "./LoginRoute";
import { WorkbenchRoute } from "./WorkbenchRoute";

export function AppRouter() {
  const [user, setUser] = useState<User>();
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    const token = window.localStorage.getItem("agenthub_token");
    if (!token) {
      setAuthReady(true);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => window.localStorage.removeItem("agenthub_token"))
      .finally(() => setAuthReady(true));
  }, []);

  if (!authReady) {
    return (
      <AntApp>
        <main className="login-shell">
          <Spin tip="Restoring session..." />
        </main>
      </AntApp>
    );
  }

  return (
    <AntApp>
      <Routes>
        <Route
          path="/login"
          element={<LoginRoute user={user} onLogin={setUser} />}
        />
        <Route
          path="/app"
          element={
            <WorkbenchRoute
              user={user}
              onLogout={() => {
                api.logout().finally(() => setUser(undefined));
              }}
            />
          }
        />
        <Route
          path="/app/:workspaceId"
          element={
            <WorkbenchRoute
              user={user}
              onLogout={() => {
                api.logout().finally(() => setUser(undefined));
              }}
            />
          }
        />
        <Route
          path="/app/:workspaceId/c/:conversationId"
          element={
            <WorkbenchRoute
              user={user}
              onLogout={() => {
                api.logout().finally(() => setUser(undefined));
              }}
            />
          }
        />
        <Route
          path="*"
          element={<Navigate to={user ? "/app" : "/login"} replace />}
        />
      </Routes>
    </AntApp>
  );
}
