import { describe, expect, it } from "vitest";
import { buildPreviewDocument } from "../src/lib/preview";

describe("buildPreviewDocument", () => {
  it("renders complete html documents directly instead of escaping source", () => {
    const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head><title>简易计算器</title></head>
<body><button id="run">计算</button><script>window.ok = true;</script></body>
</html>`;

    const result = buildPreviewDocument(html);

    expect(result).toBe(html);
    expect(result).toContain("<button id=\"run\">计算</button>");
    expect(result).not.toContain("&lt;!DOCTYPE html&gt;");
  });

  it("embeds html fragments as runnable markup", () => {
    const result = buildPreviewDocument("<button>运行</button><script>window.ok = true;</script>");

    expect(result).toContain("<button>运行</button>");
    expect(result).toContain("<script>window.ok = true;</script>");
    expect(result).not.toContain("&lt;button&gt;");
  });

  it("escapes plain text fallback", () => {
    const result = buildPreviewDocument("hello <not-html>");

    expect(result).toContain("<pre>hello &lt;not-html&gt;</pre>");
  });
});
