"use client";

export type ShotVideo = { url: string; mode?: string; taskId?: string };

type Props = {
  videos: Record<string, ShotVideo>;
  onBatch: () => void;
  batchCost: number;
  busy: boolean;
};

export default function VideoPanel({ videos, onBatch, batchCost, busy }: Props) {
  const entries = Object.entries(videos);
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium">出片结果</h2>
        <span className="text-[11px] text-slate-500">已出 {entries.length} 段</span>
      </div>

      <button
        onClick={onBatch}
        disabled={busy}
        className="w-full rounded-md bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500"
      >
        批量出片（全部镜头）
      </button>
      <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
        预计约 ¥{batchCost.toFixed(2)} · 每段约 5 分钟，串行排队
        <br />
        有定妆照的角色作为首帧（i2v），没有则退回文生视频（t2v）
      </p>

      {entries.length === 0 ? (
        <p className="mt-3 text-[11px] text-slate-500">
          还没有出片。可点上面批量，或点某个分镜右侧的「出片」。
        </p>
      ) : (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {entries.map(([shotId, v]) => (
            <div key={shotId} className="overflow-hidden rounded-lg border border-white/10">
              <video src={v.url} controls className="h-20 w-full bg-black object-contain" />
              <div className="px-1 py-0.5 text-[10px] text-slate-400">
                {v.mode === "i2v" ? "首帧=定妆照" : "文生视频"}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
