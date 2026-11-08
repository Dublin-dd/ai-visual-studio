"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import CharacterPanel from "@/components/CharacterPanel";
import StoryboardTable from "@/components/StoryboardTable";
import VideoPanel, { type ShotVideo } from "@/components/VideoPanel";
import {
  apiJson,
  formatTime,
  readError,
  STATUS_TEXT,
  type CharacterOut,
  type ProjectOut,
  type ScriptOut,
  type ShotOut,
  type TaskOut,
} from "@/lib/api";
import { totalDuration, type ShotDraft } from "@/lib/drama";

function toDraft(shots: ShotOut[]): ShotDraft[] {
  return shots.map((s) => ({
    id: s.id,
    scene: s.scene,
    camera: s.camera,
    description: s.description,
    dialogue: s.dialogue,
    duration: s.duration,
    character_names: s.character_names,
  }));
}

export default function DramaWorkspace() {
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId;

  const [project, setProject] = useState<ProjectOut | null>(null);
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [shots, setShots] = useState<ShotDraft[]>([]);
  const [characters, setCharacters] = useState<CharacterOut[]>([]);
  const [videos, setVideos] = useState<Record<string, ShotVideo>>({});
  const [task, setTask] = useState<TaskOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadShots = useCallback(async () => {
    if (!projectId) return;
    const data = await apiJson<{ items: ShotOut[] }>(`/api/drama/projects/${projectId}/shots`);
    setShots(toDraft(data.items));
  }, [projectId]);

  const loadVideos = useCallback(async () => {
    if (!projectId) return;
    const data = await apiJson<{
      items: { shot_id: string; asset: { url: string } | null; mode?: string; task_id: string }[];
    }>(`/api/drama/projects/${projectId}/videos`);
    const map: Record<string, ShotVideo> = {};
    for (const it of data.items) {
      if (it.asset?.url) map[it.shot_id] = { url: it.asset.url, mode: it.mode, taskId: it.task_id };
    }
    setVideos(map);
  }, [projectId]);

  const loadCharacters = useCallback(async () => {
    if (!projectId) return;
    const data = await apiJson<{ items: CharacterOut[] }>(
      `/api/drama/projects/${projectId}/characters`
    );
    setCharacters(data.items);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const [p, s] = await Promise.all([
          apiJson<ProjectOut>(`/api/projects/${projectId}`),
          apiJson<{ script: ScriptOut | null }>(`/api/drama/projects/${projectId}/script`),
        ]);
        if (cancelled) return;
        setProject(p);
        if (s.script) {
          setTitle(s.script.title);
          setScript(s.script.content);
        }
        await Promise.all([loadShots(), loadCharacters(), loadVideos()]);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, loadShots, loadCharacters, loadVideos]);

  // 分镜任务轮询
  useEffect(() => {
    if (!projectId || !task || (task.status !== "QUEUED" && task.status !== "RUNNING")) return;
    pollRef.current = setInterval(async () => {
      try {
        const t = await apiJson<TaskOut>(`/api/tasks/${task.id}`);
        setTask(t);
        if (t.status === "SUCCEEDED") {
          await loadShots();
          setNotice(`分镜生成完成，共 ${t.count} 个镜头`);
        } else if (t.status === "FAILED") {
          setError(t.error?.message || "分镜生成失败");
        }
      } catch {
        /* 轮询失败不打断 */
      }
    }, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [projectId, task, loadShots]);

  // 出片任务轮询：只要有视频任务在跑，每 8 秒刷新一次任务与视频列表
  const [videoTasks, setVideoTasks] = useState<TaskOut[]>([]);
  useEffect(() => {
    if (!projectId) return;
    let stop = false;
    const tick = async () => {
      try {
        const data = await apiJson<{ items: TaskOut[] }>(`/api/projects/${projectId}/tasks`);
        const vids = data.items.filter((t) => t.kind === "video_generate").slice(0, 30);
        if (!stop) setVideoTasks(vids);
        if (vids.some((t) => t.status === "SUCCEEDED" || t.status === "FAILED")) {
          await loadVideos();
        }
      } catch {
        /* 忽略轮询错误 */
      }
    };
    tick();
    const timer = setInterval(tick, 8000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, loadVideos]);

  const runningVideos = videoTasks.filter(
    (t) => t.status === "QUEUED" || t.status === "RUNNING"
  ).length;

  const generateVideo = async (shotId: string) => {
    if (!projectId) return;
    setError(null);
    try {
      await apiJson<TaskOut>(`/api/drama/projects/${projectId}/shots/${shotId}/video`, {
        method: "POST",
      });
      setNotice("出片任务已提交，约 5 分钟完成");
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    }
  };

  const batchVideo = async () => {
    if (!projectId) return;
    const est = (shots.length * 1).toFixed(0);
    if (!window.confirm(`将为 ${shots.length} 个镜头出片，预计费用约 ¥${est}，每段约 5 分钟。确定继续？`)) {
      return;
    }
    setError(null);
    try {
      const data = await apiJson<{ count: number; estimated_cost: number }>(
        `/api/drama/projects/${projectId}/videos/batch`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }
      );
      setNotice(`已提交 ${data.count} 个出片任务，预计 ¥${data.estimated_cost}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    }
  };

  const saveScript = async () => {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      await apiJson<ScriptOut>(`/api/drama/projects/${projectId}/script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, content: script }),
      });
      setNotice("剧本已保存");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const generateStoryboard = async () => {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (script.trim()) await saveScript();
      const t = await apiJson<TaskOut>(`/api/drama/projects/${projectId}/storyboard`, {
        method: "POST",
      });
      setTask(t);
      setNotice("分镜任务已提交，正在生成…");
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const saveShots = async () => {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/drama/projects/${projectId}/shots`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shots: shots.map((s, i) => ({
            index: i + 1,
            scene: s.scene,
            camera: s.camera,
            description: s.description.trim(),
            dialogue: s.dialogue.trim(),
            duration: Math.round(s.duration),
            character_names: s.character_names,
          })),
        }),
      });
      if (!res.ok) throw new Error(await readError(res));
      await loadShots();
      setNotice("分镜已保存");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const createCharacter = async (name: string, description: string) => {
    if (!projectId) return;
    try {
      await apiJson<CharacterOut>(`/api/drama/projects/${projectId}/characters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      });
      await loadCharacters();
    } catch (e) {
      setError(e instanceof Error ? e.message : "添加角色失败");
    }
  };

  const uploadRef = async (cid: string, file: File) => {
    if (!projectId) return;
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/drama/projects/${projectId}/characters/${cid}/ref`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await readError(res));
      await loadCharacters();
      setNotice("定妆照已上传");
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    }
  };

  const deleteCharacter = async (cid: string) => {
    if (!projectId) return;
    try {
      await apiJson(`/api/drama/projects/${projectId}/characters/${cid}`, { method: "DELETE" });
      await loadCharacters();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const running = task?.status === "QUEUED" || task?.status === "RUNNING";

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1400px] px-4 py-5 lg:px-8">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Link href="/drama" className="text-xs text-slate-400 hover:text-slate-200">
              ← 返回
            </Link>
            <h1 className="truncate text-lg font-semibold tracking-tight">
              {project?.name || "加载中…"}
            </h1>
          </div>
          <p className="mt-0.5 text-xs text-slate-400">
            短剧工作台 · 剧本 → 分镜 → 角色（阶段 2-3）
          </p>
        </div>
        <div className="text-xs text-slate-400">
          {task && (
            <span>
              分镜任务：{STATUS_TEXT[task.status] || task.status}
              {task.status === "SUCCEEDED" ? ` · ${task.count} 个镜头` : ""}
            </span>
          )}
        </div>
      </header>

      {(error || notice) && (
        <div
          className={`mb-3 rounded-lg border px-3 py-2 text-sm ${
            error
              ? "border-red-500/40 bg-red-500/10 text-red-200"
              : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
          }`}
        >
          {error || notice}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_320px]">
        <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <h2 className="mb-2 text-sm font-medium">1. 剧本</h2>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="本集标题，如：第一集 归途"
            className="mb-2 w-full rounded-md border border-white/10 bg-[#0e1425] px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-blue-500/60"
          />
          <textarea
            value={script}
            onChange={(e) => setScript(e.target.value)}
            rows={16}
            placeholder="粘贴剧本，例如：\n雨夜，林晚拖着行李箱回到旧公寓。她推开门，看见陈默站在窗边……"
            className="w-full resize-y rounded-md border border-white/10 bg-[#0e1425] p-2 text-xs leading-relaxed text-slate-100 outline-none focus:border-blue-500/60"
          />
          <div className="mt-2 flex gap-2">
            <button
              onClick={saveScript}
              disabled={busy || !script.trim()}
              className="flex-1 rounded-md border border-white/15 px-3 py-1.5 text-xs hover:bg-white/5"
            >
              保存剧本
            </button>
            <button
              onClick={generateStoryboard}
              disabled={busy || running || !script.trim()}
              className="flex-1 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500"
            >
              {running ? "生成中…" : "生成分镜"}
            </button>
          </div>
          <p className="mt-2 text-[10px] text-slate-500">
            共 {script.length} 字 · 生成约 5~15 秒
          </p>
        </section>

        <div>
          <StoryboardTable
            shots={shots}
            knownNames={characters.map((c) => c.name)}
            videos={videos}
            onChange={setShots}
            onSave={saveShots}
            onGenerateVideo={generateVideo}
            saving={busy}
          />
          <p className="mt-2 text-[11px] text-slate-500">
            总时长约 {totalDuration(shots)} 秒
            {runningVideos > 0 ? ` · ${runningVideos} 个出片任务进行中` : ""}
          </p>
          <div className="mt-3">
            <VideoPanel
              videos={videos}
              onBatch={batchVideo}
              batchCost={shots.length * 1}
              busy={runningVideos > 0}
            />
          </div>
        </div>

        <CharacterPanel
          characters={characters}
          onCreate={createCharacter}
          onUploadRef={uploadRef}
          onDelete={deleteCharacter}
          busy={busy}
        />
      </div>
    </main>
  );
}
