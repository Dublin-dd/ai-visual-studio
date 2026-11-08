import Image from "next/image";
import Icon from "./Icon";

export default function SectionHero({ video = false, onCreate }: { video?: boolean; onCreate: () => void }) {
  const source = video ? "/studio/blue-headphones.webp" : "/studio/amber-candle.webp";
  return <header className={`section-hero ${video ? "headphone" : "candle"}`}>
    <div className="section-art" aria-hidden="true">
      <Image unoptimized priority fill src={source} alt="" />
      {video && <Image unoptimized fill className="ear-detail" src={source} alt="" />}
    </div>
    <div className="section-copy">
      <h1>{video ? "带货视频" : "商品图"}</h1>
      <p>{video ? "分镜、配音与成片制作" : "主图、场景图与多色 SKU"}</p>
      <button className="btn btn-primary" onClick={onCreate}><Icon name="plus" size={15} />
        {video ? "新建视频项目" : "新建商品图项目"}
      </button>
    </div>
  </header>;
}
