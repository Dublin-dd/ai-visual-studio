"use client";

import { useMemo, useState } from "react";
import { parseColors } from "@/lib/sku";
import type { AssetOut } from "@/lib/api";

type Props = {
  source: AssetOut | null;
  busy: boolean;
  onCutout: () => void;
  onScene: (scene: string) => void;
  onSku: (colors: string[]) => void;
};

export default function EditPanel({ source, busy, onCutout, onScene, onSku }: Props) {
  const [scene, setScene] = useState("浅色大理石台面，柔和侧光，简洁高级");
  const [colorText, setColorText] = useState("淡粉色,浅蓝色,薄荷绿");
  const colors = useMemo(() => parseColors(colorText), [colorText]);

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium">4. 编辑商品图</h2>
        <span className="text-[11px] text-slate-500">约 25~30 秒/次</span>
      </div>

      {source ? (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/5 bg-black/20 p-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={source.url} alt="编辑对象" className="h-10 w-10 rounded object-cover" />
          <div className="text-[11px] text-slate-300">
            当前编辑对象 · {source.width}×{source.height}
          </div>
        </div>
      ) : (
        <p className="mb-3 rounded-lg border border-dashed border-white/15 p-2 text-[11px] text-slate-500">
          先在画布上选中一张商品图，再使用下面三个动作
        </p>
      )}

      <div className="space-y-3">
        <div>
          <button
            onClick={onCutout}
            disabled={!source || busy}
            className="w-full rounded-md border border-white/15 px-3 py-1.5 text-xs hover:bg-white/5"
          >
            一键抠图（白底 + 透明底）
          </button>
        </div>

        <div className="space-y-1.5">
          <textarea
            value={scene}
            onChange={(e) => setScene(e.target.value)}
            rows={2}
            placeholder="想要什么背景？例如：浅色大理石台面，柔和侧光"
            className="w-full resize-y rounded-md border border-white/10 bg-[#0e1425] p-2 text-[11px] leading-relaxed text-slate-100 outline-none focus:border-blue-500/60"
          />
          <button
            onClick={() => onScene(scene)}
            disabled={!source || busy || !scene.trim()}
            className="w-full rounded-md border border-white/15 px-3 py-1.5 text-xs hover:bg-white/5"
          >
            换背景（保持商品不变）
          </button>
        </div>

        <div className="space-y-1.5">
          <input
            value={colorText}
            onChange={(e) => setColorText(e.target.value)}
            placeholder="颜色，用逗号分隔，最多 4 个"
            className="w-full rounded-md border border-white/10 bg-[#0e1425] px-2 py-1.5 text-[11px] text-slate-100 outline-none focus:border-blue-500/60"
          />
          <div className="flex flex-wrap gap-1">
            {colors.map((c) => (
              <span
                key={c}
                className="rounded-full border border-white/15 px-2 py-0.5 text-[10px] text-slate-300"
              >
                {c}
              </span>
            ))}
            {colors.length === 0 && (
              <span className="text-[10px] text-slate-500">还没有有效颜色</span>
            )}
          </div>
          <button
            onClick={() => onSku(colors)}
            disabled={!source || busy || colors.length === 0}
            className="w-full rounded-md border border-white/15 px-3 py-1.5 text-xs hover:bg-white/5"
          >
            多 SKU 变色（{colors.length} 张）
          </button>
        </div>
      </div>
    </section>
  );
}
