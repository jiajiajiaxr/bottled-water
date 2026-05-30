// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  artifactExportFormats,
  downloadLabel,
  isOfficeArtifact,
  preferredArtifactFormat,
  openOrDownloadExport,
} from "./artifactPreview";

describe("openOrDownloadExport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ["html", "text/html; charset=utf-8"],
    ["markdown", "text/markdown; charset=utf-8"],
    ["json", "application/json; charset=utf-8"],
  ])("downloads %s previewText through a Blob URL", (format, contentType) => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const createObjectURL = vi.fn(() => `blob:${format}-preview`);
    const open = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL });
    vi.stubGlobal("open", open);

    openOrDownloadExport(
      {
        previewText: "preview body",
        contentType,
        filename: `demo.${format}`,
      },
      format,
    );

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(open).not.toHaveBeenCalled();
  });

  it.each([
    [
      "docx",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    ["xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    ["pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    ["pdf", "application/pdf"],
    ["zip", "application/zip"],
  ])("downloads %s Blob URLs", (format, contentType) => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const open = vi.fn();
    vi.stubGlobal("open", open);

    openOrDownloadExport(
      {
        previewUrl: `blob:${format}`,
        contentType,
        filename: `demo.${format}`,
      },
      format,
    );

    expect(click).toHaveBeenCalledTimes(1);
    expect(open).not.toHaveBeenCalled();
  });

});

describe("artifact export semantics", () => {
  it.each(["docx", "pptx", "xlsx", "pdf", "html", "md", "json", "zip"])(
    "only exposes the current %s format",
    (format) => {
      const formats = artifactExportFormats(format);

      expect(formats).toEqual([format]);
    },
  );

  it("normalizes markdown and labels the primary download", () => {
    expect(artifactExportFormats("markdown")).toEqual(["md"]);
    expect(downloadLabel("md")).toBe("下载 MD");
    expect(downloadLabel("pdf")).toBe("下载 PDF");
  });

  it("prefers artifact.content.format over generic artifact type", () => {
    const format = preferredArtifactFormat({
      id: "artifact-1",
      conversationId: "conversation-1",
      type: "document",
      format: "docx",
      title: "Word",
      language: "html",
      code: "",
      previousCode: "",
      updatedAt: new Date().toISOString(),
      content: { format: "docx" },
    });

    expect(format).toBe("docx");
  });

  it("detects Office artifacts for PDF preview conversion", () => {
    expect(isOfficeArtifact({
      id: "artifact-1",
      conversationId: "conversation-1",
      type: "document",
      format: "docx",
      title: "Word",
      language: "html",
      code: "",
      previousCode: "",
      updatedAt: new Date().toISOString(),
      content: { format: "docx" },
    }, "docx")).toBe(true);
  });
});
