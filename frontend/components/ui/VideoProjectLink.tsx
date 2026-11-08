"use client";

import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";

export default function VideoProjectLink({ href, className, children }: {
  href: string; className?: string; children: ReactNode;
}) {
  const link = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    const card = link.current;
    if (!card) return;
    const motion = matchMedia("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)");
    let timer: ReturnType<typeof setTimeout> | undefined;
    function stop() {
      clearTimeout(timer);
      const video = card?.querySelector("video");
      if (!video) return;
      video.pause();
      if (video.readyState >= 1) video.currentTime = 0.1;
      card?.removeAttribute("data-preview");
    }
    function enter(event: PointerEvent) {
      if (!motion.matches || event.pointerType === "touch") return;
      timer = setTimeout(() => {
        const video = card?.querySelector("video");
        if (!video) return;
        card?.setAttribute("data-preview", "");
        video.play().catch(() => { if (video.paused) card?.removeAttribute("data-preview"); });
      }, 280);
    }
    card.addEventListener("pointerenter", enter);
    card.addEventListener("pointerleave", stop);
    motion.addEventListener("change", stop);
    return () => {
      stop();
      card.removeEventListener("pointerenter", enter);
      card.removeEventListener("pointerleave", stop);
      motion.removeEventListener("change", stop);
    };
  }, []);
  return <Link href={href} className={className} ref={link}>{children}</Link>;
}
