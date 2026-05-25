export function buildPreviewDocument(code: string) {
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

  return `<!doctype html>
<html>
<head>
  <style>
    body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #f7f8fb; color: #1f2937; }
    .stage { min-height: 100vh; display: grid; place-items: center; padding: 28px; box-sizing: border-box; }
    .landing { width: min(560px, 100%); background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 32px; box-shadow: 0 24px 70px rgba(15, 23, 42, .12); }
    h1 { margin: 0 0 12px; font-size: 34px; line-height: 1.08; color: #0f172a; }
    p { margin: 0 0 22px; color: #536071; line-height: 1.7; }
    button { border: 0; background: #1677ff; color: white; padding: 10px 18px; border-radius: 8px; font-weight: 700; }
    pre { white-space: pre-wrap; background: white; border: 1px solid #d9e1ec; padding: 18px; border-radius: 8px; }
  </style>
</head>
<body>
  <div class="stage">
    ${code.includes("<section") || code.includes("<main") ? code : `<pre>${escaped}</pre>`}
  </div>
</body>
</html>`;
}
