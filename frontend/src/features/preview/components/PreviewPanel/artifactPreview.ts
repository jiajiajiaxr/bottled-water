import type { WorkspaceArtifact } from "../../../../types";

export interface ArtifactExportResult {
  previewUrl?: string;
  previewText?: string;
  contentType: string;
  filename?: string;
}

export function preferredArtifactFormat(artifact?: WorkspaceArtifact): string {
  const toolFormat =
    artifact?.format ??
    artifact?.content?.format ??
    artifact?.content?.tool_output?.format;
  if (toolFormat) return toolFormat.toLowerCase();
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

export function artifactExportFormats(preferredFormat: string): string[] {
  const normalized = preferredFormat === "web_app" ? "html" : preferredFormat;
  return Array.from(
    new Set([
      normalized,
      "pdf",
      "docx",
      "xlsx",
      "pptx",
      "html",
      "markdown",
      "json",
      "zip",
    ]),
  ).filter(Boolean);
}

export function openOrDownloadExport(
  exported: ArtifactExportResult,
  format: string,
) {
  const previewUrl = exported.previewUrl ?? previewTextUrl(exported);
  if (!previewUrl) return;
  const lowerFormat = format.toLowerCase();
  const shouldDownload =
    ["docx", "xlsx", "pptx", "zip"].includes(lowerFormat) ||
    exported.contentType.includes("officedocument") ||
    exported.contentType === "application/zip";
  if (!shouldDownload) {
    window.open(previewUrl, "_blank", "noopener,noreferrer");
    return;
  }
  const anchor = document.createElement("a");
  anchor.href = previewUrl;
  anchor.download = exported.filename || `agenthub-artifact.${lowerFormat}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function previewTextUrl(exported: ArtifactExportResult) {
  if (!exported.previewText) return undefined;
  return URL.createObjectURL(
    new Blob([exported.previewText], {
      type: exported.contentType || "text/plain;charset=utf-8",
    }),
  );
}
