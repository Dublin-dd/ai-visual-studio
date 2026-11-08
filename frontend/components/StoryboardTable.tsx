"use client";

import { CAMERAS, SCENES, missingCharacters, type ShotDraft } from "@/lib/drama";

import type { ShotVideo } from "@/components/VideoPanel";

type Props = {
  shots: ShotDraft[];
  knownNames: string[];
  videos: Record<string, ShotVideo>;
  onChange: (shots: ShotDraft[]) => void;
  onSave: () => void;
  onGenerateVideo: (shotId: string) => void;
  saving: boolean;
};

export default function StoryboardTable({
  shots,
  knownNames,
  videos,
  onChange,
  onSave,
  onGenerateVideo,
  saving,
}: Props) {
  const missing = missingCharacters(shots, knownNames);

  const update = (i: number, patch: Partial<ShotDraft>) => {
    onChange(shots.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  };

  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= shots.length) return;
    const next = [...shots];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">分镜表</h2>
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <span>{shots.length} 个镜头</span>
          <button
            onClick={onSave}
            disabled={saving || shots.length === 0}
            className="rounded-md bg-blue-600 px-2.5 py-1 text-white hover:bg-blue-500"
          >
            {saving ? "保存中…" : "保存分镜"}
          </button>
        </div>
      </div>

      {missing.length > 0 && (
        <div className="mb-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200">
          这些角色还没建档：{missing.join("、")}（可在下方角色库添加）
        </div>
      )}

      {shots.length === 0 ? (
        <p className="text-xs text-slate-500">还没有分镜。先保存剧本，再点「生成分镜」。</p>
      ) : (
        <div className="space-y-2">
          {shots.map((s, i) => {
            const rowMissing = s.character_names.filter((n) => n && !knownNames.includes(n));
            return (
              <div
                key={s.id || i}
                className={`rounded-lg border p-2 ${
                  rowMissing.length
                    ? "border-amber-500/30 bg-amber-500/[0.04]"
                    : "border-white/5 bg-black/20"
                }`}
              >
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="rounded bg-white/10 px-1.5 py-0.5 font-mono">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <select
                    value={s.scene}
                    onChange={(e) => update(i, { scene: e.target.value })}
                    className="rounded border border-white/10 bg-[#0e1425] px-1 py-0.5 text-slate-200"
                  >
                    {SCENES.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                  <select
                    value={s.camera}
                    onChange={(e) => update(i, { camera: e.target.value })}
                    className="rounded border border-white/10 bg-[#0e1425] px-1 py-0.5 text-slate-200"
                  >
                    {CAMERAS.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    min={2}
                    max={10}
                    value={s.duration}
                    onChange={(e) => update(i, { duration: Number(e.target.value) })}
                    className="w-14 rounded border border-white/10 bg-[#0e1425] px-1 py-0.5 text-slate-200"
                  />
                  <span className="text-slate-500">秒</span>
                  <input
                    value={s.character_names.join(",")}
                    onChange={(e) =>
                      update(i, {
                        character_names: e.target.value
                          .split(/[,，、/\s]+/)
                          .map((v) => v.trim())
                          .filter(Boolean),
                      })
                    }
                    placeholder="出场角色"
                    className="w-32 rounded border border-white/10 bg-[#0e1425] px-1 py-0.5 text-slate-200"
                  />
                  <span className="ml-auto flex gap-1">
                    <button
                      onClick={() => move(i, -1)}
                      className="rounded border border-white/15 px-1.5 hover:bg-white/10"
                    >
                      ↑
                    </button>
                    <button
                      onClick={() => move(i, 1)}
                      className="rounded border border-white/15 px-1.5 hover:bg-white/10"
                    >
                      ↓
                    </button>
                    {s.id && (
                      <button
                        onClick={() => onGenerateVideo(s.id as string)}
                        disabled={Boolean(videos[s.id])}
                        className="rounded border border-emerald-500/40 px-1.5 text-emerald-200 hover:bg-emerald-500/10"
                      >
                        {videos[s.id] ? "已出片" : "出片"}
                      </button>
                    )}
                    <button
                      onClick={() => onChange(shots.filter((_, idx) => idx !== i))}
                      className="rounded border border-red-500/40 px-1.5 text-red-200 hover:bg-red-500/10"
                    >
                      删
                    </button>
                  </span>
                </div>
                <textarea
                  value={s.description}
                  onChange={(e) => update(i, { description: e.target.value })}
                  rows={2}
                  placeholder="画面描述（能直接拍出来的内容）"
                  className="mt-1 w-full resize-y rounded border border-white/10 bg-[#0e1425] p-1.5 text-[11px] text-slate-100 outline-none focus:border-blue-500/60"
                />
                <input
                  value={s.dialogue}
                  onChange={(e) => update(i, { dialogue: e.target.value })}
                  placeholder="台词（可空）"
                  className="mt-1 w-full rounded border border-white/10 bg-[#0e1425] px-1.5 py-1 text-[11px] text-slate-100 outline-none focus:border-blue-500/60"
                />
                {s.id && videos[s.id] && (
                  <video
                    src={videos[s.id].url}
                    controls
                    className="mt-1 h-24 w-full rounded bg-black object-contain"
                  />
                )}
              </div>
            );
          })}
          <button
            onClick={() => onChange([...shots, { ...shots[shots.length - 1], id: undefined, description: "", dialogue: "" }])}
            className="w-full rounded-md border border-dashed border-white/20 py-1.5 text-[11px] text-slate-300 hover:bg-white/5"
          >
            ＋ 添加镜头
          </button>
        </div>
      )}
    </section>
  );
}
