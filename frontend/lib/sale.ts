import { apiJson } from "./api";

export type SaleShot = {
  index: number;
  scene: string;
  camera: string;
  description: string;
  voiceover: string;
  duration: number;
};

export type ScriptCardPayload = {
  script_id: string;
  product_name: string;
  audience: string;
  hook: string;
  selling_points: string[];
  script_text: string;
  shots: SaleShot[];
};

export type QuoteCardPayload = {
  shot_count: number;
  unit_cost: number;
  total_cost: number;
  product_asset_id: string;
};

export type FinalCardPayload = {
  confirmed?: boolean;
  total: number;
  video_url?: string;
  asset_id?: string;
};

export type CardPayload = ScriptCardPayload | QuoteCardPayload | FinalCardPayload;

export type AgentMessageKind = "text" | "script_card" | "quote_card" | "final_card";

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  kind: AgentMessageKind;
  content: string;
  payload: CardPayload | Record<string, never>;
  created_at: string | null;
};

export type AgentReply = {
  kind: AgentMessageKind;
  content: string;
  payload: CardPayload | Record<string, never>;
  workflow: string;
};

export async function chatAgent(
  projectId: string,
  message: string,
  cardId?: string,
  finalAssetId?: string
): Promise<{ reply: AgentReply; workflow: string; message_id: string }> {
  return apiJson<{ reply: AgentReply; workflow: string; message_id: string }>("/api/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, message, card_id: cardId, final_asset_id: finalAssetId }),
    // 脚本生成需 20~60 秒（模型慢时更久），给足余量，避免中途被掐断
    signal: AbortSignal.timeout(180_000),
  });
}

export async function listAgentMessages(
  projectId: string
): Promise<{ messages: AgentMessage[]; workflow: string }> {
  return apiJson<{ messages: AgentMessage[]; workflow: string }>(
    `/api/agent/projects/${projectId}/messages`
  );
}

export type BgmItem = {
  id: string;
  filename: string;
  duration: number;
  created_at: string | null;
};

export async function listBgm(
  projectId: string
): Promise<{ items: BgmItem[]; active_id: string | null }> {
  return apiJson<{ items: BgmItem[]; active_id: string | null }>(
    `/api/agent/projects/${projectId}/bgm`
  );
}

export async function uploadBgm(projectId: string, file: File): Promise<BgmItem> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/agent/projects/${projectId}/bgm`, {
    method: "POST",
    body: form,
    signal: AbortSignal.timeout(120_000),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
    throw new Error(data?.error?.message || `上传失败（${res.status}）`);
  }
  return (await res.json()) as BgmItem;
}

export type ShotStatus = "pending" | "queued" | "running" | "failed" | "done";
export type ShotItem = {
  index: number;
  scene: string;
  camera: string;
  voiceover: string;
  description: string;
  status: ShotStatus;
  video_url: string | null;
  error: string | null;
};

export const SHOT_STATUS_TEXT: Record<ShotStatus, string> = {
  pending: "待生成",
  queued: "排队中",
  running: "生成中",
  failed: "失败",
  done: "已完成",
};

export async function listShots(
  projectId: string
): Promise<{ items: ShotItem[]; final_url: string | null }> {
  return apiJson<{ items: ShotItem[]; final_url: string | null }>(
    `/api/agent/projects/${projectId}/shots`
  );
}

export type ProductImage = {
  id: string;
  url: string;
  width: number;
  height: number;
  filename: string;
};

export async function uploadProductImage(
  projectId: string,
  file: File
): Promise<ProductImage> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("file", file);
  const res = await fetch("/api/assets/upload", {
    method: "POST",
    body: form,
    signal: AbortSignal.timeout(120_000),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
    throw new Error(data?.error?.message || `上传失败（${res.status}）`);
  }
  return (await res.json()) as ProductImage;
}

export async function listProductImages(
  projectId: string
): Promise<{ items: ProductImage[] }> {
  const data = await apiJson<{ items: Array<Record<string, unknown>> }>(
    `/api/projects/${projectId}/assets`
  );
  const items = (data.items || [])
    .filter((a) => a.kind === "upload" && String(a.mime || "").startsWith("image/"))
    .map((a) => ({
      id: String(a.id),
      url: String(a.url),
      width: Number(a.width) || 0,
      height: Number(a.height) || 0,
      filename: String(a.filename || ""),
    }));
  return { items };
}
