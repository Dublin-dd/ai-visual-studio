"use client";

import { KIND_TEXT, formatTime, type AssetOut } from "@/lib/api";

type Props = {
  assets: AssetOut[];
  onAdd: (asset: AssetOut) => void;
  onDownload: (asset: AssetOut) => void;
};

export default function AssetPanel({ assets, onAdd, onDownload }: Props) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium">素材库</h2>
        <span className="text-[11px] text-slate-500">{assets.length} 个</span>
      </div>
      {assets.length === 0 ? (
        <p className="text-xs text-slate-500">上传或生成的素材会出现在这里</p>
      ) : (
        <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
          {assets.map((asset) => (
            <li
              key={asset.id}
              className="flex items-center gap-2 rounded-lg border border-white/5 bg-black/20 p-2"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={asset.url}
                alt="素材缩略图"
                className="h-10 w-10 flex-none rounded object-cover"
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[11px] text-slate-200">
                  {KIND_TEXT[asset.kind] || asset.kind} · {asset.width}×{asset.height}
                </div>
                <div className="text-[10px] text-slate-500">{formatTime(asset.created_at)}</div>
              </div>
              <div className="flex flex-none gap-1">
                <button
                  onClick={() => onAdd(asset)}
                  className="rounded border border-white/15 px-1.5 py-0.5 text-[10px] hover:bg-white/10"
                >
                  加入画布
                </button>
                <button
                  onClick={() => onDownload(asset)}
                  className="rounded border border-white/15 px-1.5 py-0.5 text-[10px] hover:bg-white/10"
                >
                  下载
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
