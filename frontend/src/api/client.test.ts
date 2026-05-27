// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import { requestFile } from "./client";

describe("requestFile", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/pdf",
    "application/zip",
    "application/octet-stream",
  ])("treats %s as binary Blob", async (contentType) => {
    const createObjectURL = vi.fn(() => "blob:office-file");
    vi.stubGlobal("URL", { ...URL, createObjectURL });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(new Blob(["docx"]), {
          headers: {
            "content-type": contentType,
            "content-disposition": 'attachment; filename="demo.docx"',
          },
        }),
      ),
    );

    const result = await requestFile("/artifacts/a/export?format=docx");

    expect(result.previewUrl).toBe("blob:office-file");
    expect(result.previewText).toBeUndefined();
    expect(result.filename).toBe("demo.docx");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("uses RFC 5987 filename from Content-Disposition", async () => {
    const createObjectURL = vi.fn(() => "blob:pdf-file");
    vi.stubGlobal("URL", { ...URL, createObjectURL });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(new Blob(["pdf"]), {
          headers: {
            "content-type": "application/pdf",
            "content-disposition": "attachment; filename=\"fallback.pdf\"; filename*=UTF-8''%E7%A4%BA%E4%BE%8B.pdf",
          },
        }),
      ),
    );

    const result = await requestFile("/artifacts/a/export?format=pdf");

    expect(result.previewUrl).toBe("blob:pdf-file");
    expect(result.filename).toBe("示例.pdf");
  });

  it("keeps HTML export as preview text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<main>ok</main>", {
          headers: { "content-type": "text/html; charset=utf-8" },
        }),
      ),
    );

    const result = await requestFile("/artifacts/a/export?format=html");

    expect(result.previewText).toContain("<main>ok</main>");
    expect(result.previewUrl).toBeUndefined();
  });
});
