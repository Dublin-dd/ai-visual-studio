import ThemeToggle from "./ThemeToggle";
import Link from "next/link";
import Icon from "./Icon";
export function Brand({ onNavigate }: { onNavigate?: () => void } = {}) { return <Link onClick={onNavigate ? e => { e.preventDefault(); onNavigate(); } : undefined} href="/" className="studio-brand" aria-label="视觉工作台首页"><span className="brand-mark"><i /><i /></span><span>视界<span className="brand-en">STUDIO</span></span></Link>; }
export default function StudioNav({ active = "home" }: { active?: "home" | "ecommerce" | "sale" }) {
  return <header className="studio-nav"><Brand /><nav aria-label="工作台导航"><Link href="/" className={active === "home" ? "active" : ""}>首页</Link><Link href="/ecommerce" className={active === "ecommerce" ? "active" : ""}><Icon name="image" size={16} />商品图</Link><Link href="/sale" className={active === "sale" ? "active" : ""}><Icon name="sparkle" size={16} />带货视频</Link></nav><div className="nav-appearance"><ThemeToggle /></div></header>;
}
