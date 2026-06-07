import { API_BASE, get, request, requestFile } from "./client";
import type { UploadedFile } from "@/types";

export async function uploadFile(
  file: File,
  conversationId?: string,
  purpose = "attachment",
  workspaceId?: string,
): Promise<UploadedFile> {
  const form = new FormData();
  form.append("file", file);
  if (conversationId) form.append("conversation_id", conversationId);
  if (workspaceId) form.append("workspace_id", workspaceId);
  form.append("purpose", purpose);
  return await request<UploadedFile>("/files/upload", {
    method: "POST",
    body: form,
  });
}

export async function files(conversationId?: string): Promise<UploadedFile[]> {
  const query = conversationId
    ? `?conversation_id=${encodeURIComponent(conversationId)}`
    : "";
  const result = await get<{ items: UploadedFile[] }>(`/files${query}`);
  return result.items;
}

export async function previewFile(
  fileId: string,
): Promise<{
  previewUrl?: string;
  previewText?: string;
  contentType: string;
  filename?: string;
  downloadUrl?: string;
  metadata?: Record<string, unknown>;
}> {
  const payload = await get<Record<string, unknown>>(`/files/${fileId}/preview`);
  const contentType = stringValue(payload.contentType ?? payload.content_type);
  const filename = stringValue(payload.filename);
  const previewText = stringValue(payload.previewText ?? payload.preview_text ?? payload.text);
  const downloadUrl = stringValue(payload.downloadUrl ?? payload.download_url);
  const mode = stringValue(payload.mode).toLowerCase();
  const shouldFetchBinaryPreview =
    Boolean(downloadUrl) &&
    (mode === "image" ||
      mode === "pdf" ||
      contentType.startsWith("image/") ||
      contentType.includes("application/pdf"));

  if (shouldFetchBinaryPreview) {
    const file = await requestFile(apiPath(downloadUrl));
    return {
      previewUrl: file.previewUrl,
      previewText: file.previewText ?? previewText,
      contentType: file.contentType || contentType,
      filename: file.filename || filename,
      downloadUrl,
      metadata: objectValue(payload.metadata),
    };
  }

  return {
    previewUrl: stringValue(payload.previewUrl ?? payload.preview_url),
    previewText,
    contentType,
    filename,
    downloadUrl,
    metadata: objectValue(payload.metadata),
  };
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : undefined;
}

function apiPath(url: string): string {
  if (url.startsWith(API_BASE)) return url.slice(API_BASE.length) || "/";
  return url;
}
