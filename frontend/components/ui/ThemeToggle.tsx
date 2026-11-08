"use client";

export default function ThemeToggle() {
  function toggleTheme() {
    const root = document.documentElement;
    const next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    try { localStorage.setItem("studio.theme", next); } catch {}
  }
  return <button type="button" className="theme-toggle" onClick={toggleTheme}>
    <span className="to-light" title="切换到日间模式"><b aria-hidden="true">☀</b><i className="sr-only">切换到日间模式</i></span>
    <span className="to-dark" title="切换到夜间模式"><b aria-hidden="true">☾</b><i className="sr-only">切换到夜间模式</i></span>
  </button>;
}
