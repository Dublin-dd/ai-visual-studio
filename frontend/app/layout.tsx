import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./appearance.css";

export const metadata: Metadata = {
  title: "云端 AI 视觉创作工作台",
  description: "画布式 AI 视觉创作：上传商品图、生成场景图、组合导出",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: `
        (() => {
          const media = matchMedia('(prefers-color-scheme: light)');
          function sync() {
            let saved;
            try { saved = localStorage.getItem('studio.theme'); } catch {}
            document.documentElement.dataset.theme = ['light','dark'].includes(saved)
              ? saved : media.matches ? 'light' : 'dark';
          }
          sync();
          media.addEventListener('change', sync);
          window.addEventListener('storage', sync);
        })();
      ` }} /></head>
      <body>{children}</body>
    </html>
  );
}
