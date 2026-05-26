import { request } from "./client";
import { demoFiles } from "@/mock";
import type { UploadedFile } from "@/types";

export async function uploadFile(
  file: File,
  conversationId?: string,
  purpose = "attachment",
): Promise<UploadedFile> {
  try {
    const form = new FormData();
    form.append("file", file);
    if (conversationId) form.append("conversation_id", conversationId);
    form.append("purpose", purpose);
    return await request<UploadedFile>("/files/upload", {
      method: "POST",
      body: form,
    });
  } catch {
    return {
      id: `file-${Date.now()}`,
      filename: file.name,
      original_filename: file.name,
      content_type: file.type || "application/octet-stream",
      size: file.size,
      purpose,
      parse_status: "stored",
      created_at: new Date().toISOString(),
    };
  }
}

export async function files(conversationId?: string): Promise<UploadedFile[]> {
  try {
    const query = conversationId
      ? `?conversation_id=${encodeURIComponent(conversationId)}`
      : "";
    const result = await request<{ items: UploadedFile[] }>(`/files${query}`);
    return result.items;
  } catch {
    return demoFiles;
  }
}

export async function previewFile(
  fileId: string,
): Promise<{
  previewUrl?: string;
  previewText?: string;
  contentType: string;
  filename?: string;
}> {
  return await request(`/files/${fileId}/download`);
}
