/** 颜色输入解析：支持中英文逗号、顿号、空格分隔，去空、去重、限个数。 */
export const MAX_COLORS = 4;

export function parseColors(input: string, max = MAX_COLORS): string[] {
  const parts = input
    .split(/[,，、;；\s]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of parts) {
    if (seen.has(p)) continue;
    seen.add(p);
    out.push(p);
    if (out.length >= max) break;
  }
  return out;
}
