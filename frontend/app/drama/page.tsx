"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiJson, formatTime, type ProjectOut } from "@/lib/api";

export default function DramaHome() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiJson<{ items: ProjectOut[] }>("/api/projects?workspace=drama");
      setProjects(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      const p = await apiJson<ProjectOut>("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() || "未命名短剧", workspace: "drama" }),
      });
      router.push(`/drama/${p.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
      setCreating(false);
    }
  };

  return (
    <main className="mx-auto min-h-screen w-full max-w-5xl px-4 py-8 lg:px-8">
      <header className="mb-6">
        <div className="flex items-center gap-2">
          <button onClick={() => router.push("/")} className="text-xs text-slate-400 hover:text-slate-200">
            ← 返回
          </button>
          <h1 className="text-xl font-semibold tracking-tight">短剧批量工作台</h1>
        </div>
        <p className="mt-1 text-xs text-slate-400">
          剧本 → 分镜脚本 → 角色定妆 → （阶段 2-4）批量出片段
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">我的短剧项目</h2>
        <div className="flex items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="新短剧名称（可留空）"
            className="w-48 rounded-md border border-white/10 bg-[#0e1425] px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/60"
          />
          <button
            onClick={create}
            disabled={creating}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500"
          >
            {creating ? "创建中…" : "新建短剧"}
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-xs text-slate-500">加载中…</p>
      ) : projects.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/15 p-8 text-center text-xs text-slate-500">
          还没有短剧项目，点右上角「新建短剧」开始
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => router.push(`/drama/${p.id}`)}
              className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-left transition hover:border-blue-500/50 hover:bg-white/[0.06]"
            >
              <div className="truncate text-sm font-medium">{p.name}</div>
              <div className="mt-2 text-[11px] text-slate-400">
                更新于 {formatTime(p.updated_at)}
              </div>
            </button>
          ))}
        </div>
      )}
    </main>
  );
}
