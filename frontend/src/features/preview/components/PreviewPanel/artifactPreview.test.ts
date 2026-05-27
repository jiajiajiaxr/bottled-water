// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import { artifactExportFormats, preferredArtifactFormat, openOrDownloadExport } from "./artifactPreview";

describe("openOrDownloadExport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ["html", "text/html; charset=utf-8"],
    ["markdown", "text/markdown; charset=utf-8"],
    ["json", "application/json; charset=utf-8"],
  ])("opens %s previewText through a Blob URL", (format, contentType) => {
    const open = vi.fn();
    const createObjectURL = vi.fn(() => `blob:${format}-preview`);
    vi.stubGlobal("open", open);
    vi.stubGlobal("URL", { ...URL, createObjectURL });

    openOrDownloadExport(
      {
        previewText: "preview body",
        contentType,
        filename: `demo.${format}`,
      },
      format,
    );

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(open).toHaveBeenCalledWith(`blob:${format}-preview`, "_blank", "noopener,noreferrer");
  });

  it.each([
    [
      "docx",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    ["xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    ["pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    ["zip", "application/zip"],
  ])("downloads %s Blob URLs instead of opening them", (format, contentType) => {
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

  it("opens PDF Blob URLs in a new tab", () => {
    const open = vi.fn();
    vi.stubGlobal("open", open);

    openOrDownloadExport(
      { previewUrl: "blob:pdf", contentType: "application/pdf", filename: "demo.pdf" },
      "pdf",
    );

    expect(open).toHaveBeenCalledWith("blob:pdf", "_blank", "noopener,noreferrer");
  });
});

describe("artifact export semantics", () => {
  it.each(["docx", "pptx", "xlsx", "pdf", "html"])(
    "puts current %s format first and keeps zip secondary",
    (format) => {
      const formats = artifactExportFormats(format);

      expect(formats[0]).toBe(format);
      expect(formats).toContain("zip");
      expect(formats.indexOf("zip")).toBeGreaterThan(0);
    },
  );

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
});
