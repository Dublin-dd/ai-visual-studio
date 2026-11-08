/* eslint-disable @next/next/no-img-element -- Canvas media must track exact layer geometry. */
"use client";
import { useEffect, useRef, useState } from "react";
import { BOARD_HEIGHT, BOARD_WIDTH, MIN_LAYER_SIZE, type Layer } from "@/lib/canvas";
import Icon from "./ui/Icon";

type Props = {
  background?: string;
  layers: Layer[]; selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMove: (id: string, x: number, y: number) => void;
  onResize: (id: string, width: number, height: number) => void;
  zoom?: number; onScale?: (scale: number) => void;
};
type Gesture = { kind: "move" | "resize"; id: string; startX: number; startY: number; origin: Layer; x: number; y: number; width: number; height: number };
export default function Canvas({ background = "#FFFFFF", layers, selectedId, onSelect, onMove, onResize, zoom = 1, onScale }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(.6);
  const [gesture, setGesture] = useState<Gesture | null>(null);
  const gestureRef = useRef<Gesture | null>(null);
  const scale = fit * zoom;
  useEffect(() => {
    const viewport = wrap.current?.parentElement;
    if (!viewport) return;
    const update = () => {
      const style = getComputedStyle(viewport);
      const w = viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const h = viewport.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
      setFit(Math.max(.1, Math.min(1, w / BOARD_WIDTH, h / BOARD_HEIGHT)));
    };
    update(); const observer = new ResizeObserver(update); observer.observe(viewport);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { onScale?.(scale); }, [scale, onScale]);
  const start = (e: React.PointerEvent, layer: Layer, kind: "move" | "resize") => {
    if (e.button !== 0) return;
    e.preventDefault(); e.stopPropagation();
    (e.currentTarget as HTMLElement).focus();
    onSelect(layer.id);
    const g = { kind, id: layer.id, startX: e.clientX, startY: e.clientY, origin: layer, x: layer.x, y: layer.y, width: layer.width, height: layer.height };
    gestureRef.current = g; setGesture(g);
  };
  useEffect(() => {
    if (!gesture) return;
    const move = (e: PointerEvent) => {
      const g = gestureRef.current; if (!g) return;
      const dx = (e.clientX - g.startX) / scale, dy = (e.clientY - g.startY) / scale;
      const next = g.kind === "move" ? { ...g, x: g.origin.x + dx, y: g.origin.y + dy } : { ...g, width: Math.max(MIN_LAYER_SIZE, Math.min(8000, g.origin.width + dx)), height: Math.max(MIN_LAYER_SIZE, Math.min(8000, g.origin.height + dy)) };
      gestureRef.current = next; setGesture(next);
    };
    const finish = () => {
      const g = gestureRef.current;
      if (g?.kind === "move" && (g.x !== g.origin.x || g.y !== g.origin.y)) onMove(g.id, Math.round(g.x), Math.round(g.y));
      if (g?.kind === "resize" && (g.width !== g.origin.width || g.height !== g.origin.height)) onResize(g.id, Math.round(g.width), Math.round(g.height));
      gestureRef.current = null; setGesture(null);
    };
    const cancel = () => { gestureRef.current = null; setGesture(null); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", finish); window.addEventListener("pointercancel", cancel);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", finish); window.removeEventListener("pointercancel", cancel); };
  }, [gesture, scale, onMove, onResize]);
  return <div ref={wrap} className="canvas-frame" style={{ width: BOARD_WIDTH * scale, height: BOARD_HEIGHT * scale, flexShrink: 0 }}><div className="canvas-board" data-testid="canvas-board" aria-label="创作画布" style={{ backgroundColor: background, width: BOARD_WIDTH, height: BOARD_HEIGHT, transform: `scale(${scale})` }} onPointerDown={() => onSelect(null)}>
    {layers.map((layer, i) => {
      const g = gesture?.id === layer.id ? gesture : layer;
      return <div key={layer.id} role="button" tabIndex={0} aria-label={`选择图层 ${i + 1}`} aria-pressed={selectedId === layer.id} className={`canvas-layer ${selectedId === layer.id ? "selected" : ""}`} onPointerDown={e => start(e, layer, "move")} onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(layer.id); }
        if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); const n = e.shiftKey ? 10 : 1; onSelect(layer.id); onMove(layer.id, layer.x + (e.key === "ArrowRight" ? n : e.key === "ArrowLeft" ? -n : 0), layer.y + (e.key === "ArrowDown" ? n : e.key === "ArrowUp" ? -n : 0)); }
      }} style={{ left: g.x, top: g.y, width: g.width, height: g.height, zIndex: layer.z, transform: `rotate(${layer.rotation}deg)` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}<img src={layer.url} alt={`画布素材 ${i + 1}`} draggable={false} />
        {selectedId === layer.id && <span className="resize-handle" aria-hidden="true" onPointerDown={e => start(e, layer, "resize")} />}
      </div>;
    })}
    {layers.length === 0 && <div className="canvas-empty"><Icon name="image" size={42} /><p>你的下一张作品，从这里开始</p><span>上传商品图，或在左侧描述想要的画面</span></div>}
  </div></div>;
}
