"use client";

import { useState, type ReactNode } from "react";
import type { ProjectOut } from "@/lib/api";

const PAGE_SIZE = 9;

export default function ProjectGallery({ title, projects, className, children }: {
  title: string;
  projects: ProjectOut[];
  className: string;
  children: (project: ProjectOut) => ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? projects : projects.slice(0, PAGE_SIZE);
  return <section>
    <div className="gallery-heading">
      <h2 className="library-section-title">{title}</h2>
      {projects.length > PAGE_SIZE && <button className="btn" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
        {expanded ? "收起" : `查看全部（${projects.length}）`}
      </button>}
    </div>
    <div className={className}>{visible.map(children)}</div>
  </section>;
}
