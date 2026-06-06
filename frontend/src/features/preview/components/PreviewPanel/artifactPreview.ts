import type { WorkspaceArtifact } from "../../../../types";

export interface ArtifactExportResult {
  previewUrl?: string;
  previewText?: string;
  contentType: string;
  filename?: string;
}

export function preferredArtifactFormat(artifact?: WorkspaceArtifact): string {
  const toolFormat =
    artifact?.content?.format ??
    artifact?.format ??
    artifact?.content?.tool_output?.format;
  if (toolFormat) return normalizeArtifactFormat(toolFormat);
  if (artifact?.type === "document") return "pdf";
  if (artifact?.type === "spreadsheet") return "xlsx";
  if (artifact?.type === "slides") return "pptx";
  return "html";
}

export function isPdfArtifact(artifact: WorkspaceArtifact | undefined, format: string) {
  return (
    format === "pdf" ||
    artifact?.media_type === "application/pdf" ||
    artifact?.content?.media_type === "application/pdf" ||
    artifact?.content?.tool_output?.media_type === "application/pdf"
  );
}

export function isOfficeArtifact(artifact: WorkspaceArtifact | undefined, format: string) {
  const normalized = normalizeArtifactFormat(format);
  const mediaType = [
    artifact?.media_type,
    artifact?.content?.media_type,
    artifact?.content?.tool_output?.media_type,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const filename = artifact?.filename ?? artifact?.content?.filename ?? "";
  return (
    ["docx", "pptx", "xlsx"].includes(normalized) ||
    mediaType.includes("officedocument") ||
    /\.(docx|pptx|xlsx)$/i.test(filename)
  );
}

export function artifactExportFormats(preferredFormat: string): string[] {
  return [normalizeArtifactFormat(preferredFormat)];
}

export function openOrDownloadExport(
  exported: ArtifactExportResult,
  format: string,
) {
  const downloadUrl = exported.previewUrl ?? previewTextUrl(exported);
  if (!downloadUrl) return;
  const lowerFormat = normalizeArtifactFormat(format);
  const anchor = document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download =
    exported.filename || `agenthub-artifact.${extensionForFormat(lowerFormat)}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function downloadLabel(format: string) {
  return `下载 ${displayFormat(format)}`;
}

function normalizeArtifactFormat(format: string) {
  const normalized = format.toLowerCase().replace(/^\./, "");
  if (normalized === "web_app" || normalized === "htm") return "html";
  if (normalized === "markdown") return "md";
  return normalized;
}

function displayFormat(format: string) {
  const normalized = normalizeArtifactFormat(format);
  return normalized === "md" ? "MD" : normalized.toUpperCase();
}

function extensionForFormat(format: string) {
  return normalizeArtifactFormat(format);
}

function previewTextUrl(exported: ArtifactExportResult) {
  if (!exported.previewText) return undefined;
  return URL.createObjectURL(
    new Blob([exported.previewText], {
      type: exported.contentType || "text/plain;charset=utf-8",
    }),
  );
}
