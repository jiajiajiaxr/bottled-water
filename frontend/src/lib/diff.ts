export function diffLines(previous: string, current: string) {
  const oldLines = previous.split("\n");
  const newLines = current.split("\n");
  const max = Math.max(oldLines.length, newLines.length);
  return Array.from({ length: max }, (_, index) => {
    const before = oldLines[index] ?? "";
    const after = newLines[index] ?? "";
    if (before === after) return { type: "same", text: after || " " };
    if (!before) return { type: "add", text: after };
    if (!after) return { type: "remove", text: before };
    return { type: "change", text: after, before };
  });
}
