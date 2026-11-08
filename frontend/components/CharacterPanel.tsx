"use client";

import { useState } from "react";
import type { CharacterOut } from "@/lib/api";

type Props = {
  characters: CharacterOut[];
  onCreate: (name: string, description: string) => Promise<void>;
  onUploadRef: (id: string, file: File) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  busy: boolean;
};

export default function CharacterPanel({
  characters,
  onCreate,
  onUploadRef,
  onDelete,
  busy,
}: Props) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium">角色库</h2>
        <span className="text-[11px] text-slate-500">{characters.length} 个角色</span>
      </div>

      <div className="mb-3 space-y-1.5">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="角色名，如：林晚"
          className="w-full rounded-md border border-white/10 bg-[#0e1425] px-2 py-1.5 text-[11px] text-slate-100 outline-none focus:border-blue-500/60"
        />
        <input
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="外貌描述，如：25岁，短发，米色风衣"
          className="w-full rounded-md border border-white/10 bg-[#0e1425] px-2 py-1.5 text-[11px] text-slate-100 outline-none focus:border-blue-500/60"
        />
        <button
          onClick={async () => {
            if (!name.trim()) return;
            await onCreate(name.trim(), desc.trim());
            setName("");
            setDesc("");
          }}
          disabled={busy || !name.trim()}
          className="w-full rounded-md border border-white/15 px-3 py-1.5 text-xs hover:bg-white/5"
        >
          添加角色
        </button>
      </div>

      {characters.length === 0 ? (
        <p className="text-xs text-slate-500">还没有角色。分镜里出现的角色建议都在这里建档。</p>
      ) : (
        <ul className="space-y-2">
          {characters.map((c) => (
            <li key={c.id} className="rounded-lg border border-white/5 bg-black/20 p-2">
              <div className="flex items-start gap-2">
                {c.ref_asset ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={c.ref_asset.url}
                    alt={`${c.name} 定妆照`}
                    className="h-12 w-12 flex-none rounded object-cover"
                  />
                ) : (
                  <div className="flex h-12 w-12 flex-none items-center justify-center rounded border border-dashed border-white/20 text-[10px] text-slate-500">
                    无照
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium text-slate-100">{c.name}</div>
                  <div className="line-clamp-2 text-[10px] text-slate-400">
                    {c.description || "未填写外貌描述"}
                  </div>
                  <div className="mt-1 flex gap-1 text-[10px]">
                    <label className="cursor-pointer rounded border border-white/15 px-1.5 py-0.5 hover:bg-white/10">
                      上传定妆照
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0];
                          if (f) await onUploadRef(c.id, f);
                          e.target.value = "";
                        }}
                      />
                    </label>
                    <button
                      onClick={() => onDelete(c.id)}
                      className="rounded border border-red-500/40 px-1.5 py-0.5 text-red-200 hover:bg-red-500/10"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
