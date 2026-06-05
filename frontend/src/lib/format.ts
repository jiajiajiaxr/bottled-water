export function formatTime(value?: string) {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatFileSize(size?: number) {
  if (!size) return "0KB";
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)}MB`;
  return `${Math.max(1, Math.ceil(size / 1024))}KB`;
}

/**
 * 将逗号分隔的字符串解析为去重空格的字符串数组。
 *
 * 常用于表单中标签、工具参数、权限列表等字段的解析。
 */
export function parseList(value?: string): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
