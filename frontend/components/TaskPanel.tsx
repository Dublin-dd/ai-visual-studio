"use client";

import { STATUS_TEXT, formatTime, type TaskOut } from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  QUEUED: "text-slate-300 border-white/20",
  RUNNING: "text-blue-300 border-blue-500/40",
  SUCCEEDED: "text-emerald-300 border-emerald-500/40",
  FAILED: "text-red-300 border-red-500/40",
};

export default function TaskPanel({ tasks }: { tasks: TaskOut[] }) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium">任务记录</h2>
        <span className="text-[11px] text-slate-500">最近 {tasks.length} 条</span>
      </div>
      {tasks.length === 0 ? (
        <p className="text-xs text-slate-500">还没有生成任务</p>
      ) : (
        <ul className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
          {tasks.map((task) => (
            <li key={task.id} className="rounded-lg border border-white/5 bg-black/20 p-2">
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${
                    STATUS_STYLE[task.status] || "border-white/20"
                  }`}
                >
                  {STATUS_TEXT[task.status] || task.status}
                </span>
                <span className="text-[10px] text-slate-500">
                  {formatTime(task.created_at)}
                </span>
              </div>
              <div className="mt-1 truncate text-[11px] text-slate-300" title={task.prompt}>
                {task.prompt}
              </div>
              <div className="mt-0.5 text-[10px] text-slate-500">
                {task.model || "-"} · {task.count} 张 · 约 ¥{task.cost_estimate.toFixed(2)}
                {task.error ? ` · ${task.error.message}` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
