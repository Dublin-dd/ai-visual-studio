"use client";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import StudioNav from "@/components/ui/StudioNav";
import { apiJson, type AssetOut, type ProjectOut } from "@/lib/api";

type Recent = { project: ProjectOut; image?: string; isVideo: boolean };
function RecentProjects() {
  const [rows, setRows] = useState<Recent[]>([]);
  const [status, setStatus] = useState("正在读取项目…");
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    async function load() {
      const data = await apiJson<{items: ProjectOut[]}>("/api/projects?workspace=ecommerce", options);
      const recent = await Promise.all(data.items.filter(p => p.asset_count).slice(0, 3).map(async project => {
        const { items } = await apiJson<{items: AssetOut[]}>(`/api/projects/${project.id}/assets`, options);
        return { project, image: items.find(a => a.mime.startsWith("image/"))?.url,
          isVideo: items.some(a => a.mime.startsWith("video/")) };
      }));
      if (!controller.signal.aborted) { setRows(recent); setStatus("创建项目后，可以在这里继续制作。"); }
    }
    load().catch(() => { if (!controller.signal.aborted) setStatus("暂时无法读取最近项目。"); });
    return () => controller.abort();
  }, []);
  return <section className="desk-recent"><h2>继续创作</h2>{rows.length ? rows.map(({project,image,isVideo}) =>
    <Link key={project.id} href={`/${isVideo ? "sale" : "ecommerce"}/${project.id}`}>
      {image && <Image unoptimized src={image} alt="" width={85} height={61} />}
      <div><strong>{project.name}</strong><small>{isVideo ? "带货视频" : "商品图"} · {project.asset_count} 个素材</small></div>
      <span>{isVideo ? "继续制作" : "打开画布"}　→</span>
    </Link>) : <p>{status}</p>}</section>;
}

export default function HomePage() {
  return <main className="studio studio-home"><StudioNav active="home" />
    <div className="desk"><h1>创作工作台</h1>
      <div className="desk-portals">
        <Link href="/ecommerce" className="desk-portal photo"><div className="desk-copy"><h2>商品图</h2><p>主图、场景图与多色 SKU</p><span className="btn btn-primary">开始制图　↗</span></div>
          <div className="desk-art prints" aria-hidden="true">{["amber-candle","amber-candle"].map((id, index) => <Image unoptimized key={index} src={`/studio/${id}.webp`} width={260} height={280} sizes="(max-width:600px) 28vw, 220px" alt="" />)}</div>
        </Link>
        <Link href="/sale" className="desk-portal film"><div className="desk-copy"><h2>带货视频</h2><p>分镜、配音与成片制作</p><span className="btn btn-primary">制作视频　↗</span></div>
          <div className="desk-art frames" aria-hidden="true"><div className="film-strip">{["blue-headphones","blue-headphones"].map((id, index) => <Image unoptimized key={index} src={`/studio/${id}.webp`} width={72} height={90} alt="" />)}</div><div className="film-front">
            <Image unoptimized src="/studio/blue-headphones.webp" fill sizes="160px" alt="" />
            <Image unoptimized className="film-cutaway" src="/studio/blue-headphones.webp" fill sizes="160px" alt="" />
            <small aria-hidden="true">▶</small></div></div>
        </Link>
      </div><RecentProjects />
    </div></main>;
}
