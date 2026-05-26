import { request } from "./client";
import type { ToolDefinition, ToolInvokeResponse } from "@/types";

export async function tools(workspaceId?: string): Promise<ToolDefinition[]> {
  try {
    const query = workspaceId
      ? `?workspace_id=${encodeURIComponent(workspaceId)}`
      : "";
    const result = await request<{ items: ToolDefinition[] }>(
      `/tools${query}`,
    );
    return result.items;
  } catch {
    return [
      {
        id: "file.extract_text",
        name: "file.extract_text",
        display_name: "提取文本",
        description: "从上传文件提取可供模型读取的文本。",
        category: "file",
        type: "builtin",
        status: "active",
        version: "1.0.0",
        permissions: ["file:read"],
        tags: ["file"],
        is_builtin: true,
      },
      {
        id: "artifact.create_pdf",
        name: "artifact.create_pdf",
        display_name: "生成 PDF",
        description: "创建 PDF 产物并返回产物卡片。",
        category: "artifact",
        type: "builtin",
        status: "active",
        version: "1.0.0",
        permissions: ["artifact:create"],
        tags: ["artifact"],
        is_builtin: true,
      },
    ];
  }
}

export async function createTool(payload: {
  workspace_id?: string;
  name: string;
  display_name?: string;
  description: string;
  category: string;
  type?: string;
  permissions?: string[];
  implementation?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
  tags?: string[];
}): Promise<ToolDefinition> {
  return await request<ToolDefinition>("/tools", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function generateTool(payload: {
  workspace_id?: string;
  name?: string;
  intent: string;
  requirements?: string;
  category?: string;
  allowed_permissions?: string[];
  tags?: string[];
}): Promise<ToolDefinition> {
  return await request<ToolDefinition>("/tools/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function invokeTool(
  toolId: string,
  argumentsValue: Record<string, unknown> = {},
  workspaceId?: string,
): Promise<ToolInvokeResponse> {
  return await request<ToolInvokeResponse>(
    `/tools/${encodeURIComponent(toolId)}/invoke`,
    {
      method: "POST",
      body: JSON.stringify({
        arguments: argumentsValue,
        workspace_id: workspaceId,
      }),
    },
  );
}

export async function deleteTool(toolId: string): Promise<{ id: string; deleted: boolean }> {
  return await request<{ id: string; deleted: boolean }>(
    `/tools/${encodeURIComponent(toolId)}`,
    { method: "DELETE" },
  );
}
