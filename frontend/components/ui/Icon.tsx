import type { CSSProperties } from "react";

const paths = {
  plus: "M12 5v14M5 12h14",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  back: "M19 12H5m6-6-6 6 6 6",
  chevron: "m9 5 7 7-7 7",
  down: "m6 9 6 6 6-6",
  image: "M4 4h16v16H4zM4 16l5-5 4 4 3-3 4 4M8 8h.01",
  film: "M4 4h16v16H4zM8 4v16M16 4v16M4 9h4m-4 6h4m8-6h4m-4 6h4",
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  sparkle: "m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4zM20 2v4m-2-2h4",
  upload: "M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5",
  download: "M12 3v13m-5-5 5 5 5-5M4 16v4h16v-4",
  layers: "m12 3 10 6-10 6L2 9zM2 13l10 6 10-6M2 17l10 6 10-6",
  clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  undo: "M9 5 4 10l5 5M4 10h10a6 6 0 0 1 6 6v3",
  redo: "m15 5 5 5-5 5m5-5H10a6 6 0 0 0-6 6v3",
  close: "m6 6 12 12M6 18 18 6",
  check: "m5 12 4 4L19 6",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7",
  cursor: "m5 3 14 9-7 1-3 7z",
  crop: "M6 3v15h15M3 6h15v15",
  sliders: "M4 7h8m4 0h4M4 17h4m4 0h8M12 4v6M8 14v6",
  search: "M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  folder: "M3 7V4h6l3 3h9v13H3z",
  expand: "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5",
  minus: "M5 12h14",
  up: "m6 10 6-6 6 6M12 4v16",
  refresh: "M20 7a9 9 0 1 0 1 8M20 3v5h-5",
  warning: "m12 3 10 18H2zM12 9v5m0 3h.01",
  scissors: "m8 8 12 12M8 16 20 4M9 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  palette: "M12 3a9 9 0 0 0 0 18h1a2 2 0 0 0 1-4c-1-1 0-3 2-3h2a3 3 0 0 0 3-3 9 9 0 0 0-9-8M7 9h.01M11 6h.01M16 7h.01M6 14h.01",
} as const;
export type IconName = keyof typeof paths;
export default function Icon({ name, size = 18, className = "", style }: { name: IconName; size?: number; className?: string; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className} style={style} aria-hidden="true"><path d={paths[name]} /></svg>;
}
