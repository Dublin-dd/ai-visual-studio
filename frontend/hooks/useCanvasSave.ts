"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "@/lib/api";
import { toServerLayers, type Layer } from "@/lib/canvas";
import { createSaveQueue } from "@/lib/save-queue";

export function useCanvasSave(projectId: string, layers: Layer[]) {
  const [status, setStatus] = useState<"saved" | "pending" | "saving" | "error">("saved");
  const initial = useRef(layers);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const active = useRef(true);
  const current = useRef(layers);
  current.current = layers;
  const queue = useMemo(() => createSaveQueue((snapshot: ReturnType<typeof toServerLayers>) => apiJson(`/api/projects/${projectId}/layers`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layers: snapshot }) })), [projectId]);
  const save = useCallback(async () => {
    if (active.current) setStatus("saving");
    try { await queue.flush(); if (active.current) setStatus("saved"); }
    catch (error) { if (active.current) setStatus("error"); throw error; }
  }, [queue]);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  useEffect(() => {
    if (layers === initial.current) return;
    queue.set(toServerLayers(layers)); setStatus("pending");
    timer.current = setTimeout(() => { void save().catch(() => {}); }, 700);
    return () => clearTimeout(timer.current);
  }, [layers, queue, save]);
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => { if (queue.dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", guard);
    return () => { window.removeEventListener("beforeunload", guard); };
  }, [queue]);
  const flush = useCallback(async () => {
    clearTimeout(timer.current);
    queue.set(toServerLayers(current.current));
    await save();
  }, [queue, save]);
  return { status, flush };
}
