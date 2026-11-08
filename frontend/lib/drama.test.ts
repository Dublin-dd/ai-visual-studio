import { describe, expect, it } from "vitest";
import {
  emptyShot,
  missingCharacters,
  parseNames,
  toServerShots,
  totalDuration,
  validateShot,
  type ShotDraft,
} from "./drama";

const shot = (over: Partial<ShotDraft> = {}): ShotDraft => ({ ...emptyShot(), ...over });

describe("validateShot", () => {
  it("合法镜头返回 null", () => {
    expect(validateShot(shot({ description: "林晚推门" }))).toBeNull();
  });

  it("空描述报错", () => {
    expect(validateShot(shot({ description: "  " }))).toContain("画面描述");
  });

  it("时长越界报错", () => {
    expect(validateShot(shot({ description: "x", duration: 1 }))).toContain("2~10");
    expect(validateShot(shot({ description: "x", duration: 11 }))).toContain("2~10");
  });

  it("非法景别报错", () => {
    expect(validateShot(shot({ description: "x", scene: "超远景" }))).toContain("景别");
  });

  it("非法运镜报错", () => {
    expect(validateShot(shot({ description: "x", camera: "旋转" }))).toContain("运镜");
  });
});

describe("missingCharacters", () => {
  it("找出未建档角色", () => {
    const shots = [
      shot({ description: "a", character_names: ["林晚", "陈默"] }),
      shot({ description: "b", character_names: ["林晚"] }),
    ];
    expect(missingCharacters(shots, ["林晚"])).toEqual(["陈默"]);
  });

  it("全部已建档返回空", () => {
    const shots = [shot({ description: "a", character_names: ["林晚"] })];
    expect(missingCharacters(shots, ["林晚", "陈默"])).toEqual([]);
  });

  it("无角色返回空", () => {
    expect(missingCharacters([shot({ description: "a" })], [])).toEqual([]);
  });
});

describe("parseNames", () => {
  it("支持多种分隔符", () => {
    expect(parseNames("林晚,陈默、小七 阿May")).toEqual(["林晚", "陈默", "小七", "阿May"]);
  });

  it("空输入", () => {
    expect(parseNames("  ")).toEqual([]);
  });

  it("最多 8 个", () => {
    expect(parseNames("a,b,c,d,e,f,g,h,i,j")).toHaveLength(8);
  });
});

describe("toServerShots", () => {
  it("重排 index 并取整时长", () => {
    const out = toServerShots([
      shot({ description: " a ", duration: 4.6 }),
      shot({ description: "b", duration: 7 }),
    ]);
    expect(out[0].index).toBe(1);
    expect(out[0].description).toBe("a");
    expect(out[0].duration).toBe(5);
    expect(out[1].index).toBe(2);
  });
});

describe("totalDuration", () => {
  it("累加时长", () => {
    expect(totalDuration([shot({ duration: 3 }), shot({ duration: 5 })])).toBe(8);
  });

  it("非法值按 0 计", () => {
    expect(totalDuration([shot({ duration: Number.NaN })])).toBe(0);
  });
});
