import { useEffect } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { App as AntApp } from "antd";
import { WorkflowStudioContent } from "../../features/workflow/WorkflowStudioContent";
import type { User } from "../../types";

export function WorkflowStudioPage({ user }: { user?: User }) {
  const params = useParams();
  const location = useLocation();
  const { message } = AntApp.useApp();
  const workspaceId = params.workspaceId
    ? decodeURIComponent(params.workspaceId)
    : "";
  const conversationId = params.conversationId
    ? decodeURIComponent(params.conversationId)
    : "";

  useEffect(() => {
    if (!workspaceId || !conversationId) {
      message.error("工作流路由缺少 workspaceId 或 conversationId");
    }
  }, [conversationId, message, workspaceId]);

  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (!workspaceId || !conversationId) return <Navigate to="/app" replace />;

  return (
    <WorkflowStudioContent
      workspaceId={workspaceId}
      conversationId={conversationId}
      onError={(value) => message.error(value)}
      onSuccess={(value) => message.success(value)}
    />
  );
}
