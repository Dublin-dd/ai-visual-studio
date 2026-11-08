import { describe, expect, it } from "vitest";
import { MAX_COLORS, parseColors } from "./sku";

describe("parseColors", () => {
  it("逗号分隔", () => {
    expect(parseColors("淡粉,浅蓝,薄荷绿")).toEqual(["淡粉", "浅蓝", "薄荷绿"]);
  });

  it("中文逗号与顿号", () => {
    expect(parseColors("淡粉，浅蓝、薄荷绿")).toEqual(["淡粉", "浅蓝", "薄荷绿"]);
  });

  it("空格分隔并去重", () => {
    expect(parseColors("红 蓝 红")).toEqual(["红", "蓝"]);
  });

  it("空输入返回空数组", () => {
    expect(parseColors("   ")).toEqual([]);
    expect(parseColors(",,，、")).toEqual([]);
  });

  it("超过上限截断", () => {
    expect(parseColors("a,b,c,d,e,f")).toHaveLength(MAX_COLORS);
  });

  it("保留多字颜色名", () => {
    expect(parseColors("玫瑰金,珊瑚橘")).toEqual(["玫瑰金", "珊瑚橘"]);
  });

  it("自定义上限", () => {
    expect(parseColors("a,b,c", 2)).toEqual(["a", "b"]);
  });
});
