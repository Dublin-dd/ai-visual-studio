export type ApiError = { error: { code: string; message: string } };

export async function readError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as ApiError;
    return data?.error?.message || `请求失败（${res.status}）`;
  } catch {
    return `请求失败（${res.status}）`;
  }
}

export async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const signal = init?.signal ?? AbortSignal.timeout(30_000);
  const res = await fetch(url, { ...init, signal });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as T;
}

export type Workspace = "ecommerce" | "drama";

export type ProjectOut = {
  cover_asset_id?: string | null;
  background_color?: string;
  id: string;
  name: string;
  workspace: Workspace;
  owner_id: string;
  created_at: string | null;
  updated_at: string | null;
  asset_count?: number;
};

export type AssetOut = {
  id: string;
  kind: "upload" | "generated" | "export" | "video";
  filename: string;
  mime: string;
  width: number;
  height: number;
  size_bytes: number;
  url: string;
  created_at: string | null;
};

export type TaskOut = {
  id: string;
  project_id: string;
  kind: "image_generate" | "cutout" | "image_edit" | "sku_variants" | "storyboard" | "video_generate";
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  prompt: string;
  width: number;
  height: number;
  count: number;
  tier: string;
  model: string;
  asset_ids: string[];
  assets: AssetOut[];
  cost_estimate: number;
  error: { code: string; message: string } | null;
  created_at: string | null;
  updated_at: string | null;
};

export type LayerOut = {
  id: string;
  asset_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  z: number;
  rotation: number;
  asset: AssetOut | null;
};

export const STATUS_TEXT: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "生成中",
  SUCCEEDED: "成功",
  FAILED: "失败",
};

export const KIND_TEXT: Record<string, string> = {
  upload: "上传",
  generated: "生成",
  export: "导出",
};

export async function downloadAsset(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await readError(res));
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

export function formatTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export type ScriptOut = {
  id: string;
  project_id: string;
  title: string;
  content: string;
  updated_at: string | null;
};

export type ShotOut = {
  id: string;
  index: number;
  scene: string;
  camera: string;
  description: string;
  dialogue: string;
  duration: number;
  character_names: string[];
};

export type CharacterOut = {
  id: string;
  name: string;
  description: string;
  ref_asset: AssetOut | null;
  created_at: string | null;
};

export const TASK_KIND_TEXT: Record<string, string> = {
  image_generate: "图像生成", cutout: "商品抠图", image_edit: "更换背景",
  sku_variants: "SKU 变色", storyboard: "生成分镜", video_generate: "生成视频",
};
export function isPending(task: TaskOut) { return task.status === "QUEUED" || task.status === "RUNNING"; }
export function errorMessage(error: unknown): string {
  if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) return "请求超时，请先查看任务记录再决定是否重新提交。";
  if (error instanceof TypeError) return "连接暂时中断，请检查网络后重试。已有素材仍然保留。";
  return error instanceof Error ? error.message : "操作未完成，请重试。";
}
