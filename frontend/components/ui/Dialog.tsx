"use client";
import { useEffect, useId, useRef, type ReactNode } from "react";
import Icon from "./Icon";
export default function Dialog({ open, onClose, title, children, wide = false }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);
  return <dialog ref={ref} aria-labelledby={titleId} className={`studio-dialog ${wide ? "studio-dialog-wide" : ""}`} onCancel={onClose} onClose={onClose} onClick={e => { if (e.target === e.currentTarget) { const r = e.currentTarget.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose(); } }}>
    <div className="dialog-head"><h2 id={titleId}>{title}</h2><button type="button" className="icon-btn" aria-label="关闭弹窗" onClick={onClose}><Icon name="close" /></button></div>{children}
  </dialog>;
}
