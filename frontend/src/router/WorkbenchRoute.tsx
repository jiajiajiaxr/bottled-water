import { useLocation, useNavigate, useParams, useSearchParams, Navigate } from "react-router-dom";
import { Workbench } from "@/pages/WorkbenchPage/Workbench";
import type { User } from "@/types";
import { normalizeMainTab } from "./utils";

interface WorkbenchRouteProps {
  user?: User;
  onLogout: () => void;
}

export function WorkbenchRoute({ user, onLogout }: WorkbenchRouteProps) {
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
      onRouteChange={(workspaceId, conversationId, options) => {
        const path = workspaceId
          ? conversationId
            ? `/app/${encodeURIComponent(workspaceId)}/c/${encodeURIComponent(conversationId)}`
            : `/app/${encodeURIComponent(workspaceId)}`
          : "/app";
        navigate(`${path}${buildSearch()}`, { replace: options?.replace });
      }}
      onRouteTabChange={(tab, options) => {
        navigate(`${location.pathname}${buildSearch(tab)}`, {
          replace: options?.replace,
        });
      }}
    />
  );
}
