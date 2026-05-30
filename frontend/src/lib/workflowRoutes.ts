export function conversationRoutePath(
  workspaceId?: string,
  conversationId?: string,
) {
  if (!workspaceId) return "/app";
  if (!conversationId) return `/app/${encodeURIComponent(workspaceId)}`;
  return `/app/${encodeURIComponent(workspaceId)}/c/${encodeURIComponent(conversationId)}`;
}

export function workflowRoutePath(workspaceId: string, conversationId: string) {
  return `/workspaces/${encodeURIComponent(workspaceId)}/conversations/${encodeURIComponent(conversationId)}/workflow`;
}

export function workspaceFilesRoutePath(workspaceId: string) {
  return `/workspaces/${encodeURIComponent(workspaceId)}/files`;
}
