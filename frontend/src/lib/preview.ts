export function buildPreviewDocument(code: string) {
  const trimmed = code.trim();
  if (isFullHtmlDocument(trimmed)) {
    return trimmed;
  }

  const bodyContent = looksLikeHtmlFragment(trimmed)
    ? trimmed
    : `<pre>${escapeHtml(trimmed)}</pre>`;

  return `<!doctype html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #f7f8fb; color: #1f2937; }
    .stage { min-height: 100vh; padding: 28px; box-sizing: border-box; }
    .stage > * { max-width: 100%; }
    pre { white-space: pre-wrap; background: white; border: 1px solid #d9e1ec; padding: 18px; border-radius: 8px; }
  </style>
</head>
<body>
  <div class="stage">
    ${bodyContent}
  </div>
</body>
</html>`;
}

function isFullHtmlDocument(code: string): boolean {
  return /^<!doctype\s+html/i.test(code) || /<html[\s>]/i.test(code);
}

function looksLikeHtmlFragment(code: string): boolean {
  return /<\/?(?:div|section|main|article|header|footer|nav|form|button|input|select|textarea|canvas|table|ul|ol|li|h[1-6]|p|style|script)\b/i.test(
    code,
  );
}

function escapeHtml(code: string): string {
  const escaped = code.replace(/[&<>"']/g, (char) => {
    const map: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return map[char];
  });
  return escaped;
}
