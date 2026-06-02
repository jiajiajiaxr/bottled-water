import { get, request } from "./client";
import type { UploadedFile } from "@/types";

export async function uploadFile(
  file: File,
  conversationId?: string,
  purpose = "attachment",
): Promise<UploadedFile> {
  const form = new FormData();
  form.append("file", file);
  if (conversationId) form.append("conversation_id", conversationId);
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
}> {
  return await get(`/files/${fileId}/download`);
}
