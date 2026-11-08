"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Dialog from "@/components/ui/Dialog";
import ProjectGallery from "@/components/ui/ProjectGallery";
import VideoProjectLink from "@/components/ui/VideoProjectLink";
import SectionHero from "@/components/ui/SectionHero";
import StudioNav from "@/components/ui/StudioNav";
import Icon from "@/components/ui/Icon";
import Image from "next/image";
import { apiJson, errorMessage, formatTime, type ProjectOut, type AssetOut } from "@/lib/api";

type ProjectMedia = { image?: string; clip?: string; images: AssetOut[] };

export default function SaleListPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [media, setMedia] = useState<Record<string, ProjectMedia>>({});
  const [coverProject, setCoverProject] = useState<ProjectOut | null>(null);
  const [savingCover, setSavingCover] = useState(false);
  const [coverError, setCoverError] = useState("");
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    for (const project of projects.filter(p => p.asset_count)) {
      apiJson<{items: AssetOut[]}>(`/api/projects/${project.id}/assets`, {signal: controller.signal})
        .then(({items}) => {
          const images = items.filter(a => a.mime.startsWith("image/"));
          const candidates = images.filter(a => !/_alpha\.png$/i.test(a.filename));
          const asset = [...candidates].sort((a, b) =>
            Math.min(b.width, b.height) - Math.min(a.width, a.height)
          )[0] ?? images[0];
          const clip = items.find(a => a.mime.startsWith("video/"));
          if (!controller.signal.aborted) {
            setMedia(prev => ({ ...prev, [project.id]: { image: asset?.url, clip: clip?.url, images } }));
          }
        }).catch(() => {});
    }
    return () => controller.abort();
  }, [projects]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiJson<{ items: ProjectOut[] }>("/api/projects?workspace=ecommerce");
      setProjects(data.items);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    if (creating || !name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const p = await apiJson<ProjectOut>("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), workspace: "ecommerce" }),
      });
      router.push(`/sale/${p.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setCreating(false);
    }
  };

  const withVideo = projects.filter(p => media[p.id]?.clip);
  const featured = withVideo[0] ?? projects.find(p => p.asset_count);
  const gallery = withVideo.filter(p => p.id !== featured?.id);
  const remaining = projects.filter(p => p.id !== featured?.id && !media[p.id]?.clip);
  const featuredCover = featured?.cover_asset_id
    ? `/api/files/${featured.cover_asset_id}`
    : featured && media[featured.id]?.image;

  async function saveCover(assetId: string | null) {
    if (!coverProject || savingCover) return;
    setSavingCover(true);
    try {
      const updated = await apiJson<ProjectOut>(`/api/projects/${coverProject.id}/cover`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_id: assetId }),
      });
      setProjects(previous => previous.map(p => p.id === updated.id ? {...p, cover_asset_id: updated.cover_asset_id} : p));
      setCoverProject(null);
    } catch (e) { setCoverError(errorMessage(e)); }
    finally { setSavingCover(false); }
  }

  return (
    <main className="studio studio-home">
      <StudioNav active="sale" />
      <div className="video-library">
        <SectionHero video onCreate={() => setNaming(true)} />
        {error && <p role="alert">{error} <button className="btn" onClick={load}>重试</button></p>}
        {loading ? <p>正在加载项目…</p> : <>
          {featured && <section className="resume-section"><h2>继续创作</h2>
            <VideoProjectLink key={featured.id} href={`/sale/${featured.id}`} className="project-resume">
              <div className="resume-thumb">
                {featuredCover && <Image unoptimized src={featuredCover} fill sizes="64px" alt="" />}
                {media[featured.id]?.clip && <video muted playsInline loop preload="metadata" aria-hidden="true" src={media[featured.id].clip} />}
              </div>
              <div><strong>{featured.name}</strong><small>{featured.asset_count} 个素材 · {formatTime(featured.updated_at)}</small></div>
              <span>继续制作 <Icon name="arrow" size={15} /></span>
            </VideoProjectLink>
          </section>}
          {featured && Boolean(media[featured.id]?.images.length) && <button className="cover-choice" onClick={() => { setCoverError(""); setCoverProject(featured); }}>选择项目封面</button>}
          {gallery.length > 0 && <ProjectGallery title="更多视频项目" className="library-gallery" projects={gallery}>{project =>
              <VideoProjectLink key={project.id} href={`/sale/${project.id}`}>
                <div className="library-frame">
                  <video muted playsInline loop preload="metadata" src={media[project.id].clip + "#t=0.1"} aria-hidden="true" />
                  <span><Icon name="film" size={15} /></span>
                </div>
                <h3>{project.name}</h3>
                <small>{project.asset_count} 个素材 · {formatTime(project.updated_at)}</small>
              </VideoProjectLink>
            }</ProjectGallery>}
          {remaining.length > 0 && <details open={!featured}>
            <summary>其他项目 <small>{remaining.length}</small></summary>
            {remaining.map(project => <Link className="library-row" key={project.id} href={`/sale/${project.id}`}>
              <strong>{project.name}</strong><small>{project.asset_count ?? 0} 个素材</small>
              <time>{formatTime(project.updated_at)}</time><Icon name="arrow" size={15} />
            </Link>)}
          </details>}
          {!projects.length && !error && <p>新建第一个项目，开始制作商品视频。</p>}
        </>}
      </div>
      <Dialog open={!!coverProject} title="选择项目封面" onClose={() => { if (!savingCover) setCoverProject(null); }}>
        {coverProject && <div className="cover-options">{media[coverProject.id]?.images.map(asset =>
          <button key={asset.id} disabled={savingCover} aria-pressed={coverProject.cover_asset_id === asset.id} onClick={() => void saveCover(asset.id)}>
            <Image unoptimized src={asset.url} alt={asset.filename} width={104} height={88} />
            <small>{asset.width} × {asset.height}</small>
          </button>)}</div>}
        {coverError && <p role="alert">{coverError}</p>}
        <button className="btn" disabled={savingCover} onClick={() => void saveCover(null)}>自动选图</button>
      </Dialog>
      <Dialog open={naming} title="新建视频项目" onClose={() => { if (!creating) setNaming(false); }}>
        <form onSubmit={e => { e.preventDefault(); void create(); }}>
          <label>项目名称<input autoFocus required maxLength={255} value={name} onChange={e => setName(e.target.value)} placeholder="例如：精华液秋季上新" /></label>
          {error && <p role="alert">{error}</p>}
          <div className="dialog-actions"><button className="btn btn-primary" disabled={!name.trim() || creating}>{creating ? "创建中…" : "创建项目"}</button></div>
        </form>
      </Dialog>
    </main>
  );
}
