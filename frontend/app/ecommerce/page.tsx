/* eslint-disable @next/next/no-img-element -- Project thumbnails use the local file API. */
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ProjectGallery from "@/components/ui/ProjectGallery";
import SectionHero from "@/components/ui/SectionHero";
import StudioNav from "@/components/ui/StudioNav";
import Icon from "@/components/ui/Icon";
import Dialog from "@/components/ui/Dialog";
import { apiJson, errorMessage, formatTime, type AssetOut, type ProjectOut } from "@/lib/api";

export default function ImageProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [images, setImages] = useState<Record<string, AssetOut[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const lock = useRef(false);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { const data = await apiJson<{ items: ProjectOut[] }>("/api/projects?workspace=ecommerce"); setProjects(data.items); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const controller = new AbortController();
    const loadImages = async () => {
      const entries = await Promise.allSettled(projects.filter(p => p.asset_count).map(async project => {
        const { items } = await apiJson<{ items: AssetOut[] }>(
          `/api/projects/${project.id}/assets`, { signal: controller.signal }
        );
        return [project.id, items.filter(asset => asset.mime.startsWith("image/"))] as const;
      }));
      if (!controller.signal.aborted) {
        setImages(Object.fromEntries(entries.flatMap(entry => entry.status === "fulfilled" ? [entry.value] : [])));
      }
    };
    void loadImages();
    return () => controller.abort();
  }, [projects]);
  const create = async (e: React.FormEvent) => {
    e.preventDefault(); if (lock.current) return;
    lock.current = true; setCreating(true); setError(null);
    try { const p = await apiJson<ProjectOut>("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim() || "未命名项目", workspace: "ecommerce" }) }); router.push(`/ecommerce/${p.id}`); }
    catch (err) { setError(errorMessage(err)); lock.current = false; setCreating(false); }
  };
  const filtered = projects.filter(p => p.name.toLowerCase().includes(search.trim().toLowerCase()));
  const isArtwork = (asset: AssetOut) => asset.kind === "generated" || asset.kind === "export";
  const works = filtered.filter(project => images[project.id]?.some(isArtwork));
  const featured = works[0];
  const other = filtered.filter(project => !images[project.id]?.some(isArtwork));
  const artwork = (id: string) => (images[id] ?? []).filter(isArtwork)
    .sort((a, b) => Number(b.kind === "generated") - Number(a.kind === "generated"));

  // 抠图任务同时返回白底结果与透明副本，展示时优先选完整作品。
  const isCutout = (asset: AssetOut) => /_alpha\.png$/i.test(asset.filename);
  const prints = featured ? artwork(featured.id) : [];
  const cover = prints.find(asset => !isCutout(asset)) ?? prints[0];
  return <main className="studio studio-home">
    <StudioNav active="ecommerce" />
    <div className="image-library">
      <SectionHero onCreate={() => setOpen(true)} />
      <div className="resume-heading"><h2>继续创作</h2><div className="search-input"><Icon name="search" size={16} /><input aria-label="搜索商品图项目" placeholder="搜索项目…" value={search} onChange={e => setSearch(e.target.value)} /></div></div>
      {error && !open && <div role="alert" className="studio-notice error">{error}<button className="btn" onClick={load}>重新加载</button></div>}
      {loading ? <p>正在加载项目…</p> : <>
        {featured && <Link className="project-resume" href={`/ecommerce/${featured.id}`}>
          {cover && <img className="resume-thumb" src={cover.url} alt="" />}
          <div><strong>{featured.name}</strong><small>{prints.length} 张作品 · {formatTime(featured.updated_at)}</small></div>
          <span>打开画布 <Icon name="arrow" size={15} /></span>
        </Link>}
        {works.length > 1 && <ProjectGallery key={search} title="更多图片项目" className="image-works" projects={works.slice(1)}>{project =>
            <Link href={`/ecommerce/${project.id}`} key={project.id}>
              <div className="project-cover"><img loading="lazy" src={(artwork(project.id).find(asset => !isCutout(asset)) ?? artwork(project.id)[0]).url} alt="" /></div>
              <h3>{project.name}</h3><small>{artwork(project.id).length} 张作品 · {formatTime(project.updated_at)}</small>
            </Link>
          }</ProjectGallery>}
        {other.length > 0 && <details key={search ? "search" : "all"} open={Boolean(search) || !featured}>
          <summary>其他项目 <small>{other.length}</small></summary>
          {other.map(project => <Link className="library-row" key={project.id} href={`/ecommerce/${project.id}`}>
            <strong>{project.name}</strong><small>{project.asset_count ?? 0} 个素材</small><time>{formatTime(project.updated_at)}</time><Icon name="arrow" size={15} />
          </Link>)}
        </details>}
        {!error && !filtered.length && <div className="empty-state"><h2>{search ? "没有找到匹配的项目" : "还没有商品图项目"}</h2><p>{search ? "试试其他关键词。" : "新建项目后即可上传商品图。"}</p></div>}
      </>}
    </div>
    <Dialog open={open} onClose={() => { if (!creating) { setOpen(false); setError(null); } }} title="创建电商项目"><form onSubmit={create}><p className="dialog-description">给这次创作起个名字。商品图、画布和生成结果都会保存在这里。</p><label>项目名称<input autoFocus maxLength={255} value={name} onChange={e => setName(e.target.value)} placeholder="例如：秋日护肤系列" /></label>{error && <p role="alert" className="dialog-description">{error}</p>}<div className="dialog-actions"><button type="button" className="btn" onClick={() => setOpen(false)} disabled={creating}>取消</button><button className="btn btn-primary" disabled={creating}>{creating ? "正在创建…" : "创建并开始"}<Icon name="arrow" size={16} /></button></div></form></Dialog>
  </main>;
}
