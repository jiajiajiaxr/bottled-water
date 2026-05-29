import { App as AntApp, Spin } from "antd";
import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api } from "./api";
import { LoginScreen } from "./features/auth/components/LoginScreen";
import { DocsPage } from "./pages/DocsPage";
import { Workbench } from "./pages/WorkbenchPage/Workbench";
import {
  conversationRoutePath,
  workflowRoutePath,
} from "./lib/workflowRoutes";
import type { User } from "./types";

const MAIN_TABS = new Set(["chat", "agents", "workspace", "settings"]);

function normalizeMainTab(
  value: string | null,
): "chat" | "agents" | "workspace" | "settings" {
  return MAIN_TABS.has(value ?? "")
    ? (value as "chat" | "agents" | "workspace" | "settings")
    : "chat";
}

function LoginRoute({
  user,
  onLogin,
}: {
  user?: User;
  onLogin: (user: User) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  if (user) return <Navigate to="/app" replace />;
  return (
    <LoginScreen
      onLogin={(nextUser) => {
        onLogin(nextUser);
        const from = (
          location.state as {
            from?: { pathname?: string; search?: string };
          } | null
        )?.from;
        const target =
          from?.pathname && from.pathname !== "/login"
            ? `${from.pathname}${from.search ?? ""}`
            : "/app";
        navigate(target, { replace: true });
      }}
    />
  );
}

function WorkbenchRoute({
  user,
  onLogout,
  routeView = "chat",
}: {
  user?: User;
  onLogout: () => void;
  routeView?: "chat" | "workflow";
}) {
  const params = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;

  const routeTab = normalizeMainTab(searchParams.get("tab"));
  const routeWorkspaceId = params.workspaceId
    ? decodeURIComponent(params.workspaceId)
    : undefined;
  const routeConversationId = params.conversationId
    ? decodeURIComponent(params.conversationId)
    : undefined;
  const buildSearch = (tab = routeTab) =>
    tab && tab !== "chat" ? `?tab=${encodeURIComponent(tab)}` : "";

  return (
    <Workbench
      user={user}
      onLogout={onLogout}
      routeWorkspaceId={routeWorkspaceId}
      routeConversationId={routeConversationId}
      routeTab={routeTab}
      routeView={routeView}
      onRouteChange={(workspaceId, conversationId, options) => {
        const path = conversationRoutePath(workspaceId, conversationId);
        navigate(`${path}${buildSearch()}`, { replace: options?.replace });
      }}
      onRouteTabChange={(tab, options) => {
        navigate(`${location.pathname}${buildSearch(tab)}`, {
          replace: options?.replace,
        });
      }}
      onOpenWorkflowPage={(workspaceId, conversationId) => {
        navigate(workflowRoutePath(workspaceId, conversationId));
      }}
      onCloseWorkflowPage={(workspaceId, conversationId) => {
        navigate(conversationRoutePath(workspaceId, conversationId), {
          replace: true,
        });
      }}
    />
  );
}

function RoutedApp() {
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
        <Route path="/docs" element={<DocsPage />} />
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
          path="/workspaces/:workspaceId/conversations/:conversationId/workflow"
          element={
            <WorkbenchRoute
              user={user}
              routeView="workflow"
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

export default function App() {
  return (
    <BrowserRouter>
      <RoutedApp />
    </BrowserRouter>
  );
}
