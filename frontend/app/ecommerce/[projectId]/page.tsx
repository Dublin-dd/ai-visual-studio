/* eslint-disable @next/next/no-img-element -- Local project media is served by the same-origin file API. */
"use client";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ThemeToggle from "@/components/ui/ThemeToggle";
import Canvas from "@/components/Canvas";
import Dialog from "@/components/ui/Dialog";
import Icon, { type IconName } from "@/components/ui/Icon";
import { Brand } from "@/components/ui/StudioNav";
import { apiJson, downloadAsset, errorMessage, formatTime, isPending, KIND_TEXT, STATUS_TEXT, TASK_KIND_TEXT, type AssetOut, type LayerOut, type ProjectOut, type TaskOut } from "@/lib/api";
import { BOARD_HEIGHT, BOARD_WIDTH, canvasReducer, defaultPlacement, fromServerLayers, initialCanvas, type Layer } from "@/lib/canvas";
import { parseColors } from "@/lib/sku";
import { useCanvasSave } from "@/hooks/useCanvasSave";

type Loaded = { project: ProjectOut; layers: Layer[]; assets: AssetOut[]; tasks: TaskOut[] };
type Mode = "generate" | "cutout" | "scene" | "sku";
type Submission = { label: string; payload: Record<string, unknown>; count: number; description: string; source?: AssetOut };
const MODES: { value: Mode; label: string; icon: IconName }[] = [
  { value: "generate", label: "生成", icon: "sparkle" }, { value: "cutout", label: "抠图", icon: "scissors" },
  { value: "scene", label: "背景", icon: "image" }, { value: "sku", label: "SKU", icon: "palette" },
];

export default function WorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let stopped = false; setLoaded(null); setError(null);
    const controller = new AbortController();
    (async () => {
      try {
        const [project, layers, assets, tasks] = await Promise.all([
          apiJson<ProjectOut>(`/api/projects/${projectId}`, { signal: controller.signal }),
          apiJson<{ items: LayerOut[] }>(`/api/projects/${projectId}/layers`, { signal: controller.signal }),
          apiJson<{ items: AssetOut[] }>(`/api/projects/${projectId}/assets`, { signal: controller.signal }),
          apiJson<{ items: TaskOut[] }>(`/api/projects/${projectId}/tasks`, { signal: controller.signal }),
        ]);
        if (project.workspace !== "ecommerce") throw Error("这是一个短剧项目，请从短剧工作台打开。");
        if (!stopped) setLoaded({ project, layers: fromServerLayers(layers.items), assets: assets.items, tasks: tasks.items });
      } catch (e) { if (!stopped) setError(errorMessage(e)); }
    })();
    return () => { stopped = true; controller.abort(); };
  }, [projectId, retry]);
  if (!loaded) return <main className="studio editor-loading">{error ? <><Icon name="warning" size={28} /><p role="alert">{error}</p><div><a className="btn" href="/ecommerce">返回项目</a> <button className="btn btn-primary" onClick={() => setRetry(n => n + 1)}>重新加载</button></div></> : <><Icon name="refresh" className="spinner" size={26} /><p className="muted">正在打开你的工作空间…</p></>}</main>;
  return <Workspace key={projectId} initial={loaded} />;
}

function Workspace({ initial }: { initial: Loaded }) {
  const router = useRouter();
  const projectId = initial.project.id;
  const [colorDraft, setColorDraft] = useState<string | null>(null);
  const [savingColor, setSavingColor] = useState(false);
  const [colorError, setColorError] = useState("");
  const [project, setProject] = useState(initial.project);
  const [state, dispatch] = useReducer(canvasReducer, { ...initialCanvas, layers: initial.layers });
  const [assets, setAssets] = useState(initial.assets);
  const [tasks, setTasks] = useState(initial.tasks);
  const [mode, setMode] = useState<Mode>("generate");
  const [library, setLibrary] = useState<"assets" | "layers">("assets");
  const [filter, setFilter] = useState("all");
  const [prompt, setPrompt] = useState("");
  const [scene, setScene] = useState("浅色大理石台面，柔和的自然侧光，简洁干净的背景");
  const [colorText, setColorText] = useState("淡粉色，浅蓝色，薄荷绿");
  const [tier, setTier] = useState("standard");
  const [size, setSize] = useState(1024);
  const [count, setCount] = useState(1);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [disconnected, setDisconnected] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [scale, setScale] = useState(.6);
  const [preview, setPreview] = useState<AssetOut | null>(null);
  const [showTasks, setShowTasks] = useState(false);
  const [confirm, setConfirm] = useState<Submission | null>(null);
  const [rename, setRename] = useState(false);
  const [name, setName] = useState(initial.project.name);
  const [renaming, setRenaming] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const submitLock = useRef(false);
  const exportLock = useRef(false);
  const ownTasks = useRef(new Set<string>());
  const addedTasks = useRef(new Set<string>());
  const alive = useRef(true);
  const { status: saveStatus, flush } = useCanvasSave(projectId, state.layers);
  const selected = state.layers.find(l => l.id === state.selectedId);
  const source = selected ? assets.find(a => a.id === selected.assetId) : undefined;
  const pending = tasks.filter(isPending);
  const colors = parseColors(colorText);
  const visibleAssets = assets.filter(a => a.mime.startsWith("image/") && (filter === "all" || a.kind === filter));
  const lastTask = tasks[0];
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const addAsset = useCallback((asset: AssetOut) => {
    dispatch({ type: "add", id: crypto.randomUUID(), layer: { assetId: asset.id, url: asset.url, rotation: 0, ...defaultPlacement(asset.width, asset.height) } });
  }, []);
  const refresh = useCallback(async () => {
    const [t, a] = await Promise.all([
      apiJson<{ items: TaskOut[] }>(`/api/projects/${projectId}/tasks`),
      apiJson<{ items: AssetOut[] }>(`/api/projects/${projectId}/assets`),
    ]);
    if (alive.current) { setTasks(t.items); setAssets(a.items); setDisconnected(false); }
    return t.items;
  }, [projectId]);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const tick = async () => {
      if (document.hidden) { timer = setTimeout(tick, 10000); return; }
      try { await refresh(); failures = 0; }
      catch { if (!stopped) { failures += 1; setDisconnected(true); } }
      if (!stopped) timer = setTimeout(tick, Math.min(30000, 3500 * 2 ** failures));
    };
    if (pending.length || disconnected) timer = setTimeout(tick, 1500);
    const onOnline = () => { void refresh().catch(() => setDisconnected(true)); };
    window.addEventListener("online", onOnline);
    return () => { stopped = true; clearTimeout(timer); window.removeEventListener("online", onOnline); };
  }, [pending.length, disconnected, refresh]);
  useEffect(() => {
    for (const task of tasks) {
      if (task.status !== "SUCCEEDED" || !ownTasks.current.has(task.id) || addedTasks.current.has(task.id)) continue;
      addedTasks.current.add(task.id);
      const images = (task.assets ?? []).filter(a => a.mime.startsWith("image/"));
      images.forEach(addAsset);
      if (images.length) setNotice(`创作完成，${images.length} 张图片已加入画布与素材库。`);
    }
  }, [tasks, addAsset]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (document.querySelector("dialog[open]")) return;
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable=true]")) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); dispatch({ type: e.shiftKey ? "redo" : "undo" }); }
      if ((e.key === "Delete" || e.key === "Backspace") && state.selectedId) { e.preventDefault(); dispatch({ type: "remove", id: state.selectedId }); }
    };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, [state.selectedId]);
  const clearFeedback = () => { setError(null); setNotice(null); };
  const upload = async (file: File) => {
    if (submitLock.current) return;
    if (file.size > 20 * 1024 * 1024) { setError("文件超过 20MB，请换一张较小的图片。"); return; }
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { setError("请选择 JPG、PNG 或 WebP 图片。"); return; }
    submitLock.current = true; setBusy(true); clearFeedback();
    try {
      const body = new FormData(); body.append("project_id", projectId); body.append("file", file);
      const asset = await apiJson<AssetOut>("/api/assets/upload", { method: "POST", body });
      addAsset(asset); setAssets(prev => [asset, ...prev]); setNotice("商品图已上传。选中它，开始抠图、换背景或制作 SKU。");
    } catch (e) { setError(errorMessage(e)); }
    finally { submitLock.current = false; setBusy(false); if (uploadRef.current) uploadRef.current.value = ""; }
  };
  const prepare = () => {
    clearFeedback();
    if (mode !== "generate" && !source) { setError("请先选中画布上的一张商品图。"); return; }
    if (mode === "generate") {
      if (!prompt.trim()) { setError("先描述一下你想要的画面。"); return; }
      setConfirm({ label: "生成图像", count, description: prompt.trim(), payload: { kind: "image_generate", prompt: prompt.trim(), width: size, height: size, count, tier } });
    } else if (mode === "cutout") setConfirm({ label: "商品抠图", count: 1, source, description: "生成白底商品图，并尝试输出透明底 PNG。白色商品及复杂边缘建议核对后使用。", payload: { kind: "cutout", source_asset_id: source!.id } });
    else if (mode === "scene") {
      if (!scene.trim()) return;
      setConfirm({ label: "更换背景", count: 1, source, description: scene.trim(), payload: { kind: "image_edit", source_asset_id: source!.id, prompt: scene.trim() } });
    } else setConfirm({ label: "生成 SKU", count: colors.length, source, description: `商品颜色：${colors.join("、")}`, payload: { kind: "sku_variants", source_asset_id: source!.id, colors, seed: Math.floor(Math.random() * 1000000) } });
  };
  const submit = async () => {
    if (!confirm || submitLock.current) return;
    submitLock.current = true; setBusy(true); clearFeedback();
    try {
      const task = await apiJson<TaskOut>("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId, ...confirm.payload }) });
      ownTasks.current.add(task.id); setTasks(prev => [task, ...prev]); setConfirm(null); setNotice("任务已加入队列，可以继续编辑画布。结果会保存在素材库。");
    } catch (e) { setConfirm(null); setError(errorMessage(e)); void refresh().catch(() => setDisconnected(true)); }
    finally { submitLock.current = false; setBusy(false); }
  };
  const download = async (asset: AssetOut) => {
    try { await downloadAsset(asset.url, asset.filename || `素材-${asset.id.slice(0,8)}.png`); }
    catch (e) { setError(errorMessage(e)); }
  };
  const exportCanvas = async () => {
    if (exportLock.current || !state.layers.length) return;
    exportLock.current = true; setExporting(true); clearFeedback();
    try {
      await flush();
      const result = await apiJson<{ asset: AssetOut }>(`/api/projects/${projectId}/export`, { method: "POST" });
      setAssets(prev => [result.asset, ...prev]);
      await downloadAsset(result.asset.url, `${project.name}.png`);
      setNotice("已导出最新画布，PNG 同时保存在素材库。");
    } catch (e) { setError(errorMessage(e)); }
    finally { exportLock.current = false; setExporting(false); }
  };
  const background = project.background_color ?? "#FFFFFF";
  const applyBackground = async () => {
    if (colorDraft === null || savingColor) return;
    setSavingColor(true);
    setColorError("");
    try {
      const updated = await apiJson<ProjectOut>(`/api/projects/${projectId}/background`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ color: colorDraft }),
      });
      setProject(updated);
      setColorDraft(null);
    } catch (e) {
      setColorError(errorMessage(e));
    } finally {
      setSavingColor(false);
    }
  };
  const leave = async (destination = "/ecommerce") => { try { await flush(); router.push(destination); } catch { setError("画布尚未保存成功，请重试保存后再离开。"); } };
  const saveName = async (e: React.FormEvent) => {
    e.preventDefault(); if (!name.trim() || renaming) return; setRenaming(true);
    try { const p = await apiJson<ProjectOut>(`/api/projects/${projectId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim() }) }); setProject(p); setRename(false); }
    catch (err) { setError(errorMessage(err)); }
    finally { setRenaming(false); }
  };
  const saveText = { saved: "所有更改已保存", pending: "有更改待保存", saving: "正在保存…", error: "保存失败，点击重试" }[saveStatus];
  return <main className="studio editor">
    <Dialog open={colorDraft !== null} onClose={() => { if (!savingColor) setColorDraft(null); }} title="画板背景">
      <p className="dialog-description">底色会随项目保存，并用于导出 PNG。</p>
      <div className="board-color-options">
        {[["纯白", "#FFFFFF"], ["暖灰", "#EAE6DF"]].map(([label, color]) =>
          <button key={color} className="btn" disabled={savingColor} aria-pressed={colorDraft === color} onClick={() => setColorDraft(color)}>
            <i style={{ backgroundColor: color }} />{label}
          </button>)}
        <label>自定义<input type="color" disabled={savingColor} value={colorDraft ?? background} onChange={e => setColorDraft(e.target.value.toUpperCase())} /></label>
      </div>
      {colorError && <p role="alert">{colorError}</p>}
      <div className="dialog-actions"><button className="btn" disabled={savingColor} onClick={() => setColorDraft(null)}>取消</button>
        <button className="btn btn-primary" disabled={savingColor} onClick={applyBackground}>{savingColor ? "保存中…" : "应用"}</button></div>
    </Dialog>
    <header className="editor-top"><div className="editor-title"><button className="icon-btn" aria-label="保存并返回项目" title="保存并返回项目" onClick={() => void leave()}><Icon name="back" /></button><Brand onNavigate={() => void leave("/")} /><span className="header-divider" /><button className="project-name-btn" title="修改项目名称" onClick={() => { setName(project.name); setRename(true); }}><span><strong>{project.name}</strong><small>电商素材 / 创作工作台</small></span><Icon name="down" size={13} /></button></div><div className="editor-actions"><ThemeToggle /><button className={`save-status ${saveStatus === "error" ? "failed" : ""}`} onClick={() => void flush().catch(e => setError(errorMessage(e)))} title={saveText}><Icon name={saveStatus === "saved" ? "check" : saveStatus === "error" ? "warning" : "refresh"} size={13} className={saveStatus === "saving" ? "spinner" : ""} />{saveText}</button><button className="btn btn-primary" disabled={exporting || !state.layers.length} onClick={() => void exportCanvas()}><Icon name="download" size={15} />{exporting ? "导出中…" : "导出 PNG"}</button></div></header>
    {(error || notice) && <div className={`studio-notice ${error ? "error" : ""}`} role={error ? "alert" : "status"}><Icon name={error ? "warning" : "check"} size={16} /><span>{error || notice}</span><button className="icon-btn" aria-label="关闭提示" onClick={clearFeedback}><Icon name="close" size={15} /></button></div>}
    {disconnected && <div className="studio-notice warning" role="status"><Icon name="refresh" size={15} /><span>暂时无法更新任务状态，正在重新连接。服务端任务可能仍在进行。</span></div>}
    <div className="editor-body">
      <aside className="tool-panel" aria-label="创作工具"><div className="panel-heading"><h2>创作工具</h2><Icon name="sliders" size={15} /></div><div className="tool-modes" role="group" aria-label="选择创作方式">{MODES.map(m => <button key={m.value} className={mode === m.value ? "active" : ""} aria-pressed={mode === m.value} onClick={() => setMode(m.value)}><Icon name={m.icon} size={17} />{m.label}</button>)}</div>
        <div className="tool-content"><h3>{{ generate: "让想象，有迹可循", cutout: "让商品成为主角", scene: "为商品换个场景", sku: "一款商品，多种可能" }[mode]}</h3><p className="tool-description">{{ generate: "描述画面，生成独立图片。保留商品外观请使用「背景」。", cutout: "从现有商品图生成白底与透明底素材。", scene: "选中商品，描述它将出现的新环境。", sku: "以同一张商品图为参考，生成不同颜色的变体。" }[mode]}</p>
        {mode !== "generate" && (source ? <div className="source-preview"><img src={source.url} alt="当前商品参考图" /><span>已选中商品图<small>{source.width} × {source.height}</small></span></div> : <div className="source-empty">先选中画布上的商品图。<br />还没有素材？可以先上传一张。</div>)}
        {mode === "generate" && <><div className="tool-field"><label className="field-heading" htmlFor="prompt"><span>画面描述</span><span>{prompt.length}/2000</span></label><textarea id="prompt" className="prompt-field" rows={5} maxLength={2000} placeholder="例如：一瓶护肤精华放在浅色石台上，晨光穿过纱帘，温暖而安静…" value={prompt} onChange={e => setPrompt(e.target.value)} /></div><div className="tool-field two-fields"><label>生成档位<select value={tier} onChange={e => setTier(e.target.value)}><option value="standard">标准</option><option value="draft">草稿</option><option value="hq">精修</option></select></label><label>图片尺寸<select value={size} onChange={e => setSize(Number(e.target.value))}>{[1024,768,512].map(s => <option key={s} value={s}>{s}²</option>)}</select></label></div><div className="tool-field"><div className="field-heading"><span>生成数量</span><span>最多 4 张</span></div><div className="count-options" role="group" aria-label="生成数量">{[1,2,3,4].map(n => <button key={n} aria-pressed={count === n} className={count === n ? "active" : ""} onClick={() => setCount(n)}>{n} 张</button>)}</div></div></>}
        {mode === "scene" && <div className="tool-field"><label className="field-heading" htmlFor="scene">背景描述</label><textarea id="scene" rows={5} maxLength={2000} value={scene} onChange={e => setScene(e.target.value)} /></div>}
        {mode === "sku" && <div className="tool-field"><label htmlFor="colors">商品颜色<input id="colors" value={colorText} onChange={e => setColorText(e.target.value)} placeholder="用逗号分隔，最多 4 个颜色" maxLength={200} /></label><div className="color-tags">{colors.map(c => <span key={c}>{c}</span>)}</div><p className="tool-footnote">每个颜色生成一张，单次最多 4 张。</p></div>}
        {mode === "cutout" && <p className="tool-description">先由 AI 生成白底，再转换为透明底。白色商品、玻璃和细小边缘可能需要进一步检查。</p>}
        <button className="btn btn-primary btn-full" disabled={busy || (mode === "generate" ? !prompt.trim() : !source || (mode === "scene" && !scene.trim()) || (mode === "sku" && !colors.length))} onClick={prepare}><Icon name="sparkle" size={16} />{busy ? "正在提交…" : { generate: "生成图像", cutout: "开始抠图", scene: "生成新背景", sku: `生成 ${colors.length} 个 SKU` }[mode]}</button><p className="tool-footnote">提交前将确认预计费用。生成时可继续编辑，结果自动保存。</p><div className="tool-separator" /><button className="upload-zone" disabled={busy} onClick={() => uploadRef.current?.click()}><Icon name="upload" size={16} />上传商品图</button><p className="tool-footnote" style={{ textAlign: "center" }}>JPG / PNG / WebP · 单张不超过 20MB</p><input ref={uploadRef} type="file" accept="image/png,image/jpeg,image/webp" style={{ display: "none" }} aria-label="上传商品图片文件" onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f); }} />
        </div>
      </aside>
      <section className="canvas-column" aria-label="画布编辑区"><div className="canvas-stage"><div className="canvas-topbar"><div className="canvas-tools"><span className="icon-btn active" title="选中并拖动"><Icon name="cursor" size={16} /></span><span className="header-divider" /><button className="icon-btn" title="撤销 ⌘Z" aria-label="撤销" disabled={!state.past.length} onClick={() => dispatch({ type: "undo" })}><Icon name="undo" size={16} /></button><button className="icon-btn" title="重做 ⇧⌘Z" aria-label="重做" disabled={!state.future.length} onClick={() => dispatch({ type: "redo" })}><Icon name="redo" size={16} /></button></div><button className="board-color-trigger" aria-label="画板背景" title="画板背景" onClick={() => { setColorDraft(background); setColorError(""); }}><i style={{ backgroundColor: background }} />画板 01</button><span> <span style={{ color: "#666", margin: "0 7px" }}>/</span> {BOARD_WIDTH} × {BOARD_HEIGHT}</span><button className="icon-btn" title="适应画布" aria-label="适应画布" onClick={() => setZoom(1)}><Icon name="expand" size={15} /></button></div>
        <div className="canvas-scroll"><Canvas background={colorDraft ?? background} layers={state.layers} selectedId={state.selectedId} onSelect={id => dispatch({ type: "select", id })} onMove={(id,x,y) => dispatch({ type: "move", id,x,y })} onResize={(id,width,height) => dispatch({ type: "resize", id,width,height })} zoom={zoom} onScale={setScale} /></div>
        <div className="canvas-bottom"><span>{state.layers.length} 个图层 <span className="canvas-hint">· 拖动排列，方向键微调</span></span><div className="zoom-control"><button className="icon-btn" aria-label="缩小画布" disabled={zoom <= .5} onClick={() => setZoom(z => Math.max(.5,z-.25))}><Icon name="minus" size={14} /></button><span>{Math.round(scale * 100)}%</span><button className="icon-btn" aria-label="放大画布" disabled={zoom >= 2.5} onClick={() => setZoom(z => Math.min(2.5,z+.25))}><Icon name="plus" size={14} /></button></div></div>
      </div><button className="task-summary" onClick={() => setShowTasks(true)}><Icon name={pending.length ? "refresh" : "clock"} size={16} className={pending.length ? "spinner" : ""} /><span className="summary-copy">{pending.length ? `${pending.length} 个任务进行中` : lastTask ? "最近的创作记录" : "准备好，开始一次新的创作"}<br /><small>{pending.length ? "结果自动存入素材库，无需停留等待" : lastTask ? `${TASK_KIND_TEXT[lastTask.kind]} · ${STATUS_TEXT[lastTask.status] ?? "状态待确认"}` : "生成任务和历史结果都可以在这里查看"}</small></span><span className="micro muted">任务记录</span><Icon name="chevron" size={14} /></button></section>
      <aside className="library-panel" aria-label="素材与图层"><div className="library-tabs" role="group" aria-label="右侧面板"><button className={library === "assets" ? "active" : ""} aria-pressed={library === "assets"} onClick={() => setLibrary("assets")}><Icon name="image" size={15} />素材库</button><button className={library === "layers" ? "active" : ""} aria-pressed={library === "layers"} onClick={() => setLibrary("layers")}><Icon name="layers" size={15} />图层<span className="count-pill">{state.layers.length}</span></button></div><div className="library-content">
      {library === "assets" ? <><div className="library-toolbar"><span>{visibleAssets.length} 个素材</span><select aria-label="筛选素材类型" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">全部素材</option><option value="upload">已上传</option><option value="generated">AI 生成</option><option value="export">已导出</option></select></div>{visibleAssets.length ? <div className="asset-grid">{visibleAssets.map((a,i) => <div className="asset-tile" key={a.id}><div className="asset-thumb"><button onClick={() => setPreview(a)} aria-label={`预览素材 ${i+1}`}><img src={a.url} alt={`${KIND_TEXT[a.kind] || "素材"} ${i+1}`} loading="lazy" /></button><button className="asset-add" title="加入画布" aria-label={`将素材 ${i+1} 加入画布`} onClick={() => addAsset(a)}><Icon name="plus" size={14} /></button></div><div className="asset-meta"><span>{KIND_TEXT[a.kind]}</span><span>{a.width} × {a.height}</span></div></div>)}</div> : <div className="empty-state"><Icon name="image" size={28} /><h3>还没有这类素材</h3><p>上传与生成的图片会保存在这里。</p></div>}<p className="tool-footnote" style={{ marginTop: 20 }}>点击图片放大预览，点击 ＋ 加入画布。</p></> : <><div className="library-toolbar"><span>按叠放顺序排列</span><span>上层在前</span></div><div className="layer-list">{[...state.layers].sort((a,b) => b.z-a.z).map(l => <button className={`layer-row ${selected?.id === l.id ? "active" : ""}`} key={l.id} onClick={() => dispatch({ type: "select", id: l.id })}><img src={l.url} alt="" /><span>图层 {state.layers.indexOf(l)+1}</span><small>{Math.round(l.width)}×{Math.round(l.height)}</small></button>)}</div>{!state.layers.length && <div className="empty-state"><Icon name="layers" size={25} /><p>加入素材后，在这里管理图层。</p></div>}</>}
      {selected && <div className="layer-properties"><h3>当前选中 · 图层 {state.layers.indexOf(selected)+1}</h3><div className="two-fields"><NumberField key={`${selected.id}-x-${selected.x}`} label="X 位置" value={selected.x} onCommit={x => dispatch({ type: "move", id: selected.id, x, y: selected.y })} /><NumberField key={`${selected.id}-y-${selected.y}`} label="Y 位置" value={selected.y} onCommit={y => dispatch({ type: "move", id: selected.id, x: selected.x, y })} /></div><div className="two-fields"><NumberField key={`${selected.id}-w-${selected.width}`} label="宽度" value={selected.width} min={40} max={8000} onCommit={width => dispatch({ type: "resize", id: selected.id, width, height: selected.height })} /><NumberField key={`${selected.id}-h-${selected.height}`} label="高度" value={selected.height} min={40} max={8000} onCommit={height => dispatch({ type: "resize", id: selected.id, width: selected.width, height })} /></div><div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}><button className="btn" onClick={() => dispatch({ type: "front", id: selected.id })}><Icon name="up" size={13} />置顶</button>{source && <button className="btn" onClick={() => void download(source)}><Icon name="download" size={13} />下载</button>}<button className="btn" title="从画布移除，原素材仍然保留" onClick={() => dispatch({ type: "remove", id: selected.id })}><Icon name="trash" size={13} />移除</button></div><p className="tool-footnote">移除仅影响画布，可撤销恢复。</p></div>}
      </div></aside>
    </div>
    <Dialog open={Boolean(confirm)} onClose={() => { if (!busy) setConfirm(null); }} title={`确认${confirm?.label ?? "生成"}`}><p className="dialog-description">确认后开始调用模型。你可以继续编辑，生成结果会自动保存。</p>{confirm && <><div className="confirm-details"><p><span>本次操作</span><strong>{confirm.label}</strong></p><p><span>生成数量</span><strong>{confirm.count} 次{mode === "cutout" ? "（白底＋透明底）" : ""}</strong></p><p><span>预计费用</span><strong>约 ¥{(confirm.count*.3).toFixed(2)}</strong></p></div>{confirm.source && <div className="source-preview" style={{ marginTop: 16 }}><img src={confirm.source.url} alt="本次生成使用的参考图" /><span>本次使用的商品参考图</span></div>}<p className="confirm-prompt">{confirm.description}</p><p className="tool-footnote">费用为估算，以服务商实际账单为准。生成时间会随排队情况变化。</p></>}<div className="dialog-actions"><button className="btn" disabled={busy} onClick={() => setConfirm(null)}>返回修改</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{busy ? "提交中…" : "确认并生成"}<Icon name="sparkle" size={15} /></button></div></Dialog>
    <Dialog open={Boolean(preview)} onClose={() => setPreview(null)} title="素材预览" wide>{preview && <><img className="preview-image" src={preview.url} alt="素材完整预览" /><div className="dialog-actions"><span className="micro muted" style={{ marginRight: "auto" }}>{preview.width} × {preview.height} · {KIND_TEXT[preview.kind]}</span><button className="btn" onClick={() => void download(preview)}><Icon name="download" size={15} />下载原图</button><button className="btn btn-primary" onClick={() => { addAsset(preview); setPreview(null); }}><Icon name="plus" size={15} />加入画布</button></div></>}</Dialog>
    <Dialog open={showTasks} onClose={() => setShowTasks(false)} title={`任务记录 · ${tasks.length}`} wide>{tasks.length ? <div className="task-list">{tasks.map(t => <article className="task-card" key={t.id}><div className="task-card-head"><span>{TASK_KIND_TEXT[t.kind] ?? "创作任务"}</span><span className={`status-tag ${t.status === "FAILED" ? "failed" : ""}`}><Icon name={isPending(t) ? "clock" : t.status === "SUCCEEDED" ? "check" : "warning"} size={12} />{STATUS_TEXT[t.status] ?? "状态待确认"}</span></div><p>{t.prompt || TASK_KIND_TEXT[t.kind]}</p>{t.error && <p role="status">{t.error.message}</p>}<footer><span>{formatTime(t.created_at)} · {t.count} 次</span><span>估算 ¥{(t.cost_estimate ?? 0).toFixed(2)}</span></footer><details className="tool-footnote"><summary>生成详情</summary><p>模型：{t.model || "等待分配"}<br />任务编号：{t.id}</p></details></article>)}</div> : <div className="empty-state"><Icon name="clock" size={28} /><h3>还没有生成任务</h3><p>提交一次创作后，可以在这里跟进结果。</p></div>}</Dialog>
    <Dialog open={rename} onClose={() => setRename(false)} title="项目名称"><form onSubmit={saveName}><label>名称<input autoFocus value={name} maxLength={255} onChange={e => setName(e.target.value)} /></label>{error && <p role="alert">{error}</p>}<div className="dialog-actions"><button type="button" className="btn" onClick={() => setRename(false)}>取消</button><button className="btn btn-primary" disabled={renaming || !name.trim()}>{renaming ? "保存中…" : "保存名称"}</button></div></form></Dialog>
  </main>;
}

function NumberField({ label, value, onCommit, min = -8000, max = 8000 }: { label: string; value: number; onCommit: (n: number) => void; min?: number; max?: number }) {
  const [draft, setDraft] = useState(String(Math.round(value)));
  const commit = () => { const n = Number(draft); if (draft.trim() && Number.isFinite(n)) { const safe = Math.min(max,Math.max(min,Math.round(n))); if (safe !== value) onCommit(safe); setDraft(String(safe)); } else setDraft(String(Math.round(value))); };
  return <label>{label}<input type="number" min={min} max={max} value={draft} onChange={e => setDraft(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === "Enter") { commit(); e.currentTarget.blur(); } }} /></label>;
}
